#!/usr/bin/env python3
"""Validate the lean rblx-harness project surface."""

import argparse
import json
import os
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(HARNESS, "shared", "gates"))
import gatelib


LOCAL_STATE = {
    ".agents": ".agents/.rblx-harness-probe",
    ".codex": ".codex/.rblx-harness-probe",
    ".serena": ".serena/.rblx-harness-probe",
    ".roblox": ".roblox",
    ".rblx-new-game.json": ".rblx-new-game.json",
}


def load_manifest(root, errors):
    path = os.path.join(root, "manifest.json")
    try:
        value = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append("manifest: %s" % error)
        return {}
    if not isinstance(value, dict) or value.get("schema") != 1:
        errors.append("manifest: schema 1 is required")
        return {}
    return value


def has_link(root):
    if not os.path.isdir(root):
        return False
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        if any(os.path.islink(os.path.join(directory, name)) for name in dirnames + filenames):
            return True
    return False


def validate_local_state(root, errors):
    for relative, probe in LOCAL_STATE.items():
        rc, tracked, detail = gatelib.git(root, "ls-files", "--", relative)
        if rc != 0:
            errors.append("local state: cannot inspect %s: %s" % (relative, detail))
        elif tracked:
            errors.append("local state must not be tracked: %s" % relative)
        rc, _, _ = gatelib.git(root, "check-ignore", "--no-index", "--quiet", "--", probe)
        if rc != 0:
            errors.append("local state is not ignored: %s" % relative)


def validate(root):
    root = os.path.realpath(root)
    errors = []
    if not gatelib.is_roblox_project(root):
        errors.append("marker: .roblox is absent")
    dependency = os.path.join(root, "rblx-harness")
    if not gatelib.project_harness_root(root):
        errors.append("submodule: rblx-harness is absent, invalid, or not registered from the required GitHub URL")
    manifest = load_manifest(root, errors)
    places = manifest.get("places") if isinstance(manifest.get("places"), list) else []
    if not places:
        errors.append("places: at least one place is required")
    for place in places:
        path = os.path.join(root, place + ".project.json")
        try:
            document = json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError) as error:
            errors.append("project %s: %s" % (place, error))
            continue
        if not isinstance(document, dict) or not isinstance(document.get("tree"), dict):
            errors.append("project %s: tree is absent" % place)
        for relative in (
            "places/%s/src/ServerScriptService/Services" % place,
            "places/%s/src/StarterPlayer/StarterPlayerScripts/Controllers" % place,
        ):
            if not os.path.isdir(os.path.join(root, *relative.split("/"))):
                errors.append("place path is absent: %s" % relative)
    if not os.path.isfile(os.path.join(root, "default.project.json")):
        errors.append("default.project.json is absent")
    for name in ("AGENTS.md", "README.md"):
        if not os.path.isfile(os.path.join(root, name)):
            errors.append("template output is absent: %s" % name)
    if not os.path.isfile(gatelib.SHARED_HANDOFF):
        errors.append("shared compaction handoff is absent: rblx-harness/shared/HANDOFF.md")
    if os.path.exists(os.path.join(root, ".claude")) or os.path.exists(os.path.join(root, "CLAUDE.md")):
        errors.append("Claude support must be absent")
    validate_local_state(root, errors)

    agents_ok, detail = gatelib.required_codex_agents_status(root)
    if not agents_ok:
        errors.append("agents: %s" % detail)
    hooks_ok, detail, _ = gatelib.hook_definition_status(root)
    if not hooks_ok:
        errors.append("hooks: %s" % detail)
    for skill in gatelib.REQUIRED_SKILLS:
        path = os.path.join(root, ".agents", "skills", skill)
        if not os.path.isdir(path) or not os.path.isfile(os.path.join(path, "SKILL.md")):
            errors.append("skill is absent: %s" % skill)
    if os.path.lexists(os.path.join(root, ".agents", "skills", "rblx-new-game")):
        errors.append("rblx-new-game must not be installed inside a managed project")

    asset_values = manifest.get("assets") or []
    if not isinstance(asset_values, list) or any(not isinstance(value, str) for value in asset_values):
        errors.append("manifest assets must be a list of names")
        assets = set()
    else:
        if "plugin" in asset_values:
            errors.append("manifest uses legacy plugin asset; use plugins")
        assets = set(asset_values)
        unknown = assets.difference(("packages", "services", "controllers", "plugins"))
        if unknown:
            errors.append("manifest has unknown assets: %s" % ", ".join(sorted(unknown)))
    asset_roots = {
        "packages": os.path.join(root, "shared", "src", "ReplicatedStorage", "Packages"),
        "services": os.path.join(root, "shared", "src", "ServerScriptService", "Services"),
        "controllers": os.path.join(root, "shared", "src", "StarterPlayer", "StarterPlayerScripts", "Controllers"),
    }
    for asset, path in asset_roots.items():
        if asset in assets and not has_link(path):
            errors.append("%s asset links are absent" % asset)
    if os.path.lexists(os.path.join(root, "plugin")):
        errors.append("legacy plugin/ is present; use plugins/")
    if "plugins" in assets and not os.path.isdir(os.path.join(root, "plugins")):
        errors.append("plugin support is selected but plugins/ is absent")

    for base in (os.path.join(root, "shared"), os.path.join(root, ".agents")):
        if not os.path.isdir(base):
            continue
        for directory, dirnames, filenames in os.walk(base, followlinks=False):
            for name in dirnames + filenames:
                path = os.path.join(directory, name)
                if os.path.islink(path) and not os.path.exists(path):
                    errors.append("dead symlink: %s" % os.path.relpath(path, root))
    for relative in (
        "tools/data_write/data_write.py",
        "tools/type_write/type_write.py",
        "tools/api_dump/api_dump.py",
        "tools/frame_census/frame_census.py",
        "tools/create_boilerplate/create_boilerplate.py",
        "tools/style_assess/style_assess.py",
    ):
        if not os.path.isfile(os.path.join(dependency, *relative.split("/"))):
            errors.append("harness tool is absent: %s" % relative)
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=os.getcwd())
    args = parser.parse_args(argv)
    errors = validate(args.project_root)
    if errors:
        for error in errors:
            sys.stderr.write("project-gate|ERROR|%s\n" % error)
        return 2
    print("project-gate|READY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
