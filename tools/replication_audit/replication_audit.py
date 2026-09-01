#!/usr/bin/env python3
"""replication_audit — DATA1, DATA8, REV6's four sins, WRIT8, DATA17, DES2,
DATA30. Path is load-bearing: DATA1's owner derives from Services/<Name>/, so
a file outside a service tree is skipped, not failed. Fails closed — a wrong
replication channel ships to every client and surfaces as a desync."""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import lint_driver  # noqa: E402

if __name__ == "__main__":
    try:
        sys.exit(lint_driver.scan("replication_audit", os.path.join(HERE, "rules"), sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as e:
        sys.stderr.write("Run replication_audit; fix the err; retry.\n")
        sys.exit(2)
