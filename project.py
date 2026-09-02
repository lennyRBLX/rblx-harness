#!/usr/bin/env python3
"""Project-local rblx-harness Git submodule command."""

import os
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "shared", "skills", "rblx-new-game", "scripts")
sys.path.insert(0, SCRIPTS)

from dependency import DependencyError, main  # noqa: E402


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DependencyError as error:
        sys.stderr.write("rblx-harness-dependency: ERROR %s\n" % error)
        sys.exit(2)
