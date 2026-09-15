#!/usr/bin/env python3
"""Install the optional Roblox Claude Code settings profile or relink one project.

Claude Code has no named permission profiles. The closest native form is a
settings file passed with `claude --settings PATH`, which applies to that session
only, so the profile stays optional. Sandboxed commands already write to the
working directory; `.claude` and `.git` hooks/config are protected paths that no
grant can lift, so run setup_project.py outside the sandbox.
"""

import argparse
import json
import os
import subprocess
import sys


HARNESS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROFILE_NAME = "rblx-harness-roblox.json"
PROFILE = {
    "sandbox": {
        "enabled": True,
        "filesystem": {
            "allowWrite": ["~/.cache/harness"],
        },
        "network": {
            "allowedDomains": [
                "raw.githubusercontent.com",
                "github.com",
                "codeload.github.com",
                "objects.githubusercontent.com",
                "release-assets.githubusercontent.com",
                "localhost",
                "127.0.0.1",
            ],
        },
    },
}


def config_path():
    home = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    return os.path.join(os.path.realpath(os.path.expanduser(home)), PROFILE_NAME)


def add_missing(current, defaults, label="profile"):
    """Add absent keys and list entries while retaining explicit user choices."""
    changed = False
    for key, value in defaults.items():
        name = "%s.%s" % (label, key)
        if key not in current:
            current[key] = json.loads(json.dumps(value))
            changed = True
        elif isinstance(value, dict):
            if not isinstance(current[key], dict):
                raise ValueError("%s must contain an object" % name)
            changed = add_missing(current[key], value, name) or changed
        elif isinstance(value, list):
            if not isinstance(current[key], list):
                raise ValueError("%s must contain an array" % name)
            missing = [item for item in value if item not in current[key]]
            current[key].extend(missing)
            changed = changed or bool(missing)
    return changed


def install_profile():
    path = config_path()
    try:
        with open(path, encoding="utf-8") as handle:
            current = handle.read()
    except FileNotFoundError:
        current = None
    if current is None:
        profile, state = {}, "INSTALLED"
    else:
        profile, state = json.loads(current), "UPDATED"
        if not isinstance(profile, dict):
            raise ValueError("%s must contain an object" % path)
    if not add_missing(profile, PROFILE):
        print("permissions-profile|PRESENT|optional; start Claude Code with --settings %s" % path)
        return 0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(profile, indent=2) + "\n")
    print("permissions-profile|%s|optional; start Claude Code with --settings %s" % (state, path))
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
    present = os.path.isfile(config_path())
    print("permissions-profile|%s|optional; default permissions supported" % ("PRESENT" if present else "ABSENT"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError, AttributeError) as error:
        sys.stderr.write("permissions-profile|ERROR|%s\n" % error)
        sys.exit(2)
