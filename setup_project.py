#!/usr/bin/env python3
"""Install Codex support and link selected harness assets into a project."""

import argparse
import json
import os
import shutil
import sys


HARNESS = os.path.dirname(os.path.abspath(__file__))
AGENTS = ("researcher", "optimizer", "reviewer", "debugger")
PROJECT_SKILLS = ("rblx-writer", "rblx-debug", "rblx-optimize")
HARNESS_SKILLS = PROJECT_SKILLS + ("rblx-new-game",)
MANIFEST = "info.json"
IGNORE_BEGIN = "# BEGIN rblx-harness links"
IGNORE_END = "# END rblx-harness links"
LOCAL_IGNORE_BEGIN = "# BEGIN rblx-new-game"
LOCAL_IGNORE_END = "# END rblx-new-game"
LOCAL_IGNORE_ENTRIES = (
    "/.agents/",
    "/.codex/",
    "/.serena/",
    "/.roblox",
    "/.rblx-new-game.json",
    ".DS_Store",
)
ASSET_ORDER = ("packages", "services", "controllers", "plugins")


def fail(message):
    raise RuntimeError(message)


def read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, ValueError) as error:
        fail("cannot read %s: %s" % (path, error))
    if not isinstance(value, dict):
        fail("%s must contain an object" % path)
    return value


def write_json(path, value):
    write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, encoding="utf-8") as handle:
            if handle.read() == text:
                return False
    except OSError:
        pass
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return True


def remove_path(path):
    if os.path.islink(path) or os.path.isfile(path):
        os.unlink(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)


def relative_link(source, destination, directory=False, replace_regular=False):
    if not os.path.exists(source):
        fail("harness asset is absent: %s" % source)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    if os.path.islink(destination):
        if os.path.realpath(destination) == os.path.realpath(source):
            return "exact"
        os.unlink(destination)
    elif os.path.lexists(destination):
        if not replace_regular:
            return "preserved"
        if os.path.isdir(destination):
            shutil.rmtree(destination)
        else:
            os.unlink(destination)
    target = os.path.relpath(source, os.path.dirname(destination))
    try:
        os.symlink(target, destination, target_is_directory=directory)
    except OSError as error:
        fail("cannot create symlink %s -> %s: %s" % (destination, target, error))
    return "linked"


def update_ignore(directory, names):
    path = os.path.join(directory, ".gitignore")
    try:
        with open(path, encoding="utf-8") as handle:
            current = handle.read()
    except OSError:
        current = ""
    begin = current.find(IGNORE_BEGIN)
    end = current.find(IGNORE_END)
    if begin >= 0 and end >= begin:
        end += len(IGNORE_END)
        current = (current[:begin] + current[end:]).strip()
    managed = "\n".join((IGNORE_BEGIN,) + tuple(sorted(set(names))) + (IGNORE_END,))
    rendered = "\n\n".join(part for part in (current, managed) if part).strip() + "\n"
    write_text(path, rendered)


def update_local_ignore(project):
    path = os.path.join(project, ".gitignore")
    try:
        with open(path, encoding="utf-8") as handle:
            current = handle.read()
    except OSError:
        current = ""
    begin = current.find(LOCAL_IGNORE_BEGIN)
    end = current.find(LOCAL_IGNORE_END, begin if begin >= 0 else 0)
    if begin >= 0 and end >= begin:
        end += len(LOCAL_IGNORE_END)
        current = (current[:begin] + current[end:]).strip()
    managed = "\n".join((LOCAL_IGNORE_BEGIN,) + LOCAL_IGNORE_ENTRIES + (LOCAL_IGNORE_END,))
    rendered = "\n\n".join(part for part in (current, managed) if part).strip() + "\n"
    write_text(path, rendered)


def ensure_marker(project):
    marker = os.path.join(project, ".roblox")
    if os.path.lexists(marker) and (os.path.islink(marker) or not os.path.isfile(marker)):
        fail(".roblox must be a regular file")
    if not os.path.exists(marker):
        write_text(marker, "")


def normalize_assets(manifest):
    raw = manifest.get("assets") or []
    if not isinstance(raw, list) or any(not isinstance(value, str) for value in raw):
        fail("manifest assets must be a list of names")
    selected = set()
    for value in raw:
        canonical = "plugins" if value == "plugin" else value
        if canonical not in ASSET_ORDER:
            fail("unknown harness asset: %s" % value)
        selected.add(canonical)
    return [name for name in ASSET_ORDER if name in selected]


def migrate_plugins_directory(project):
    legacy = os.path.join(project, "plugin")
    plugins = os.path.join(project, "plugins")
    if not os.path.lexists(legacy):
        return
    if os.path.lexists(plugins):
        fail("both legacy plugin/ and plugins/ exist; merge them before setup")
    if os.path.islink(legacy) or not os.path.isdir(legacy):
        fail("legacy plugin/ must be a regular directory")
    os.rename(legacy, plugins)


def ensure_plugins_directory(project):
    directory = os.path.join(project, "plugins")
    if os.path.lexists(directory) and (os.path.islink(directory) or not os.path.isdir(directory)):
        fail("plugins/ must be a regular directory")
    os.makedirs(directory, exist_ok=True)
    if not os.listdir(directory):
        write_text(os.path.join(directory, ".gitkeep"), "")


def link_tree(source_root, destination_root, replace_regular=False):
    if not os.path.isdir(source_root):
        fail("harness asset root is absent: %s" % source_root)
    os.makedirs(destination_root, exist_ok=True)
    results = {"linked": 0, "exact": 0, "preserved": 0}
    ignored = set()
    for directory, dirnames, filenames in os.walk(source_root):
        dirnames[:] = sorted(name for name in dirnames if name != "__pycache__")
        relative = os.path.relpath(directory, source_root)
        destination_directory = destination_root if relative == "." else os.path.join(destination_root, relative)
        os.makedirs(destination_directory, exist_ok=True)
        for filename in sorted(filenames):
            if filename in (".DS_Store", ".gitignore", ".luaurc") or filename.endswith(".pyc"):
                continue
            source = os.path.join(directory, filename)
            destination = os.path.join(destination_directory, filename)
            state = relative_link(source, destination, replace_regular=replace_regular)
            results[state] += 1
            if state != "preserved":
                top = filename if relative == "." else relative.split(os.sep, 1)[0]
                ignored.add(top)
    update_ignore(destination_root, ignored)
    return results


def harness_hook_text():
    document = read_json(os.path.join(HARNESS, "openai", "hooks", "project.json"))
    hooks = document.get("hooks")
    if not isinstance(hooks, dict):
        fail("project hook source is malformed")
    for entries in hooks.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            for handler in entry.get("hooks", []) if isinstance(entry, dict) else []:
                if not isinstance(handler, dict):
                    continue
                command = handler.get("command")
                if isinstance(command, str):
                    handler["command"] = command.replace("/rblx-harness/openai/", "/openai/")
                command_windows = handler.get("commandWindows")
                if isinstance(command_windows, str):
                    handler["commandWindows"] = command_windows.replace(
                        "rblx-harness\\openai\\",
                        "openai\\",
                    )
    return json.dumps(document, indent=2) + "\n"


def copy_codex_support(project, harness_checkout=False):
    codex = os.path.join(project, ".codex")
    agents = os.path.join(codex, "agents")
    os.makedirs(agents, exist_ok=True)
    for filename in os.listdir(agents):
        if filename.endswith(".toml") and os.path.splitext(filename)[0] not in AGENTS:
            os.unlink(os.path.join(agents, filename))
    for name in AGENTS:
        shutil.copy2(
            os.path.join(HARNESS, "openai", "agents", name + ".toml"),
            os.path.join(agents, name + ".toml"),
        )
    hooks_path = os.path.join(codex, "hooks.json")
    if harness_checkout:
        write_text(hooks_path, harness_hook_text())
    else:
        shutil.copy2(os.path.join(HARNESS, "openai", "hooks", "project.json"), hooks_path)
    sys.path.insert(0, os.path.join(HARNESS, "shared", "gates"))
    import gatelib

    config_path = os.path.join(codex, "config.toml")
    try:
        with open(config_path, encoding="utf-8") as handle:
            existing = handle.read()
    except OSError:
        existing = ""
    with open(os.path.join(HARNESS, "openai", "config", "project.toml"), encoding="utf-8") as handle:
        canonical = handle.read()
    write_text(config_path, gatelib.merge_project_codex_config(existing, canonical))

    skills_root = os.path.join(project, ".agents", "skills")
    os.makedirs(skills_root, exist_ok=True)
    if not harness_checkout:
        remove_path(os.path.join(skills_root, "rblx-new-game"))
    skill_names = HARNESS_SKILLS if harness_checkout else PROJECT_SKILLS
    skill_source = os.path.join(HARNESS, "shared", "skills")
    for name in skill_names:
        relative_link(
            os.path.join(skill_source, name),
            os.path.join(skills_root, name),
            directory=True,
            replace_regular=True,
        )


def install_harness_support():
    copy_codex_support(HARNESS, harness_checkout=True)
    print("setup-harness|READY|agents=%s|skills=%s" % (
        ",".join(AGENTS),
        ",".join(HARNESS_SKILLS),
    ))


def render_templates(project, manifest):
    places = manifest.get("places") or []
    services = manifest.get("services") or "none"
    controllers = manifest.get("controllers") or "none"
    gameplay = manifest.get("gameplay") or "Not recorded."
    assets = manifest.get("assets") or []
    summary = "Gameplay loop: %s\n\nServices: %s\n\nControllers: %s" % (
        gameplay,
        services,
        controllers,
    )
    with open(os.path.join(HARNESS, "templates", "AGENTS.md"), encoding="utf-8") as handle:
        template = handle.read()
    rendered = (
        template.replace("{{SUMMARY}}", summary)
        .replace("{{PLACES}}", "\n".join("- " + place for place in places))
        .replace("{{ASSETS}}", ", ".join(assets) if assets else "none")
    )
    write_text(os.path.join(project, "AGENTS.md"), rendered)
    readme_path = os.path.join(project, "README.md")
    if not os.path.exists(readme_path):
        with open(os.path.join(HARNESS, "templates", "README.md"), encoding="utf-8") as handle:
            readme = handle.read()
        project_name = os.path.basename(project.rstrip(os.sep)) or "Roblox Project"
        write_text(
            readme_path,
            readme.replace("{{PROJECT}}", project_name).replace("{{GAMEPLAY}}", gameplay),
        )


def install(project, manifest):
    project = os.path.realpath(project)
    if not os.path.isdir(project):
        fail("project directory is absent: %s" % project)
    if not os.path.exists(os.path.join(project, "rblx-harness")):
        fail("project has no rblx-harness submodule")
    places = manifest.get("places")
    if not isinstance(places, list) or not places:
        fail("manifest has no places")
    migrate_plugins_directory(project)
    assets = normalize_assets(manifest)
    if os.path.isdir(os.path.join(project, "plugins")) and "plugins" not in assets:
        assets.append("plugins")
    assets = [name for name in ASSET_ORDER if name in set(assets)]
    manifest = dict(manifest)
    manifest["assets"] = assets
    update_local_ignore(project)
    ensure_marker(project)
    for place in places:
        os.makedirs(os.path.join(project, "places", place, "src", "ServerScriptService", "Services"), exist_ok=True)
        os.makedirs(
            os.path.join(project, "places", place, "src", "StarterPlayer", "StarterPlayerScripts", "Controllers"),
            exist_ok=True,
        )

    linked = {}
    if "packages" in assets:
        linked["packages"] = link_tree(
            os.path.join(project, "rblx-harness", "packages", "ReplicatedStorage", "Packages"),
            os.path.join(project, "shared", "src", "ReplicatedStorage", "Packages"),
            replace_regular=True,
        )
        linked["modules"] = link_tree(
            os.path.join(project, "rblx-harness", "packages", "ServerScriptService", "Modules"),
            os.path.join(project, "shared", "src", "ServerScriptService", "Modules"),
            replace_regular=True,
        )
    if "services" in assets:
        linked["services"] = link_tree(
            os.path.join(project, "rblx-harness", "packages", "ServerScriptService", "Services"),
            os.path.join(project, "shared", "src", "ServerScriptService", "Services"),
        )
    if "controllers" in assets:
        linked["controllers"] = link_tree(
            os.path.join(
                project,
                "rblx-harness",
                "packages",
                "StarterPlayer",
                "StarterPlayerScripts",
                "Controllers",
            ),
            os.path.join(project, "shared", "src", "StarterPlayer", "StarterPlayerScripts", "Controllers"),
        )
    if "plugins" in assets:
        ensure_plugins_directory(project)

    copy_codex_support(project)
    render_templates(project, manifest)
    print("setup-project|READY|places=%s|assets=%s" % (
        ",".join(places),
        ",".join(assets) if assets else "none",
    ))
    for category in sorted(linked):
        counts = linked[category]
        print("links|%s|linked=%d|exact=%d|preserved=%d" % (
            category,
            counts["linked"],
            counts["exact"],
            counts["preserved"],
        ))
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser()
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--project")
    target.add_argument("--harness", action="store_true")
    parser.add_argument("--manifest")
    parser.add_argument("--from-state", action="store_true")
    args = parser.parse_args(argv)
    if args.harness:
        if args.manifest or args.from_state:
            fail("--harness cannot be combined with project manifest options")
        install_harness_support()
        return 0
    project = os.path.realpath(args.project)
    manifest_path = args.manifest or os.path.join(project, MANIFEST)
    if not args.from_state and not args.manifest:
        fail("use --from-state or --manifest")
    manifest = install(project, read_json(manifest_path))
    if os.path.realpath(manifest_path) == os.path.realpath(os.path.join(project, MANIFEST)):
        write_json(manifest_path, manifest)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError) as error:
        sys.stderr.write("setup-project: ERROR %s\n" % error)
        sys.exit(2)
