#!/usr/bin/env python3
"""PERMISSIONS_HARNESS installer, project relinker, and read-only preflight.

The command validates the documented static Codex permission configuration.
"""

import os
import subprocess
import sys

HARNESS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HARNESS, "shared", "gates"))
import gatelib


def install_status(profile_changed, hooks_changed):
    status = "permissions-harness|%s|hooks=%s" % (
        "installed" if profile_changed else "exact",
        "installed" if hooks_changed else "exact",
    )
    actions = []
    if profile_changed:
        actions.append("Select Roblox")
    if hooks_changed:
        actions.append("review changed hooks and approve them once with /hooks")
    if not actions:
        return status + "|discovery exact; no new task required."
    return status + "|" + "; ".join(actions) + "; retry and continue the current task."


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--relink"] or (
        len(argv) == 3 and argv[:2] == ["--relink", "--host"] and argv[2] in ("codex", "claude")
    ):
        host = argv[2] if len(argv) == 3 else "all"
        scaffold = os.path.join(
            HARNESS,
            "shared",
            "skills",
            "roblox-new-game",
            "scripts",
            "scaffold.py",
        )
        command = [sys.executable, scaffold, "relink", "--root", os.path.realpath(os.getcwd())]
        if host != "all":
            command += ["--host", host]
        return subprocess.call(command)
    if argv == ["--install"]:
        profile_ok, _ = gatelib.permissions_harness()
        changed = False
        if not profile_ok:
            ok, detail, changed = gatelib.install_permissions_harness()
            if not ok:
                print(gatelib.permissions_harness_block("profile installation failed: %s" % detail))
                return 2
        hooks_ok, hooks_detail, hooks_changed = gatelib.install_user_hooks()
        if not hooks_ok:
            print("Fix %s → rerun this cmd." % hooks_detail)
            return 2
        print(install_status(changed, hooks_changed))
        return 0
    if argv:
        print("usage: permissions_harness.py [--install|--relink [--host {codex,claude}]]")
        return 2
    ok, message = gatelib.require_permissions_harness()
    if not ok:
        print(message)
        return 2
    print("permissions-harness: READY static profile=Roblox")
    return 0


if __name__ == "__main__":
    sys.exit(main())
