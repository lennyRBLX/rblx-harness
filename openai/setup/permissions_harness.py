#!/usr/bin/env python3
"""Install the optional Roblox profile or relink one project."""

import argparse
import os
import re
import subprocess
import sys


HARNESS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BEGIN = "# BEGIN optional rblx-harness Roblox profile"
END = "# END optional rblx-harness Roblox profile"
PROFILE = """# BEGIN optional rblx-harness Roblox profile
[permissions.Roblox]
extends = ":workspace"

[permissions.Roblox.filesystem]
"~/.cache/harness" = "write"
"~/.cache/harness/creator-docs/.git" = "write"

[permissions.Roblox.filesystem.":workspace_roots"]
".git" = "write"
"rblx-harness/tools/bin" = "write"
"tools/bin" = "write"

[permissions.Roblox.network]
enabled = true

[permissions.Roblox.network.domains]
"raw.githubusercontent.com" = "allow"
"github.com" = "allow"
"codeload.github.com" = "allow"
"objects.githubusercontent.com" = "allow"
"release-assets.githubusercontent.com" = "allow"
"localhost" = "allow"
"127.0.0.1" = "allow"
# END optional rblx-harness Roblox profile
"""


def config_path():
    home = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
    return os.path.join(os.path.realpath(os.path.expanduser(home)), "config.toml")


def profile_present(text):
    return bool(re.search(r"(?m)^\s*\[permissions\.Roblox\]\s*$", text))


def install_profile():
    path = config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        current = open(path, encoding="utf-8").read()
    except OSError:
        current = ""
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\s*", re.DOTALL)
    unmanaged = pattern.sub("", current).strip()
    if profile_present(unmanaged):
        print("permissions-profile|PRESENT|optional; Full Access remains supported")
        return 0
    rendered = "\n\n".join(part for part in (unmanaged, PROFILE.strip()) if part) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(rendered)
    print("permissions-profile|INSTALLED|optional; no profile selection or restart required")
    return 0


def relink(root):
    return subprocess.call(
        [sys.executable, os.path.join(HARNESS, "setup_project.py"), "--project", root, "--from-state"],
        cwd=root,
    )


def main(argv=None):
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--install", action="store_true")
    group.add_argument("--relink", action="store_true")
    args = parser.parse_args(argv)
    if args.install:
        return install_profile()
    if args.relink:
        return relink(os.path.realpath(os.getcwd()))
    try:
        current = open(config_path(), encoding="utf-8").read()
    except OSError:
        current = ""
    print("permissions-profile|%s|optional; Full Access supported" % ("PRESENT" if profile_present(current) else "ABSENT"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
