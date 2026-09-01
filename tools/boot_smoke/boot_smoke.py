#!/usr/bin/env python3
"""boot_smoke — DEBUG11's ratified console taxonomy as one command.

Pipeline: argon sourcemap -> luau-lsp analyze -> StudioMCP start_stop_play ->
console scrape. Studio-only by locked decision, no Open Cloud; the target
place must already be open.

Output: stage lines, then one final JSON verdict line:
    {"sourcemap": {...}, "analyze": {...}, "play": {...}, "pass": bool}
Exit 0 pass · 2 boot errors or analyze findings · 3 environment. done-gate
blocks on 2 AND on 3 — an unreachable Studio is not waved through; the same
precondition already blocks writes at write-gate under GATE4, so the two
gates fail for one stated reason.

Usage: boot_smoke.py [--root DIR] [--project FILE] [--play-seconds N]
                     [--mcp-cmd CMD] [--console-log FILE] [--session ID]
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
HARNESS = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(HARNESS, "shared", "gates"))
import gatelib  # noqa: E402
import studio_rpc  # noqa: E402
from studio_rpc import EnvError, StudioRPC  # noqa: E402

LUAU_LSP = gatelib.bundled_tool_path("luau-lsp")
DEFINITIONS = os.path.join(TOOLS, "globalTypes.d.luau")
BASE_LUAURC = os.path.join(TOOLS, "base.luaurc")

DIAGNOSTIC_RE = re.compile(r"^.+\(\d+,\d+\): \w+")
# the ratified taxonomy [R DEBUG11]
ERROR_RE = re.compile(
    r"(?i)\berrors?\b|\bexception\b|stack begin|attempt to (index|call|perform|compare)"
    r"|failed to load|cannot resume|is not a valid member|infinite loop"
)
WARN_RE = re.compile(
    r"(?i)\bwarn\b|infinite yield|\bfailed\b|services? unavailable|attempted to call require"
)


def classify_line(line):
    if ERROR_RE.search(line):
        return "error"
    if WARN_RE.search(line):
        return "warning"
    return "ok"


def new_console_lines(baseline, post):
    base_lines = baseline.splitlines()
    post_lines = post.splitlines()
    if post_lines[: len(base_lines)] == base_lines:
        return post_lines[len(base_lines):]
    return post_lines  # log rotated/cleared: treat everything as new


def read_places_map(root):
    mapping = {}
    claude_md = os.path.join(root, "CLAUDE.md")
    if os.path.exists(claude_md):
        with open(claude_md, encoding="utf-8") as f:
            text = f.read()
        m = re.search(r"^## places\s*\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
        if m:
            for line in m.group(1).strip().split("\n"):
                parts = line.strip().split("|")
                if len(parts) == 2 and parts[1].isdigit():
                    mapping[parts[0]] = int(parts[1])
    return mapping


def stage_sourcemap(root, project_name):
    project = os.path.join(root, project_name)
    if not os.path.isfile(project):
        raise EnvError("no-project", "no %s under %s" % (project_name, root))
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "sourcemap.json")
        gen = subprocess.run(["argon", "sourcemap", project, "-o", out], capture_output=True, text=True, cwd=root)
        if gen.returncode != 0 or not os.path.isfile(out):
            return {"pass": False, "detail": (gen.stdout + gen.stderr).strip()[-400:]}, None
        with open(out, encoding="utf-8") as f:
            data = f.read()
    return {"pass": True}, data


def stage_analyze(root, project_name, sourcemap_data):
    lsp = LUAU_LSP if os.path.exists(LUAU_LSP) else "luau-lsp"
    if not os.path.isfile(DEFINITIONS):
        raise EnvError("definitions-absent", "vendored globalTypes.d.luau missing - tools/get_toolchain.sh")
    paths = [p for p in ("shared", "places") if os.path.isdir(os.path.join(root, p))]
    if not paths:
        paths = ["."]
    with tempfile.TemporaryDirectory() as tmp:
        smap = os.path.join(tmp, "sourcemap.json")
        with open(smap, "w", encoding="utf-8") as f:
            f.write(sourcemap_data)
        analyze = subprocess.run(
            [
                lsp,
                "analyze",
                # the pinned type posture: explicit new solver at the binary's
                # compiled-default flags, DM types off. Never add
                # --no-flags-enabled or --settings here — both silently flip
                # the flag posture.
                "--flag:LuauSolverV2=true",
                "--no-strict-dm-types",
                "--platform",
                "roblox",
                "--sourcemap",
                smap,
                "--definitions",
                "@roblox=" + DEFINITIONS,
                "--base-luaurc",
                BASE_LUAURC,
                "--ignore",
                "**/_Index/**",
                "--ignore",
                "**/Packages/**",
                "--ignore",
                "**/Modules/**",
                "--ignore",
                "**/tests/**",
                *paths,
            ],
            capture_output=True,
            text=True,
            cwd=root,
        )
    if analyze.returncode not in (0, 1):
        raise EnvError("analyze-crashed", (analyze.stdout + analyze.stderr).strip()[-300:])
    # exits 0 on lint-severity findings, so scan for path(line,col): Code:
    findings = [ln for ln in (analyze.stdout + analyze.stderr).splitlines() if DIAGNOSTIC_RE.match(ln)]
    return {"pass": not findings, "findings": len(findings), "lines": findings[:20]}


def stage_play(mcp_cmd, root, play_seconds, session_id):
    mapping = read_places_map(root)
    with StudioRPC(mcp_cmd) as rpc:
        _, place_id = rpc.select_studio(set(mapping.values()))
        if place_id == 0:
            raise EnvError("unpublished-place", "publish the place before running Studio checks")
        studio_rpc.acquire_lock(place_id, session_id, "boot_smoke")
        try:
            baseline = rpc.call("get_console_output")
            rpc.call("start_stop_play", {"is_start": True})
            try:
                time.sleep(play_seconds)
                post = rpc.call("get_console_output")
            finally:
                rpc.call("start_stop_play", {"is_start": False})
        finally:
            studio_rpc.release_lock(place_id)
    lines = new_console_lines(baseline, post)
    errors = [ln for ln in lines if classify_line(ln) == "error"]
    warnings = [ln for ln in lines if classify_line(ln) == "warning"]
    return {
        "pass": not errors,
        "seconds": play_seconds,
        "new_lines": len(lines),
        "errors": errors[:20],
        "warnings": warnings[:20],
        "place_id": place_id,
    }


def stage_play_from_log(log_path):
    if not os.path.isfile(log_path):
        raise EnvError("console-log-absent", log_path)
    with open(log_path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    errors = [ln for ln in lines if classify_line(ln) == "error"]
    warnings = [ln for ln in lines if classify_line(ln) == "warning"]
    return {"pass": not errors, "seconds": None, "new_lines": len(lines), "errors": errors[:20], "warnings": warnings[:20]}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="boot_smoke")
    parser.add_argument("--root", default=".")
    parser.add_argument("--project", default="default.project.json")
    parser.add_argument("--play-seconds", type=float, default=12.0)
    parser.add_argument("--mcp-cmd", default=None)
    parser.add_argument("--console-log", metavar="FILE")
    parser.add_argument("--session", default="local")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)

    verdict = {"sourcemap": None, "analyze": None, "play": None, "pass": False}
    try:
        verdict["sourcemap"], smap = stage_sourcemap(root, args.project)
        print("sourcemap: %s" % ("OK" if verdict["sourcemap"]["pass"] else "FAILED"))
        if not verdict["sourcemap"]["pass"]:
            print(json.dumps(verdict))
            return 2

        verdict["analyze"] = stage_analyze(root, args.project, smap)
        print("analyze: %d findings" % verdict["analyze"]["findings"])

        if args.console_log:
            verdict["play"] = stage_play_from_log(args.console_log)
        else:
            verdict["play"] = stage_play(args.mcp_cmd, root, args.play_seconds, args.session)
        play = verdict["play"]
        print("play: %d new console lines, %d errors, %d warnings" % (play["new_lines"], len(play["errors"]), len(play["warnings"])))
        for line in play["errors"]:
            print("  error: %s" % line)

        verdict["pass"] = verdict["sourcemap"]["pass"] and verdict["analyze"]["pass"] and play["pass"]
        print("boot_smoke: %s" % ("PASS" if verdict["pass"] else "FAIL"))
        print(json.dumps(verdict))
        return 0 if verdict["pass"] else 2
    except EnvError as e:
        print("ENV|%s|%s" % (e.cause, e.remedy))
        print(json.dumps(verdict))
        return 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        sys.stderr.write("boot_smoke: CRASH %s: %s - nothing was verified\n" % (type(e).__name__, e))
        sys.exit(2)
