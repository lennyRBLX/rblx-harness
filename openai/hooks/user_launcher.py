#!/usr/bin/env python3
"""Locate a sibling Roblox harness and forward one Codex user hook."""

import json
import os
import subprocess
import sys


def managed_root(cwd):
    current = os.path.realpath(cwd)
    while True:
        if os.path.isfile(os.path.join(current, ".roblox")):
            return current
        if os.path.basename(current).lower() == "harness" and os.path.isfile(
            os.path.join(current, "shared", "CORE.md")
        ):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return ""
        current = parent


def harness_root(root):
    if os.path.basename(root).lower() == "harness":
        return root
    candidate = os.path.join(os.path.dirname(root), "harness")
    return candidate if os.path.isfile(os.path.join(candidate, "shared", "CORE.md")) else ""


def main(argv=None):
    raw = sys.stdin.buffer.read()
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        sys.stderr.write("hook-launcher: malformed payload\n")
        return 2
    root = managed_root(payload.get("cwd") or os.getcwd()) if isinstance(payload, dict) else ""
    if not root:
        return 0
    harness = harness_root(root)
    if not harness:
        sys.stderr.write("hook-launcher: sibling harness is absent\n")
        return 2
    adapter = os.path.join(harness, "openai", "hooks", "adapter.py")
    command = [sys.executable, "-B", adapter] + list(sys.argv[1:] if argv is None else argv)
    result = subprocess.run(command, input=raw, capture_output=True)
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
