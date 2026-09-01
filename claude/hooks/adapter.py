#!/usr/bin/env python3
"""Claude Code hook adapter."""

import os
import sys

HARNESS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HARNESS, "shared", "gates"))
from adapterlib import main  # noqa: E402

if __name__ == "__main__":
    if sys.argv[1:3] != ["--host", "claude"]:
        sys.stderr.write("hook-adapter: explicit --host claude is required\n")
        sys.exit(2)
    sys.exit(main("claude", sys.argv[3:]))
