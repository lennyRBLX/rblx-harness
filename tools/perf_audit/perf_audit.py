#!/usr/bin/env python3
"""perf_audit — OPT15, OPT18, OPT19, OPT20. Statically decidable and
Studio-free, which is what lets it stay in done-gate's floor with Studio
closed. Fails open, warns: performance findings are recoverable by revert and
the thresholds are advisory — a false block here costs a correct write."""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import lint_driver  # noqa: E402

if __name__ == "__main__":
    try:
        sys.exit(lint_driver.scan("perf_audit", os.path.join(HERE, "rules"), sys.argv[1:], fails_open=True))
    except SystemExit:
        raise
    except Exception as e:
        sys.stderr.write("perf_audit: CRASH %s: %s - nothing was scanned\n" % (type(e).__name__, e))
        sys.exit(2)
