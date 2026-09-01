#!/usr/bin/env python3
"""Run required validation before the assistant emits its final response."""

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gatelib  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--session", required=True)
    args = parser.parse_args(argv)
    root = os.path.realpath(args.root)
    if not os.path.isdir(root):
        sys.stderr.write("finalize: project root is absent\n")
        return 2
    if not args.session.strip():
        sys.stderr.write("finalize: session identity is absent\n")
        return 2
    if gatelib.is_harness(root):
        command = [
            sys.executable,
            os.path.join(HERE, "harness_gate.py"),
            "--validate",
            "--session-id",
            args.session,
        ]
    elif gatelib.is_roblox_project(root):
        command = [
            sys.executable,
            os.path.join(HERE, "done_gate.py"),
            "--validate",
            "--root",
            root,
            "--session",
            args.session,
        ]
    else:
        sys.stderr.write("finalize: root is neither harness nor a managed .roblox project\n")
        return 2
    result = subprocess.run(
        command,
        cwd=root,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
