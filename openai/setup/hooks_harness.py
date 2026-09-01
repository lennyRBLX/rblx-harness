#!/usr/bin/env python3
"""Install/verify the stable user-level Roblox harness hooks."""

import os
import sys

HARNESS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HARNESS, "shared", "gates"))
import gatelib  # noqa: E402


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--install" not in argv:
        ok, detail, _ = gatelib.hook_definition_status(os.getcwd(), "user", "codex")
        if not ok:
            print(
                "Install Roblox harness hooks, then retry the current task: python3 %s --install"
                % os.path.abspath(__file__)
            )
            return 2
        print("hooks-harness|READY")
        return 0
    ok, detail, changed = gatelib.install_user_hooks()
    if not ok:
        print("Fix %s → rerun this cmd." % detail)
        return 2
    status = "hooks-harness|%s" % ("installed" if changed else "exact")
    if changed:
        print(status + "|Review changed hooks during maintenance; retry and continue the current task.")
    else:
        print(status + "|discovery exact; no new task required.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
