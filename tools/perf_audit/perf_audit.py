#!/usr/bin/env python3
"""perf_audit — static performance and representation candidates, Studio-free.
Performance thresholds are advisory; findings are warnings, not measured gains."""

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
