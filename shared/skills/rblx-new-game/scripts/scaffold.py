#!/usr/bin/env python3
"""Inspect, record, and emit a multi-place Roblox project."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys


HERE = os.path.dirname(os.path.realpath(__file__))
SKILL_DIR = os.path.dirname(HERE)
LOCAL_HARNESS = os.path.dirname(os.path.dirname(os.path.dirname(SKILL_DIR)))
INTERVIEW_FILE = ".rblx-new-game.json"
MANIFEST_FILE = ".rblx-harness.json"
FIELDS = ("gameplay", "places", "services", "controllers", "assets", "harness")
COMPONENT = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
SOURCE_SUFFIXES = (".lua", ".luau")
SKIP_DIRS = {".git", "rblx-harness", ".agents", ".codex", "__pycache__"}

SERVICE_FRAME = """local m = {}

-- privates

-- functions
function m:Start()
end

-- events

return m
"""

CONTROLLER_FRAME = """local m = {}

-- privates

-- functions
function m:Start()
end

return m
"""

SERVER_ENTRY = """local ServerScriptService = game:GetService("ServerScriptService")

local roots = { ServerScriptService.Services }
local placeServices = ServerScriptService:FindFirstChild("PlaceServices")
if placeServices then
\ttable.insert(roots, placeServices)
end

for _, root in roots do
\tfor _, child in root:GetChildren() do
\t\tif child:IsA("ModuleScript") then
\t\t\tlocal service = require(child)
\t\t\tif type(service) == "table" and type(service.Start) == "function" then
\t\t\t\ttask.spawn(function()
\t\t\t\t\tservice:Start()
\t\t\t\tend)
\t\t\tend
\t\tend
\tend
end
"""

CLIENT_ENTRY = """local Players = game:GetService("Players")

local playerScripts = Players.LocalPlayer:WaitForChild("PlayerScripts")
local roots = { playerScripts.Controllers }
local placeControllers = playerScripts:FindFirstChild("PlaceControllers")
if placeControllers then
\ttable.insert(roots, placeControllers)
end

for _, root in roots do
\tfor _, child in root:GetChildren() do
\t\tif child:IsA("ModuleScript") then
\t\t\tlocal controller = require(child)
\t\t\tif type(controller) == "table" and type(controller.Start) == "function" then
\t\t\t\ttask.spawn(function()
\t\t\t\t\tcontroller:Start()
\t\t\t\tend)
\t\t\tend
\t\tend
\tend
end
"""


def state_path(root):
    return os.path.join(root, INTERVIEW_FILE)


def load_state(root):
    try:
        with open(state_path(root), encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def write_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def write_text(path, text, overwrite=True):
    if not overwrite and os.path.exists(path):
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return True


def clean_module_name(filename):
    name = filename
    for suffix in (".server.luau", ".client.luau", ".server.lua", ".client.lua", ".luau", ".lua"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return os.path.splitext(name)[0]


def scope_for(parts):
    folded = [part.casefold() for part in parts]
    if "places" in folded:
        index = folded.index("places")
        if index + 1 < len(parts):
            return parts[index + 1]
    return "shared"


def component_record(root, path, category, index):
    relative = os.path.relpath(path, root).replace(os.sep, "/")
    parts = relative.split("/")
    if index + 1 >= len(parts):
        return None
    item = parts[index + 1]
    name = clean_module_name(item)
    if not COMPONENT.fullmatch(name) or name.casefold() in ("tests", "placeservices", "placecontrollers"):
        return None
    item_path = os.path.join(root, *parts[: index + 2])
    if not os.path.exists(item_path):
        item_path = path
    return {
        "name": name,
        "scope": scope_for(parts),
        "path": os.path.relpath(item_path, root).replace(os.sep, "/"),
        "kind": "directory" if os.path.isdir(item_path) else "file",
        "category": category,
    }


def inspect_project(root):
    root = os.path.realpath(root)
    if not os.path.isdir(root):
        raise ValueError("project root is absent")
    places = set()
    places_dir = os.path.join(root, "places")
    if os.path.isdir(places_dir):
        places.update(
            name for name in os.listdir(places_dir)
            if COMPONENT.fullmatch(name) and os.path.isdir(os.path.join(places_dir, name))
        )
    for filename in os.listdir(root):
        if filename.endswith(".project.json") and filename != "default.project.json":
            name = filename[: -len(".project.json")]
            if COMPONENT.fullmatch(name):
                places.add(name)

    found = {"services": {}, "controllers": {}}
    source_count = 0
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(
            name for name in dirnames
            if name not in SKIP_DIRS and not os.path.islink(os.path.join(directory, name))
        )
        relative_directory = os.path.relpath(directory, root)
        parts = [] if relative_directory == "." else relative_directory.split(os.sep)
        folded = [part.casefold() for part in parts]
        category = None
        index = -1
        if "services" in folded:
            category = "services"
            index = len(folded) - 1 - folded[::-1].index("services")
        elif "controllers" in folded:
            category = "controllers"
            index = len(folded) - 1 - folded[::-1].index("controllers")
        for filename in sorted(filenames):
            if not filename.endswith(SOURCE_SUFFIXES):
                continue
            path = os.path.join(directory, filename)
            if os.path.islink(path):
                continue
            source_count += 1
            if category is None:
                continue
            record = component_record(root, path, category, index)
            if record:
                key = (record["scope"].casefold(), record["name"].casefold(), record["path"])
                found[category][key] = record
                if record["scope"] != "shared":
                    places.add(record["scope"])
    services = sorted(found["services"].values(), key=lambda item: (item["scope"].casefold(), item["name"].casefold(), item["path"]))
    controllers = sorted(found["controllers"].values(), key=lambda item: (item["scope"].casefold(), item["name"].casefold(), item["path"]))
    project_files = [name for name in os.listdir(root) if name.endswith(".project.json")]
    existing = bool(source_count or services or controllers or places or project_files)
    return {
        "root": root,
        "project": "existing" if existing else "new",
        "git": os.path.exists(os.path.join(root, ".git")),
        "harness": os.path.exists(os.path.join(root, "rblx-harness")),
        "plugin": os.path.isdir(os.path.join(root, "plugin")),
        "places": sorted(places, key=str.casefold),
        "services": services,
        "controllers": controllers,
    }


def place_names(text):
    names = [part.strip() for part in re.split(r"[,;\n]+", text) if part.strip()]
    if not names or any(not COMPONENT.fullmatch(name) for name in names):
        raise ValueError("places must be comma-separated safe names")
    if len({name.casefold() for name in names}) != len(names):
        raise ValueError("each place must be named once")
    return names


def scoped_components(text, places=None):
    if text.strip().casefold() == "none":
        return []
    records = []
    seen = set()
    place_lookup = {name.casefold(): name for name in (places or [])}
    for clause in (part.strip() for part in re.split(r"[;\n]+", text) if part.strip()):
        if ":" not in clause:
            raise ValueError("use 'shared: Name; Place: Name' or none")
        scope, raw = (part.strip() for part in clause.split(":", 1))
        if scope.casefold() == "shared":
            scope = "shared"
        elif place_lookup:
            if scope.casefold() not in place_lookup:
                raise ValueError("unknown place scope: %s" % scope)
            scope = place_lookup[scope.casefold()]
        elif not COMPONENT.fullmatch(scope):
            raise ValueError("invalid scope: %s" % scope)
        names = [name.strip() for name in raw.split(",") if name.strip()]
        if not names:
            raise ValueError("%s must name at least one module" % scope)
        for name in names:
            if not COMPONENT.fullmatch(name):
                raise ValueError("invalid module name: %s" % name)
            key = (scope.casefold(), name.casefold())
            if key in seen:
                raise ValueError("module is repeated: %s:%s" % (scope, name))
            seen.add(key)
            records.append({"scope": scope, "name": name})
    return records


def asset_names(text):
    normalized = " ".join(text.casefold().replace(",", " ").replace(";", " ").split())
    if normalized in ("all", "accept all", "yes all", "yes to all"):
        return ["packages", "services", "controllers", "plugin"]
    if normalized in ("none", "no"):
        return []
    aliases = {
        "package": "packages",
        "packages": "packages",
        "service": "services",
        "services": "services",
        "controller": "controllers",
        "controllers": "controllers",
        "plugin": "plugin",
        "plugins": "plugin",
        "support": None,
        "and": None,
    }
    assets = []
    for token in normalized.split():
        if token not in aliases:
            raise ValueError("unknown asset choice: %s" % token)
        value = aliases[token]
        if value and value not in assets:
            assets.append(value)
    return assets


def yes_no(text):
    value = text.strip().casefold()
    if value in ("yes", "y", "true", "use", "accept"):
        return True
    if value in ("no", "n", "false", "decline"):
        return False
    raise ValueError("harness answer must be Yes or No")


def validate_answer(field, text, state):
    text = text.strip()
    if not text:
        raise ValueError("%s answer is empty" % field)
    if field == "gameplay":
        return text
    if field == "places":
        return ", ".join(place_names(text))
    if field in ("services", "controllers"):
        places = place_names(state["places"]) if state.get("places") else None
        scoped_components(text, places)
        return text
    if field == "assets":
        return ", ".join(asset_names(text)) or "none"
    if field == "harness":
        return "yes" if yes_no(text) else "no"
    raise ValueError("unknown interview field: %s" % field)


def answer(root, field, text):
    root = os.path.realpath(root)
    if not os.path.isdir(root):
        raise ValueError("project root is absent")
    if field not in FIELDS:
        raise ValueError("field must be one of: %s" % ", ".join(FIELDS))
    state = load_state(root)
    state[field] = validate_answer(field, text, state)
    write_json(state_path(root), state)
    print("ANSWERED|%s|%s" % (field, state[field]))


def validate_state(state, plugin_exists=False):
    missing = [field for field in FIELDS if not isinstance(state.get(field), str) or not state[field].strip()]
    if missing:
        raise ValueError("missing interview answers: %s" % ", ".join(missing))
    places = place_names(state["places"])
    services = scoped_components(state["services"], places)
    controllers = scoped_components(state["controllers"], places)
    assets = asset_names(state["assets"])
    harness = yes_no(state["harness"])
    if plugin_exists and "plugin" not in assets:
        assets.append("plugin")
    if not harness and set(assets).intersection(("packages", "services", "controllers")):
        raise ValueError("harness packages, services, and controllers require rblx-harness")
    return places, services, controllers, assets, harness


def module_destination(root, category, scope, name):
    if category == "services":
        suffix = os.path.join("src", "ServerScriptService", "Services")
    else:
        suffix = os.path.join("src", "StarterPlayer", "StarterPlayerScripts", "Controllers")
    base = os.path.join(root, "shared", suffix) if scope == "shared" else os.path.join(root, "places", scope, suffix)
    return os.path.join(base, name + ".luau")


def snapshot_modules(root, inspection):
    snapshots = []
    for category in ("services", "controllers"):
        for record in inspection[category]:
            source = os.path.join(root, *record["path"].split("/"))
            if os.path.islink(source) or not os.path.exists(source):
                continue
            if os.path.isdir(source):
                files = {}
                for directory, dirnames, filenames in os.walk(source):
                    dirnames[:] = [name for name in dirnames if not os.path.islink(os.path.join(directory, name))]
                    for filename in filenames:
                        path = os.path.join(directory, filename)
                        if os.path.islink(path):
                            continue
                        with open(path, "rb") as handle:
                            files[os.path.relpath(path, source)] = handle.read()
                if files:
                    snapshots.append(dict(record, files=files))
            else:
                with open(source, "rb") as handle:
                    snapshots.append(dict(record, content=handle.read()))
    return snapshots


def restore_modules(root, snapshots, places):
    place_lookup = {place.casefold(): place for place in places}
    restored = []
    for record in snapshots:
        scope = "shared" if record["scope"].casefold() == "shared" else place_lookup.get(record["scope"].casefold())
        if not scope:
            continue
        flat = module_destination(root, record["category"], scope, record["name"])
        if "files" in record:
            if os.path.exists(flat) and not os.path.islink(flat):
                os.unlink(flat)
            destination = os.path.splitext(flat)[0]
            os.makedirs(destination, exist_ok=True)
            for relative, content in record["files"].items():
                path = os.path.join(destination, relative)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as handle:
                    handle.write(content)
        else:
            directory = os.path.splitext(flat)[0]
            if os.path.isdir(directory) and not os.path.islink(directory):
                shutil.rmtree(directory)
            os.makedirs(os.path.dirname(flat), exist_ok=True)
            with open(flat, "wb") as handle:
                handle.write(record["content"])
        restored.append("%s:%s:%s" % (record["category"], scope, record["name"]))
    return restored


def emit_module(root, category, record):
    destination = module_destination(root, category, record["scope"], record["name"])
    directory_form = os.path.splitext(destination)[0]
    if os.path.exists(destination) or os.path.isdir(directory_form):
        return
    frame = SERVICE_FRAME if category == "services" else CONTROLLER_FRAME
    write_text(destination, frame)


def project_document(project_name, place):
    tree = {
        "$className": "DataModel",
        "ReplicatedStorage": {"$path": "shared/src/ReplicatedStorage"},
        "ServerScriptService": {
            "$path": "shared/src/ServerScriptService",
            "PlaceServices": {"$path": "places/%s/src/ServerScriptService/Services" % place},
            "Tests": {"$path": "tests/%s/server" % place},
        },
        "StarterPlayer": {
            "StarterPlayerScripts": {
                "$path": "shared/src/StarterPlayer/StarterPlayerScripts",
                "PlaceControllers": {
                    "$path": "places/%s/src/StarterPlayer/StarterPlayerScripts/Controllers" % place
                },
                "Tests": {"$path": "tests/%s/client" % place},
            }
        },
    }
    return json.dumps({"name": "%s_%s" % (project_name.lower(), place.lower()), "tree": tree}, indent=2) + "\n"


def append_root_ignore(root):
    path = os.path.join(root, ".gitignore")
    begin = "# BEGIN rblx-new-game"
    end = "# END rblx-new-game"
    try:
        current = open(path, encoding="utf-8").read()
    except OSError:
        current = ""
    pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end) + r"\s*", re.DOTALL)
    retained = pattern.sub("", current).strip()
    managed = "%s\n%s\n.DS_Store\n%s" % (begin, INTERVIEW_FILE, end)
    write_text(path, "\n\n".join(part for part in (retained, managed) if part) + "\n")


def render_without_harness(root, state, places, assets):
    text = (
        "# Project\n\nGameplay loop: %s\n\nServices: %s\n\nControllers: %s\n\n"
        "## Places\n\n%s\n\n## Assets\n\n%s\n"
    ) % (
        state["gameplay"],
        state["services"],
        state["controllers"],
        "\n".join("- " + place for place in places),
        ", ".join(assets) if assets else "none",
    )
    write_text(os.path.join(root, "AGENTS.md"), text)
    write_text(os.path.join(root, "HANDOFF.md"), "goal:\nchanged:\nevidence:\nopen:\n", overwrite=False)


def emit(root):
    root = os.path.realpath(root)
    if not os.path.isdir(root):
        raise ValueError("project root is absent")
    state = load_state(root)
    plugin_exists = os.path.isdir(os.path.join(root, "plugin"))
    places, services, controllers, assets, harness = validate_state(state, plugin_exists)
    dependency = os.path.join(root, "rblx-harness")
    if harness and not os.path.isfile(os.path.join(dependency, "setup_project.py")):
        raise ValueError("rblx-harness submodule is absent; run dependency.py setup --yes")

    inspection = inspect_project(root)
    snapshots = snapshot_modules(root, inspection)
    project_name = os.path.basename(root.rstrip(os.sep)) or "game"
    append_root_ignore(root)
    for relative in (
        "shared/src/ReplicatedStorage",
        "shared/src/ServerScriptService/Services",
        "shared/src/ServerScriptService/Modules",
        "shared/src/StarterPlayer/StarterPlayerScripts/Controllers",
    ):
        os.makedirs(os.path.join(root, *relative.split("/")), exist_ok=True)
    for place in places:
        for relative in (
            "places/%s/src/ServerScriptService/Services" % place,
            "places/%s/src/StarterPlayer/StarterPlayerScripts/Controllers" % place,
            "tests/%s/server" % place,
            "tests/%s/client" % place,
        ):
            directory = os.path.join(root, *relative.split("/"))
            os.makedirs(directory, exist_ok=True)
            marker = os.path.join(directory, ".gitkeep")
            if not os.listdir(directory):
                open(marker, "a", encoding="utf-8").close()

    write_text(os.path.join(root, "shared", "src", "ServerScriptService", "Server.server.luau"), SERVER_ENTRY, overwrite=False)
    write_text(
        os.path.join(root, "shared", "src", "StarterPlayer", "StarterPlayerScripts", "Client.client.luau"),
        CLIENT_ENTRY,
        overwrite=False,
    )
    for record in services:
        emit_module(root, "services", record)
    for record in controllers:
        emit_module(root, "controllers", record)
    restored = restore_modules(root, snapshots, places)

    for index, place in enumerate(places):
        content = project_document(project_name, place)
        write_text(os.path.join(root, place + ".project.json"), content)
        if index == 0:
            write_text(os.path.join(root, "default.project.json"), content)
    if "plugin" in assets:
        os.makedirs(os.path.join(root, "plugin"), exist_ok=True)

    manifest = {
        "schema": 1,
        "gameplay": state["gameplay"],
        "places": places,
        "services": state["services"],
        "controllers": state["controllers"],
        "assets": assets,
        "harness": harness,
    }
    if harness:
        write_json(os.path.join(root, MANIFEST_FILE), manifest)
        result = subprocess.run(
            [sys.executable, os.path.join(dependency, "setup_project.py"), "--project", root, "--from-state"],
            cwd=root,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError("project integration failed")
    else:
        render_without_harness(root, state, places, assets)
    os.remove(state_path(root))
    print("EMITTED|%s|places=%s|assets=%s|preserved=%s" % (
        project_name,
        ",".join(places),
        ",".join(assets) if assets else "none",
        ",".join(restored) if restored else "none",
    ))


def status(root):
    state = load_state(os.path.realpath(root))
    missing = [field for field in FIELDS if not state.get(field)]
    print(json.dumps({"answers": state, "missing": missing}, indent=2, sort_keys=True))
    return 2 if missing else 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("inspect", "answer", "status", "emit"))
    parser.add_argument("field", nargs="?")
    parser.add_argument("text", nargs="*")
    parser.add_argument("--root", default=os.getcwd())
    args = parser.parse_args(argv)
    if args.command == "inspect":
        print(json.dumps(inspect_project(args.root), indent=2, sort_keys=True))
        return 0
    if args.command == "answer":
        if not args.field or not args.text:
            raise ValueError("answer requires <field> <text>")
        answer(args.root, args.field, " ".join(args.text))
        return 0
    if args.command == "status":
        return status(args.root)
    emit(args.root)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError) as error:
        sys.stderr.write("scaffold: ERROR %s\n" % error)
        sys.exit(2)
