#!/usr/bin/env python3
"""Install Codex support and link selected harness assets into a project."""

import argparse
import json
import os
import shutil
import sys


HARNESS = os.path.dirname(os.path.abspath(__file__))
AGENTS = ("researcher", "optimizer", "reviewer", "debugger")
PROJECT_SKILLS = ("rblx-writer", "rblx-debug", "rblx-optimize", "rblx-new-game")
MANIFEST = ".rblx-harness.json"
IGNORE_BEGIN = "# BEGIN rblx-harness links"
IGNORE_END = "# END rblx-harness links"


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


def remove_link(path):
    if os.path.islink(path):
        os.unlink(path)


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


def copy_codex_support(project):
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
    shutil.copy2(
        os.path.join(HARNESS, "openai", "hooks", "project.json"),
        os.path.join(codex, "hooks.json"),
    )
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
    for name in PROJECT_SKILLS:
        relative_link(
            os.path.join(project, "rblx-harness", "shared", "skills", name),
            os.path.join(skills_root, name),
            directory=True,
            replace_regular=True,
        )


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
    handoff = os.path.join(project, "HANDOFF.md")
    if not os.path.exists(handoff):
        shutil.copy2(os.path.join(HARNESS, "templates", "HANDOFF.md"), handoff)


def install(project, manifest):
    project = os.path.realpath(project)
    if not os.path.isdir(project):
        fail("project directory is absent: %s" % project)
    if not os.path.isfile(os.path.join(project, ".roblox")):
        fail("project has no .roblox marker")
    if not os.path.exists(os.path.join(project, "rblx-harness")):
        fail("project has no rblx-harness submodule")
    places = manifest.get("places")
    assets = set(manifest.get("assets") or [])
    if not isinstance(places, list) or not places:
        fail("manifest has no places")
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
    if "plugin" in assets or os.path.isdir(os.path.join(project, "plugin")):
        os.makedirs(os.path.join(project, "plugin"), exist_ok=True)
        marker = os.path.join(project, "plugin", ".gitkeep")
        if not os.path.exists(marker):
            open(marker, "a", encoding="utf-8").close()

    copy_codex_support(project)
    render_templates(project, manifest)
    print("setup-project|READY|places=%s|assets=%s" % (
        ",".join(places),
        ",".join(sorted(assets)) if assets else "none",
    ))
    for category in sorted(linked):
        counts = linked[category]
        print("links|%s|linked=%d|exact=%d|preserved=%d" % (
            category,
            counts["linked"],
            counts["exact"],
            counts["preserved"],
        ))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--manifest")
    parser.add_argument("--from-state", action="store_true")
    args = parser.parse_args(argv)
    project = os.path.realpath(args.project)
    manifest_path = args.manifest or os.path.join(project, MANIFEST)
    if not args.from_state and not args.manifest:
        fail("use --from-state or --manifest")
    install(project, read_json(manifest_path))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError) as error:
        sys.stderr.write("setup-project: ERROR %s\n" % error)
        sys.exit(2)
