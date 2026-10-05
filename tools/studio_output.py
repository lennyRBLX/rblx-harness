#!/usr/bin/env python3
"""Read one Studio console snapshot; return a bounded, filtered delta.

No play, execution, source writes or cleanup. --input accepts a saved text
log for offline processing. --since is the preceding snapshot for this scope.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import re
import time

from test_buffer import Collector, summary

from studio_rpc import EnvError, StudioRPC

CACHE = Path.home() / ".cache/harness/console"


def delta(before, after):
    old, new = before.splitlines(), after.splitlines()
    if not old:
        return new, "baseline"
    if new[:len(old)] == old:
        return new[len(old):], "append"
    # Only a full prefix is proof of continuity. On rotation/reset, retain all.
    return new, "reset-or-rotation"


def snapshot(scope, console, since=None, contains=(), tail=40, max_chars=8000, cache=CACHE):
    before = ""
    transport = []
    errors = []
    if since:
        raw = Path(since).read_bytes()
        if Path(since).stem != hashlib.sha256(raw).hexdigest():
            raise ValueError("snapshot hash mismatch")
        prior = json.loads(raw)
        if prior.get("schema") != "harness-console-v1" or prior.get("scope") != scope:
            raise ValueError("snapshot scope mismatch")
        before = prior["console"]
        transport = prior.get("transport", [])
        errors = prior.get("errors", [])
    lines, continuity = delta(before, console)
    selected = [line for line in lines if all(term in line for term in contains)]
    displayed = selected[-tail:]
    text = "\n".join(displayed)
    # Deduplicate transport delivery only, never equal-valued observations.
    transport = list(dict.fromkeys(transport + [line[line.find(side):].split()[0]
        for line in lines for side in ("SERVER|", "CLIENT|") if side in line and "|BUF|" in line]))
    if len(transport) > 8192:
        raise ValueError("transport retention limit; collect each run separately")
    errors = list(dict.fromkeys(errors + [line for line in lines if re.search(r"error|exception|stack begin|stack end|FAIL\|", line, re.I)]))
    controls = [line for line in lines if "|CTRL|" in line]
    payload = {"schema": "harness-console-v1", "scope": scope, "console": console, "transport": transport, "errors": errors}
    raw = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode()
    cache.mkdir(parents=True, exist_ok=True)
    artifact = cache / (hashlib.sha256(raw).hexdigest() + ".json")
    fd, temporary = tempfile.mkstemp(dir=cache, prefix=".console-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
        os.replace(temporary, artifact)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {"artifact": str(artifact), "scope": scope, "continuity": continuity,
            "new_lines": len(lines), "matched_lines": len(selected), "omitted_lines": len(selected) - len(displayed),
            "omitted_chars": max(0, len(text) - max_chars), "text": text[-max_chars:],
            "errors": errors, "controls": controls,
            "transport": transport, "result": "log-evidence-only"}


def live_console(rpc, studio_id):
    if studio_id not in {item["id"] for item in rpc.list_studios()}:
        raise ValueError("studio_id is not in the current Studio list")
    return rpc.call("get_console_output", {"studio_id": studio_id})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--studio-id")
    source.add_argument("--input", type=Path)
    parser.add_argument("--scope", help="stable scope for offline logs; defaults to input path")
    parser.add_argument("--since", type=Path)
    parser.add_argument("--contains", action="append", default=[])
    parser.add_argument("--tail", type=int, default=40)
    parser.add_argument("--max-chars", type=int, default=8000)
    parser.add_argument("--mcp-cmd")
    parser.add_argument("--side", choices=["SERVER", "CLIENT"])
    parser.add_argument("--script")
    parser.add_argument("--run")
    parser.add_argument("--wait", type=float, default=0, help="bounded result collection, seconds (0..300)")
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.tail <= 1000 or not 1 <= args.max_chars <= 100000:
            raise ValueError("tail must be 1..1000; max-chars must be 1..100000")
        if not 0 <= args.wait <= 300:
            raise ValueError("wait must be 0..300")
        expected = (args.side, args.script, args.run)
        decoding = any(expected)
        if decoding and not all(expected):
            raise ValueError("side, script and run required together")
        deadline = time.monotonic() + args.wait
        since = args.since
        retained_errors = []
        shown_controls = set()
        while True:
            if args.input:
                console = args.input.read_text(encoding="utf-8")
                scope = "file:" + (args.scope or str(args.input.resolve()))
            else:
                with StudioRPC(args.mcp_cmd) as rpc:
                    console = live_console(rpc, args.studio_id)
                scope = "studio:" + args.studio_id
            report = snapshot(scope, console, since, args.contains, args.tail, args.max_chars)
            since = report["artifact"]
            retained_errors.extend(report["errors"])
            for notice in report["controls"]:
                if notice not in shown_controls:
                    print(notice, flush=True)
                    shown_controls.add(notice)
            if not decoding:
                if report["transport"]:
                    collector = Collector()
                    collector.feed("\n".join(report["transport"]))
                    print(summary(collector.finish()))
                else:
                    print("\n".join(line for line in report["text"].splitlines() if "|CTRL|" not in line and "|BUF|" not in line))
                for error in report["errors"]:
                    if error not in report["text"]:
                        print(error)
                print("OUTPUT|" + report["continuity"] + "|artifact=" + report["artifact"])
                return 0
            collector = Collector(expected)
            collector.feed("\n".join(report["transport"]))
            try:
                records = collector.finish()
            except ValueError as error:
                if str(error) not in {"missing output", "incomplete buffer"} or time.monotonic() >= deadline:
                    for item in dict.fromkeys(retained_errors): print(item)
                    print("OUTPUT|artifact=" + report["artifact"])
                    raise
                time.sleep(min(0.25, max(0, deadline - time.monotonic())))
                continue
            # Decode every complete record before shortening any display.
            print(summary(records))
            for error in dict.fromkeys(retained_errors): print(error)
            print("OUTPUT|artifact=" + report["artifact"])
            return 0 if all(r["status"] == "pass" for _, r in records) else 2
    except (EnvError, OSError, ValueError) as error:
        print("OUTPUT|rejected|" + str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
