#!/usr/bin/env python3
"""Install the optional Roblox profile or relink one project."""

import argparse
import os
import re
import subprocess
import sys
import tomllib


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
".agents" = "write"
".codex" = "write"
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
WORKSPACE_ROOTS_HEADER = '[permissions.Roblox.filesystem.":workspace_roots"]'
RUNTIME_WRITE_ENTRIES = (".agents", ".codex")


def config_path():
    home = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
    return os.path.join(os.path.realpath(os.path.expanduser(home)), "config.toml")


def profile_present(text):
    permissions = tomllib.loads(text).get("permissions", {})
    return isinstance(permissions, dict) and isinstance(permissions.get("Roblox"), dict)


def add_runtime_writes(text):
    """Add absent grants while retaining explicit choices and multiline strings."""
    profile = tomllib.loads(text)["permissions"]["Roblox"]
    filesystem = profile.get("filesystem", {})
    grants = filesystem.get(":workspace_roots", {})
    missing = [name for name in RUNTIME_WRITE_ENTRIES if name not in grants]
    if not missing:
        return text, False
    additions = "".join('\n"%s" = "write"' % name for name in missing)
    # A candidate heading inside an open multiline string has an invalid prefix.
    # Parse headers independently so quoted/dotted TOML keys retain their meaning.
    for header in re.finditer(r"(?m)^[ \t]*\[[^\r\n]+\][ \t]*(?:#[^\r\n]*)?$", text):
        try:
            tomllib.loads(text[:header.start()])
            table = tomllib.loads(header.group())
        except tomllib.TOMLDecodeError:
            continue
        if table == {"permissions": {"Roblox": {"filesystem": {":workspace_roots": {}}}}}:
            updated = text[:header.end()] + additions + text[header.end():]
            tomllib.loads(updated)
            return updated, True
    if ":workspace_roots" not in filesystem:
        updated = text.rstrip() + "\n\n" + WORKSPACE_ROOTS_HEADER + additions + "\n"
        tomllib.loads(updated)
        return updated, True
    # Inline and dotted definitions need no rewrite of user configuration.
    return text, False


def install_profile():
    path = config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        current = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        current = ""
    if profile_present(current):
        updated, changed = add_runtime_writes(current)
        if changed:
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(updated)
            print("permissions-profile|UPDATED|runtime directories allowed; Full Access remains supported")
        else:
            print("permissions-profile|PRESENT|optional; Full Access remains supported")
        return 0
    rendered = current + ("\n\n" if current else "") + PROFILE
    tomllib.loads(rendered)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(rendered)
    print("permissions-profile|INSTALLED|optional; select the Roblox profile to use it")
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
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError, AttributeError) as error:
        sys.stderr.write("permissions-profile|ERROR|%s\n" % error)
        sys.exit(2)
