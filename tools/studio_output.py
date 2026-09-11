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
    if since:
        raw = Path(since).read_bytes()
        if Path(since).stem != hashlib.sha256(raw).hexdigest():
            raise ValueError("snapshot hash mismatch")
        prior = json.loads(raw)
        if prior.get("schema") != "harness-console-v1" or prior.get("scope") != scope:
            raise ValueError("snapshot scope mismatch")
        before = prior["console"]
    lines, continuity = delta(before, console)
    selected = [line for line in lines if all(term in line for term in contains)]
    displayed = selected[-tail:]
    text = "\n".join(displayed)
    payload = {"schema": "harness-console-v1", "scope": scope, "console": console}
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
            "result": "log-evidence-only"}


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
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.tail <= 1000 or not 1 <= args.max_chars <= 100000:
            raise ValueError("tail must be 1..1000; max-chars must be 1..100000")
        if args.input:
            console = args.input.read_text(encoding="utf-8")
            scope = "file:" + (args.scope or str(args.input.resolve()))
        else:
            with StudioRPC(args.mcp_cmd) as rpc:
                console = live_console(rpc, args.studio_id)
            scope = "studio:" + args.studio_id
        print(json.dumps(snapshot(scope, console, args.since, args.contains, args.tail, args.max_chars)))
        return 0
    except (EnvError, OSError, ValueError) as error:
        print(json.dumps({"error": str(error), "result": "unavailable"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
