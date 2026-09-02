#!/usr/bin/env python3
"""Run repository or project validation before a final response."""

import argparse
import os
import subprocess
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(os.path.dirname(HERE))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--session", required=True)
    args = parser.parse_args(argv)
    root = os.path.realpath(args.root)
    if not os.path.isdir(root) or not args.session.strip():
        sys.stderr.write("finalize: root and session are required\n")
        return 2
    if root == os.path.realpath(HARNESS):
        command = [sys.executable, os.path.join(HARNESS, "tools", "tests", "run_verify.py")]
    elif os.path.isfile(os.path.join(root, ".roblox")):
        dependency = os.path.join(root, "rblx-harness")
        command = [
            sys.executable,
            os.path.join(dependency, "tools", "project_gate", "project_gate.py"),
            "--project-root",
            root,
        ]
    else:
        sys.stderr.write("finalize: root is not rblx-harness or a managed project\n")
        return 2
    result = subprocess.run(command, cwd=root, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    if result.returncode != 0:
        return result.returncode
    print("FINALIZED|session=%s" % args.session)
    return 0


if __name__ == "__main__":
    sys.exit(main())
