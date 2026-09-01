#!/usr/bin/env python3
"""Locate the platform Roblox Studio MCP executable and replace this process."""

import glob
import os
import sys


def find_studio_mcp():
    override = os.environ.get("ROBLOX_STUDIO_MCP")
    if override and os.path.isfile(override):
        return os.path.realpath(override)
    candidates = ["/Applications/RobloxStudio.app/Contents/MacOS/StudioMCP"]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.extend(glob.glob(os.path.join(local, "Roblox", "Versions", "*", "StudioMCP.exe")))
    existing = [path for path in candidates if os.path.isfile(path)]
    if not existing:
        return None
    return max(existing, key=lambda path: os.path.getmtime(path))


def main(argv=None):
    executable = find_studio_mcp()
    if not executable:
        sys.stderr.write("StudioMCP is absent; install or update Roblox Studio.\n")
        return 2
    os.execv(executable, [executable] + list(argv or []))
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
