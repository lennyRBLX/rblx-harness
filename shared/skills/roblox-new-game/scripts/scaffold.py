#!/usr/bin/env python3
"""roblox-new-game scaffolder — refuses to emit until the file-shaping
criteria are complete, and names the unanswered items so the skill re-asks
exactly those. The criteria file is consumed when the scaffold lands.

  scaffold.py answer <flag> <text> --root DIR     record an accepted answer
  scaffold.py status --root DIR                   answered / missing
  scaffold.py bootstrap --root DIR                create only the empty .roblox
                                                  managed-project sentinel
  scaffold.py emit --root DIR --name NAME
  scaffold.py relink --root DIR                   instructions + links + settings
  scaffold.py refresh-instructions --root DIR     refresh CLAUDE.md + AGENTS.md
  scaffold.py install-profile                     user Codex profile bootstrap
  scaffold.py backfill --shared DIR [--copy]      re-deliver the museum into
                                                  an existing project; --copy
                                                  is the Windows byte-copy path
"""

import hashlib
import json
import os
import re
import shutil
import sys


def resolve_harness(skill_dir, argv=None, cwd=None):
    """Find the checkout when this skill is linked or copied to user scope."""
    argv = list(sys.argv[1:] if argv is None else argv)
    cwd = os.path.realpath(os.getcwd() if cwd is None else cwd)
    candidates = [os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(skill_dir))))]
    try:
        root_index = argv.index("--root")
        project_root = os.path.realpath(argv[root_index + 1])
    except (ValueError, IndexError):
        project_root = ""
    if project_root:
        candidates.append(os.path.join(project_root, ".roblox-harness"))
    current = cwd
    while True:
        candidates.extend((current, os.path.join(current, ".roblox-harness")))
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    for candidate in candidates:
        root = os.path.realpath(candidate)
        if os.path.isfile(os.path.join(root, "shared", "gates", "gatelib.py")):
            return root
    raise RuntimeError("project-local .roblox-harness checkout could not be resolved")


SKILL_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
HARNESS = resolve_harness(SKILL_DIR)
PACKAGES = os.path.join(HARNESS, "packages")
MUSEUM_SKIP = {".DS_Store", "README.md", ".luaurc", ".gitignore"}
sys.path.insert(0, os.path.join(HARNESS, "shared", "gates"))
import gatelib  # noqa: E402
if (
    getattr(gatelib, "PROJECT_LOCAL_INSTALL_SCHEMA", 0) < 1
    or getattr(gatelib, "PROJECT_HARNESS_DIR", "") != ".roblox-harness"
    or not isinstance(getattr(gatelib, "HANDOFF_RELATIVE", None), str)
    or not callable(getattr(gatelib, "project_harness_root", None))
):
    raise RuntimeError(
        "project-local .roblox-harness is incompatible; update the dependency and retry setup"
    )
sys.path.insert(0, os.path.join(HARNESS, "tools", "create_boilerplate"))
import create_boilerplate  # noqa: E402

# museum canon that lives OUTSIDE the two fully-linked roots. Everything else
# under Services/ and Controllers/ is a project-owned byte-copy, but these are
# prescribed whole — the project supplies the handlers, never the driver — so
# they link back to the project's .roblox-harness checkout per file.
# The root itself stays project code: no nocheck .luaurc, and the generated
# .gitignore names only the linked file.
MUSEUM_ITEMS = ("ServerScriptService/Services/Effects.luau",)

# shared controllers that are a parent for children rather than a leaf: every
# place gets its own folder per root, grafted under the shared controller at
# client start. Argon cannot merge a declared child into a $path-mounted tree —
# it emits both and the duplicate wins nondeterministically — so the graft is
# a runtime reparent, not a project-file nesting.
PLACE_CHILD_ROOTS = ("Effects", "Gui", "Updates")

BLOCKING_SET = {
    "places": "1. initial place names",
    "services": "2. scoped keystone service modules",
    "controllers": "3. scoped keystone controller modules",
}

PRESCRIBED_COMPONENTS = {
    "services": {"effects", "payments", "playerdata", "updates"},
    "controllers": {"effects", "gui", "updates"},
}
PLACEHOLDER_PATTERNS = (
    r"\btbd\b",
    r"\btodo\b",
    r"\bunknown\b",
    r"\bundecided\b",
    r"\bunspecified\b",
    r"\bunassigned\b",
    r"\bnot sure\b",
    r"\bdecide later\b",
    r"\bask later\b",
    r"\bagent decides?\b",
    r"\b(?:ai|codex|claude) decides?\b",
    r"\bplaceholder\b",
    r"\bjunk\b",
    r"\blorem ipsum\b",
    r"\b(?:foo|bar|baz)\b",
    r"\bwhatever\b",
    r"\bsomething(?: here)?\b",
    r"\b(?:sample|example|test) answer\b",
    r"\bn/?a\b",
)
COMPONENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")


def scaffold_preflight(root):
    if not gatelib.is_roblox_project(root):
        print("REFUSED|.roblox sentinel absent|run dependency setup, then retry")
        return False
    sentinel = os.path.join(root, ".roblox")
    if os.path.islink(sentinel) or os.path.getsize(sentinel) != 0:
        print("REFUSED|.roblox sentinel invalid|replace it with an empty regular file, then retry")
        return False
    return True


def permission_preflight(root):
    if not scaffold_preflight(root):
        return False
    session_id = os.environ.get("CODEX_THREAD_ID", "")
    if not gatelib.session_authorized(root, session_id):
        print(gatelib.blocker_instruction("new-task", root))
        return False
    return True


def cmd_bootstrap(root):
    """Create only the empty managed-project marker before SessionStart.

    Interview state, project source, integration, and authorization remain
    untouched. The root must already exist so this exception cannot create an
    implicit project at an unintended path.
    """
    if not os.path.isdir(root):
        print("REFUSED|root absent|create the project directory explicitly, then rerun bootstrap")
        return 2
    sentinel = os.path.join(root, ".roblox")
    if os.path.lexists(sentinel):
        if os.path.islink(sentinel) or not os.path.isfile(sentinel):
            print("REFUSED|.roblox sentinel is not a regular file|replace it with an empty regular file")
            return 2
        if os.path.getsize(sentinel) != 0:
            print("REFUSED|.roblox sentinel is not empty|empty it explicitly, then rerun bootstrap")
            return 2
        state = "exact"
    else:
        descriptor = os.open(sentinel, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        os.close(descriptor)
        state = "created"
    if state == "exact":
        print("BOOTSTRAPPED|.roblox|exact; no integration or session change")
    else:
        print("BOOTSTRAPPED|.roblox|created; run relink and follow its discovery result")
    return 0

GITIGNORE = """.claude/agents/
.claude/skills/
.claude/settings.local.json
.codex/agents/
.agents/skills/
%s
gates/
.DS_Store
tests/**
!tests/**/
!tests/**/.gitkeep
""" % gatelib.HANDOFF_RELATIVE

SERVER_ENTRY = """local ServerScriptService = game:GetService("ServerScriptService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

-- the place file declares Events; this is the belt for a hand-built place.
-- FindFirstChild, not WaitForChild: a server script runs after the DataModel
-- is loaded, so an absent child here is absent for good [R WRIT29]
local Events = ReplicatedStorage:FindFirstChild("Events")
if not Events then
\tEvents = Instance.new("Folder")
\tEvents.Name = "Events"
\tEvents.Parent = ReplicatedStorage
end

local roots = { ServerScriptService.Services }
local placeServices = ServerScriptService:FindFirstChild("PlaceServices")
if placeServices then
\ttable.insert(roots, placeServices)
end

-- the Event package builds a service's remotes unnamed and unparented; this
-- is the half that names them and files them under
-- ReplicatedStorage.Events.<Service>, which is where the client's
-- Event(service, name) looks. Every service is required and wired before a
-- single Start runs: a Start may fire on its own event, and a client lookup
-- must never race a folder that is still being filled.
local services = {}
for _, root in roots do
\tfor _, child in root:GetChildren() do
\t\tif not child:IsA("ModuleScript") then
\t\t\tcontinue
\t\tend

\t\tlocal ok, service = pcall(require, child)
\t\tif not ok then
\t\t\twarn("Server | FAILED TO REQUIRE '" .. child.Name .. "':", service)
\t\t\tcontinue
\t\tend

\t\tif type(service) ~= "table" then
\t\t\tcontinue
\t\tend

\t\ttable.insert(services, { Name = child.Name, Module = service })

\t\tif type(service.Events) ~= "table" then
\t\t\tcontinue
\t\tend

\t\tlocal folder = Instance.new("Folder")
\t\tfolder.Name = child.Name

\t\tfor name, event in service.Events do
\t\t\tif typeof(event) == "Instance" then
\t\t\t\tevent.Name = name
\t\t\t\tevent.Parent = folder
\t\t\telseif type(event) == "table" then
\t\t\t\t-- a nested group is its own flat folder, "Service.Group", so the
\t\t\t\t-- client reads it with Event("Service.Group", name)
\t\t\t\tlocal container = Instance.new("Folder")
\t\t\t\tcontainer.Name = child.Name .. "." .. name

\t\t\t\tfor n, e in event do
\t\t\t\t\te.Name = n
\t\t\t\t\te.Parent = container
\t\t\t\tend

\t\t\t\tcontainer.Parent = Events
\t\t\tend
\t\tend

\t\tfolder.Parent = Events
\tend
end

require(ServerScriptService.Services.PlayerData):Start()

for _, service in services do
\tif service.Name ~= "PlayerData" and type(service.Module.Start) == "function" then
\t\ttask.spawn(function()
\t\t\tservice.Module:Start()
\t\tend)
\tend
end
"""

CLIENT_ENTRY = """local Players = game:GetService("Players")

local Player = Players.LocalPlayer

local scripts = Player.PlayerScripts
local controllers = scripts:WaitForChild("Controllers", 10)

-- place-owned children are grafted onto the shared controller they belong to
-- before anything is required, so each controller still reads its own
-- script:GetChildren() and never learns a place exists
local placeChildren = scripts:FindFirstChild("PlaceChildren")
if placeChildren and controllers then
\tfor _, folder in placeChildren:GetChildren() do
\t\tlocal target = controllers:FindFirstChild(folder.Name)
\t\tif not target then
\t\t\twarn("PlaceChildren | no shared controller named '" .. folder.Name .. "'")
\t\t\tcontinue
\t\tend

\t\tfor _, child in folder:GetChildren() do
\t\t\tchild.Parent = target
\t\tend
\tend
end

local roots = { controllers }
local placeControllers = scripts:FindFirstChild("PlaceControllers")
if placeControllers then
\ttable.insert(roots, placeControllers)
end

for _, root in roots do
\tif root then
\t\tfor _, child in root:GetChildren() do
\t\t\tif child:IsA("ModuleScript") then
\t\t\t\tlocal controller = require(child)
\t\t\t\tif type(controller) == "table" and type(controller.Start) == "function" then
\t\t\t\t\ttask.spawn(function()
\t\t\t\t\t\tcontroller:Start()
\t\t\t\t\tend)
\t\t\t\tend
\t\t\tend
\t\tend
\tend
end
"""


def criteria_path(root):
    return os.path.join(root, ".criteria.json")


def load_criteria(root):
    try:
        with open(criteria_path(root), encoding="utf-8") as f:
            criteria = json.load(f)
            return criteria if isinstance(criteria, dict) else {}
    except (OSError, ValueError):
        return {}


def placeholder_decision(text):
    low = " ".join(text.casefold().split())
    return not low or any(re.search(pattern, low) for pattern in PLACEHOLDER_PATTERNS)


def place_names(text):
    return [name.strip() for name in re.split(r"[,;\n]+", text) if name.strip()]


def scoped_components(text):
    """Parse ``shared: A, B; Place: C`` into ordered scope/name pairs."""
    if text.strip().casefold() == "none":
        return [], []
    parsed = []
    errors = []
    for clause in (item.strip() for item in re.split(r"[;\n]+", text) if item.strip()):
        if ":" not in clause:
            errors.append("use '<scope>: Name, Name' clauses, or 'none'")
            continue
        scope, raw_names = (part.strip() for part in clause.split(":", 1))
        names = [name.strip() for name in raw_names.split(",") if name.strip()]
        if not COMPONENT_RE.fullmatch(scope):
            errors.append("%s: scope must be one safe place name or shared" % (scope or "<empty>"))
        if not names:
            errors.append("%s: name at least one module" % (scope or "<empty>"))
        for name in names:
            if not COMPONENT_RE.fullmatch(name):
                errors.append("%s: module names use letters and digits and begin with a letter" % name)
        parsed.append((scope, names))
    scopes = [scope.casefold() for scope, _ in parsed]
    duplicates = sorted({scope for scope in scopes if scopes.count(scope) > 1})
    if duplicates:
        errors.append("name each scope once: %s" % ", ".join(duplicates))
    return parsed, errors


def validation_result(flag, text):
    """Return hard semantic errors and naming advisories for one answer."""
    errors = []
    warnings = []

    if placeholder_decision(text):
        return ["replace filler or placeholder text with an explicit project decision"], warnings

    if flag == "places":
        names = place_names(text)
        if not names:
            errors.append("name at least one initial place")
        for name in names:
            if not COMPONENT_RE.fullmatch(name):
                errors.append("%s: place names use letters and digits and begin with a letter" % name)
            elif name.casefold() in ("none", "shared"):
                errors.append("%s: reserved place name" % name)
        folded = [name.casefold() for name in names]
        duplicates = sorted({name for name in folded if folded.count(name) > 1})
        if duplicates:
            errors.append("name each place once: %s" % ", ".join(duplicates))
    elif flag in ("services", "controllers"):
        clauses, syntax_errors = scoped_components(text)
        errors.extend(syntax_errors)
        for scope, names in clauses:
            for name in names:
                if scope.casefold() == "shared" and name.casefold() in PRESCRIBED_COMPONENTS[flag]:
                    errors.append("%s: already ships as a prescribed %s" % (name, flag[:-1]))
                suffix = re.search(r"(?:Service|Controller)$", name, re.IGNORECASE)
                if suffix:
                    bare = name[: -len(suffix.group(0))] or "feature"
                    warnings.append("WRIT10|%s|prefer the bare feature noun %s" % (name, bare))
            folded = [name.casefold() for name in names]
            duplicates = sorted({name for name in folded if folded.count(name) > 1})
            if duplicates:
                errors.append("%s: name each module once: %s" % (scope, ", ".join(duplicates)))
    return errors, warnings


def criteria_validation(criteria):
    invalid = {}
    warnings = []
    for flag in BLOCKING_SET:
        text = criteria.get(flag, "")
        if not isinstance(text, str) or not text.strip():
            continue
        errors, answer_warnings = validation_result(flag, text.strip())
        if errors:
            invalid[flag] = errors
        warnings.extend((flag, warning) for warning in answer_warnings)
    places = {name.casefold(): name for name in place_names(criteria.get("places", ""))}
    if places:
        for flag in ("services", "controllers"):
            clauses, _ = scoped_components(criteria.get(flag, ""))
            unknown = sorted(
                {scope for scope, _ in clauses if scope.casefold() != "shared" and scope.casefold() not in places}
            )
            if unknown:
                invalid.setdefault(flag, []).append("unknown place scope: %s" % ", ".join(unknown))
    return invalid, warnings


def cmd_answer(root, flag, text):
    if not scaffold_preflight(root):
        return 2
    if flag not in BLOCKING_SET:
        print("REFUSED|%s|not a blocking-set flag" % flag)
        return 2
    text = text.strip()
    if not text:
        print("REFUSED|%s|empty answer" % flag)
        return 2
    errors, warnings = validation_result(flag, text)
    if errors:
        for error in errors:
            print("REFUSED|%s|%s" % (flag, error))
        return 2
    criteria = load_criteria(root)
    criteria[flag] = text
    combined_invalid, _ = criteria_validation(criteria)
    if flag in combined_invalid:
        for error in combined_invalid[flag]:
            if error not in errors:
                print("REFUSED|%s|%s" % (flag, error))
        return 2
    for warning in warnings:
        print("ADVISORY|%s|%s" % (flag, warning))
    os.makedirs(root, exist_ok=True)
    with open(criteria_path(root), "w", encoding="utf-8") as f:
        json.dump(criteria, f, indent=1)
    print("ACCEPTED|%s" % flag)
    return 0


def cmd_status(root):
    criteria = load_criteria(root)
    invalid, warnings = criteria_validation(criteria)
    missing = []
    for flag in BLOCKING_SET:
        answer = criteria.get(flag, "")
        if not isinstance(answer, str) or not answer.strip():
            state = "missing"
            missing.append(flag)
        elif flag in invalid:
            state = "invalid|" + "; ".join(invalid[flag])
        else:
            state = "answered"
        print("%s|%s" % (flag, state))
    for flag, warning in warnings:
        print("ADVISORY|%s|%s" % (flag, warning))
    return 0 if not missing and not invalid else 1


def parse_places(criteria):
    """Initial place names from the validated places answer."""
    return place_names(criteria.get("places", ""))


def architecture_summary(criteria):
    services = " ".join(criteria["services"].split())
    controllers = " ".join(criteria["controllers"].split())
    return "Keystone services: %s. Keystone controllers: %s." % (services, controllers)


def emit_keystones(root, criteria, places):
    """Create the confirmed module files through the canonical emitter."""
    place_lookup = {place.casefold(): place for place in places}
    for flag, kind in (("services", "service"), ("controllers", "controller")):
        clauses, _ = scoped_components(criteria[flag])
        for scope, names in clauses:
            place = None if scope.casefold() == "shared" else place_lookup[scope.casefold()]
            for name in names:
                argv = [kind, name, "--root", root]
                if place:
                    argv.extend(("--place", place))
                if create_boilerplate.main(argv) != 0:
                    return False
    return True


def place_project(project_name, place):
    """One Argon project per place: shared core mounted whole, the place's own
    dirs as PlaceServices/PlaceControllers, tests mounted at
    ServerScriptService/Tests and StarterPlayerScripts/Tests."""
    return (
        json.dumps(
            {
                "name": "%s_%s" % (project_name.lower(), place.lower()),
                "tree": {
                    "$className": "DataModel",
                    "ReplicatedStorage": {
                        "$path": "shared/src/ReplicatedStorage",
                        "Events": {"$className": "Folder"},
                    },
                    "ServerScriptService": {
                        "$path": "shared/src/ServerScriptService",
                        "PlaceServices": {"$path": "places/%s/src/ServerScriptService/Services" % place},
                        "Tests": {"$path": "tests/%s/server" % place},
                    },
                    "ServerStorage": {
                        "$path": "shared/src/ServerStorage",
                        "Plugins": {"$path": "plugins"},
                    },
                    "StarterPlayer": {
                        "StarterPlayerScripts": {
                            "$path": "shared/src/StarterPlayer/StarterPlayerScripts",
                            "PlaceControllers": {
                                "$path": "places/%s/src/StarterPlayer/StarterPlayerScripts/Controllers" % place
                            },
                            "PlaceChildren": dict(
                                {"$className": "Folder"},
                                **{
                                    root: {
                                        "$path": "places/%s/src/StarterPlayer/StarterPlayerScripts/%s" % (place, root)
                                    }
                                    for root in PLACE_CHILD_ROOTS
                                }
                            ),
                            "Tests": {"$path": "tests/%s/client" % place},
                        },
                    },
                },
            },
            indent=2,
        )
        + "\n"
    )


def emit_museum_links(shared, copy=False):
    """Per-file, never per-directory — Argon follows file symlinks and drops
    directory symlinks. Relative, never absolute. Directory packages are
    recreated as real dirs with every file
    linked. The generated .gitignore inside each root names exactly the
    museum files, so no symlink is ever committed and Windows has nothing to
    materialize."""
    emitted = {"ReplicatedStorage/Packages": [], "ServerScriptService/Modules": []}
    for rel_root in emitted:
        src_root = os.path.join(PACKAGES, rel_root)
        dst_root = os.path.join(shared, "src", rel_root)
        os.makedirs(dst_root, exist_ok=True)
        if not os.path.isdir(src_root):
            print("WARN|museum root absent: %s - build step 10 supplies it" % src_root)
            continue
        for dirpath, dirnames, filenames in os.walk(src_root):
            rel_dir = os.path.relpath(dirpath, src_root)
            for fn in sorted(filenames):
                if fn in MUSEUM_SKIP:
                    continue
                src = os.path.join(dirpath, fn)
                dst_dir = os.path.join(dst_root, rel_dir) if rel_dir != "." else dst_root
                os.makedirs(dst_dir, exist_ok=True)
                dst = os.path.join(dst_dir, fn)
                if os.path.islink(dst) or os.path.exists(dst):
                    os.unlink(dst)  # a stale byte-copy yields to the link
                if copy:
                    shutil.copyfile(src, dst)
                else:
                    os.symlink(os.path.relpath(src, dst_dir), dst)
                top = rel_dir.split(os.sep)[0] if rel_dir != "." else fn
                if top not in emitted[rel_root]:
                    emitted[rel_root].append(top)
        with open(os.path.join(dst_root, ".luaurc"), "w", encoding="utf-8") as f:
            f.write('{\n\t"languageMode": "nocheck"\n}\n')
        with open(os.path.join(dst_root, ".gitignore"), "w", encoding="utf-8") as f:
            f.write("# museum files - delivered by symlink from .roblox-harness/, never committed\n")
            for name in sorted(emitted[rel_root]):
                f.write(name + "\n")
    return emitted


def emit_museum_items(shared, copy=False):
    """The MUSEUM_ITEMS half of the delivery: per-file links for canon that
    sits inside an otherwise project-owned root. Runs before emit_prescribed
    so a stale byte-copy yields to the link, exactly as the linked roots do.
    Each root gets a .gitignore naming only its linked files — the project's
    own services next to them stay committed."""
    ignores = {}
    for rel in MUSEUM_ITEMS:
        rel_dir, fn = os.path.split(rel)
        src = os.path.join(PACKAGES, rel)
        if not os.path.exists(src):
            print("WARN|museum item absent: %s - build step 10 supplies it" % src)
            continue
        dst_dir = os.path.join(shared, "src", rel_dir)
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(dst_dir, fn)
        if os.path.islink(dst) or os.path.exists(dst):
            os.unlink(dst)  # a stale byte-copy yields to the link
        if copy:
            shutil.copyfile(src, dst)
        else:
            os.symlink(os.path.relpath(src, os.path.realpath(dst_dir)), dst)
        ignores.setdefault(dst_dir, []).append(fn)
    for dst_dir, names in ignores.items():
        with open(os.path.join(dst_dir, ".gitignore"), "w", encoding="utf-8") as f:
            f.write("# museum files - delivered by symlink from .roblox-harness/, never committed\n")
            for name in sorted(names):
                f.write(name + "\n")
    return ignores


def emit_prescribed(shared):
    """Everything outside the linked roots is a byte-copy at scaffold time:
    PlayerData/Payments/Updates and the Controllers are project-owned and
    edited per project. MUSEUM_ITEMS are the exception and belong to
    emit_museum_items."""
    for rel in ("ServerScriptService/Services", "StarterPlayer/StarterPlayerScripts/Controllers"):
        src_root = os.path.join(PACKAGES, rel)
        dst_root = os.path.join(shared, "src", rel)
        os.makedirs(dst_root, exist_ok=True)
        if not os.path.isdir(src_root):
            continue
        for dirpath, dirnames, filenames in os.walk(src_root):
            rel_dir = os.path.relpath(dirpath, src_root)
            for fn in sorted(filenames):
                if fn in MUSEUM_SKIP:
                    continue
                item = "/".join([rel] + ([] if rel_dir == "." else rel_dir.split(os.sep)) + [fn])
                if item in MUSEUM_ITEMS:
                    continue
                dst_dir = os.path.join(dst_root, rel_dir) if rel_dir != "." else dst_root
                os.makedirs(dst_dir, exist_ok=True)
                dst = os.path.join(dst_dir, fn)
                if not os.path.exists(dst):
                    shutil.copyfile(os.path.join(dirpath, fn), dst)


def project_harness(root):
    candidate = gatelib.project_harness_root(root)
    return candidate if candidate and os.path.realpath(candidate) == os.path.realpath(HARNESS) else ""


def require_project_harness(root):
    if project_harness(root):
        return True
    print("REFUSED|project harness absent|initialize the .roblox-harness submodule")
    return False


def write_if_changed(path, content):
    try:
        with open(path, encoding="utf-8") as handle:
            if handle.read() == content:
                return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return True


def discovery_relatives(host="all"):
    codex = [
        "AGENTS.md",
        ".codex/config.toml",
        ".codex/hooks.json",
        ".agents/skills/roblox-writer/SKILL.md",
        ".agents/skills/roblox-writer/agents/openai.yaml",
    ]
    claude = [
        "CLAUDE.md",
        ".claude/settings.json",
        ".claude/skills/roblox-writer/SKILL.md",
    ]
    for name in ("reviewer", "debugger", "optimizer", "researcher", "maintainer"):
        codex.append(".codex/agents/%s.toml" % name)
        claude.append(".claude/agents/%s.md" % name)
    if host == "codex":
        return codex
    if host == "claude":
        return claude
    return codex + claude


def discovery_snapshot(root, host="all"):
    """Fingerprint only files whose changed bytes require host rediscovery."""
    snapshot = {}
    for relative in discovery_relatives(host):
        path = os.path.join(root, relative)
        if os.path.islink(path):
            link = os.readlink(path)
            try:
                with open(path, "rb") as source:
                    digest = hashlib.sha256(source.read()).hexdigest()
            except OSError:
                snapshot[relative] = ("broken-link", link, "")
            else:
                snapshot[relative] = ("link", link, digest)
        elif os.path.isfile(path):
            try:
                with open(path, "rb") as source:
                    digest = hashlib.sha256(source.read()).hexdigest()
            except OSError:
                snapshot[relative] = ("unreadable", "")
            else:
                snapshot[relative] = ("file", digest)
        elif os.path.isdir(path):
            snapshot[relative] = ("directory", "")
        else:
            snapshot[relative] = ("missing", "")
    return snapshot


def discovery_baseline_path(root, host="all"):
    key = hashlib.sha256(os.path.realpath(root).encode("utf-8")).hexdigest()[:20]
    suffix = "" if host == "all" else "-" + host
    return os.path.join(gatelib.CACHE, "discovery", key + suffix + ".json")


def read_discovery_baseline(root, host="all"):
    try:
        with open(discovery_baseline_path(root, host), encoding="utf-8") as handle:
            snapshot = json.load(handle)
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return {}
    return snapshot if isinstance(snapshot, dict) else {}


def normalized_discovery_snapshot(snapshot):
    return json.loads(json.dumps(snapshot, sort_keys=True))


def hook_discovery_snapshot(root, host="all"):
    """Capture only hook definitions, excluding adjacent settings/config."""
    snapshot = {}
    relatives = {
        "codex": (".codex/hooks.json",),
        "claude": (".claude/settings.json",),
        "all": (".codex/hooks.json", ".claude/settings.json"),
    }.get(host, ())
    for relative in relatives:
        path = os.path.join(root, relative)
        try:
            with open(path, encoding="utf-8") as handle:
                document = json.load(handle)
            hooks = document.get("hooks")
            if not isinstance(hooks, dict):
                raise ValueError("hooks table absent")
        except (OSError, ValueError):
            snapshot[relative] = None
        else:
            snapshot[relative] = hooks
    return snapshot


def write_discovery_baseline(root, snapshot, host="all"):
    """Persist the loaded referent bytes so later harness updates are visible."""
    path = discovery_baseline_path(root, host)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rendered = json.dumps(
        normalized_discovery_snapshot(snapshot),
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"
    try:
        with open(path, encoding="utf-8") as existing:
            if existing.read() == rendered:
                return False
    except OSError:
        pass
    temporary = path + ".%d.tmp" % os.getpid()
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(rendered)
    os.replace(temporary, path)
    return True


def discovery_status(status, discovery_changed, profile_changed=False, hooks_changed=False, host="codex"):
    if not discovery_changed:
        return status + "|discovery exact; no new task required."
    actions = []
    if profile_changed:
        actions.append("Select Roblox")
    if hooks_changed:
        actions.append("review changed hooks and approve them once with /hooks")
    if not actions:
        actions.append("Retry host discovery")
    return status + "|" + "; ".join(actions) + "; continue the current task after revalidation."


def ensure_managed_directory(path):
    """Repair a generated directory without disturbing valid child entries."""
    if os.path.islink(path) or (os.path.lexists(path) and not os.path.isdir(path)):
        os.unlink(path)
    os.makedirs(path, exist_ok=True)


def replace_managed_file(source, destination):
    """Install one regular discovery file even when its old shape is damaged."""
    try:
        if not os.path.islink(destination) and os.path.isfile(destination):
            with open(source, "rb") as source_file, open(destination, "rb") as destination_file:
                if source_file.read() == destination_file.read():
                    return False
    except OSError:
        pass
    if os.path.islink(destination) or os.path.isfile(destination):
        os.unlink(destination)
    elif os.path.isdir(destination):
        shutil.rmtree(destination)
    temporary = destination + ".relink.tmp"
    if os.path.lexists(temporary):
        if os.path.isdir(temporary) and not os.path.islink(temporary):
            shutil.rmtree(temporary)
        else:
            os.unlink(temporary)
    shutil.copyfile(source, temporary)
    os.chmod(temporary, os.stat(source).st_mode & 0o777)
    os.replace(temporary, destination)
    return True


def remove_managed_entry(path):
    if os.path.islink(path):
        os.unlink(path)
        return
    if not os.path.lexists(path):
        return
    if os.path.isdir(path):
        # A Windows junction is not consistently reported by islink().
        if os.name == "nt" and os.path.normcase(os.path.realpath(path)) != os.path.normcase(os.path.abspath(path)):
            os.rmdir(path)
        else:
            shutil.rmtree(path)
        return
    os.unlink(path)


def materialized_runtime():
    return os.name == "nt"


def deliver_managed_source(source, destination, directory=False, materialize=None):
    """Deliver a symlink on authoring hosts and regular bytes on Windows."""
    materialize = materialized_runtime() if materialize is None else bool(materialize)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    if materialize and not directory:
        return replace_managed_file(source, destination)
    remove_managed_entry(destination)
    if materialize:
        shutil.copytree(source, destination)
    else:
        os.symlink(os.path.relpath(source, os.path.realpath(os.path.dirname(destination))), destination)
    return True


def project_files(root):
    return sorted(
        name
        for name in os.listdir(root)
        if name.endswith(".project.json") and name != "default.project.json" and os.path.isfile(os.path.join(root, name))
    )


def default_project_source(root):
    """Resolve the existing selection, then use a stable first-file fallback."""
    candidates = project_files(root)
    if not candidates:
        return ""
    default = os.path.join(root, "default.project.json")
    if os.path.islink(default):
        target = os.path.basename(os.readlink(default))
        if target in candidates:
            return target
    try:
        with open(default, "rb") as handle:
            raw = handle.read()
    except OSError:
        raw = b""
    placeholder = raw.decode("utf-8", "ignore").strip()
    if placeholder in candidates:
        return placeholder
    if raw:
        try:
            default_name = json.loads(raw.decode("utf-8")).get("name")
        except (AttributeError, UnicodeError, ValueError):
            default_name = None
        for candidate in candidates:
            path = os.path.join(root, candidate)
            try:
                with open(path, "rb") as handle:
                    candidate_raw = handle.read()
                candidate_name = json.loads(candidate_raw.decode("utf-8")).get("name")
            except (AttributeError, OSError, UnicodeError, ValueError):
                continue
            if candidate_raw == raw or (default_name and candidate_name == default_name):
                return candidate
    return candidates[0]


def materialize_default_project(root, preferred=""):
    candidates = project_files(root)
    selected = preferred if preferred in candidates else default_project_source(root)
    if not selected:
        print("REFUSED|project files absent|restore at least one .project.json file")
        return 2
    destination = os.path.join(root, "default.project.json")
    remove_managed_entry(destination)
    shutil.copyfile(os.path.join(root, selected), destination)
    print("default-project|%s" % selected)
    return 0


def emit_default_project(root, place, materialize=None):
    """Select the first interview place with a link or Windows-safe bytes."""
    materialize = materialized_runtime() if materialize is None else bool(materialize)
    source_name = "%s.project.json" % place
    source = os.path.join(root, source_name)
    destination = os.path.join(root, "default.project.json")
    remove_managed_entry(destination)
    if materialize:
        shutil.copyfile(source, destination)
    else:
        os.symlink(source_name, destination)
    return destination


def instruction_context(text):
    """Read the project-owned summary and place map from a managed file."""
    match = re.search(
        r"(?ms)^## summary\s*\n+(.*?)\n+## places\s*\n+(.*?)\s*\Z",
        text,
    )
    if not match:
        return None
    summary = match.group(1).strip()
    places = tuple(line.strip() for line in match.group(2).splitlines() if line.strip())
    if not summary or not places or any(not re.fullmatch(r"[^|\n]+\|[0-9]+", line) for line in places):
        return None
    return summary, places


def write_instruction_files(root, summary, places):
    places_block = "\n".join(places)
    for template_path, destination in (
        (os.path.join("claude", "CLAUDE.template.md"), os.path.join(root, "CLAUDE.md")),
        (os.path.join("openai", "AGENTS.template.md"), os.path.join(root, "AGENTS.md")),
    ):
        with open(os.path.join(HARNESS, template_path), encoding="utf-8") as source:
            rendered = source.read()
        rendered = rendered.replace("{{SUMMARY}}", summary).replace("{{PLACES}}", places_block)
        with open(destination, "w", encoding="utf-8") as output:
            output.write(rendered)


def refresh_instruction_files(root, announce=True):
    """Refresh both runtime files without changing project-specific fields."""
    contexts = []
    for name in ("CLAUDE.md", "AGENTS.md"):
        path = os.path.join(root, name)
        try:
            with open(path, encoding="utf-8") as source:
                context = instruction_context(source.read())
        except OSError:
            continue
        if context is None:
            print("REFUSED|%s malformed|summary and places could not be preserved" % name)
            return 2
        contexts.append((name, context))
    if not contexts:
        return 0
    canonical = contexts[0][1]
    if any(context != canonical for _, context in contexts[1:]):
        print("REFUSED|instruction files disagree|reconcile summary and places before relink")
        return 2
    write_instruction_files(root, canonical[0], canonical[1])
    if announce:
        print("instructions-refreshed|CLAUDE.md,AGENTS.md")
    return 0


def emit_codex(root):
    """Install Codex hooks, native agent TOMLs, fast-mode configuration, and
    the writer skill. Agent files are copied without translating Claude
    frontmatter; each runtime keeps its own canonical definition."""
    codex_dir = os.path.join(root, ".codex")
    agents_dir = os.path.join(codex_dir, "agents")
    ensure_managed_directory(codex_dir)
    ensure_managed_directory(agents_dir)
    with open(os.path.join(HARNESS, "openai", "hooks", "project.json"), encoding="utf-8") as f:
        hooks = f.read()
    write_if_changed(os.path.join(codex_dir, "hooks.json"), hooks)
    config_path = os.path.join(codex_dir, "config.toml")
    try:
        with open(config_path, encoding="utf-8") as existing_file:
            existing_config = existing_file.read()
    except FileNotFoundError:
        existing_config = ""
    with open(os.path.join(HARNESS, "openai", "config", "project.toml"), encoding="utf-8") as source:
        merged_config = gatelib.merge_project_codex_config(existing_config, source.read())
    write_if_changed(config_path, merged_config)
    codex_skills = os.path.join(root, ".agents", "skills")
    os.makedirs(codex_skills, exist_ok=True)
    writer_dst = os.path.join(codex_skills, "roblox-writer")
    remove_managed_entry(writer_dst)
    os.makedirs(os.path.join(writer_dst, "agents"), exist_ok=True)
    shared_skill = os.path.join(HARNESS, "shared", "skills", "roblox-writer", "SKILL.md")
    metadata = os.path.join(HARNESS, "openai", "skills", "roblox-writer", "agents", "openai.yaml")
    deliver_managed_source(shared_skill, os.path.join(writer_dst, "SKILL.md"))
    deliver_managed_source(metadata, os.path.join(writer_dst, "agents", "openai.yaml"))
    for name in gatelib.REQUIRED_CODEX_AGENTS:
        src = os.path.join(HARNESS, "openai", "agents", name + ".toml")
        dst = os.path.join(agents_dir, name + ".toml")
        replace_managed_file(src, dst)
    agents_ok, agents_detail = gatelib.required_codex_agents_status(root)
    if not agents_ok:
        raise RuntimeError(agents_detail)


def remove_legacy_git_history(root):
    """Remove only generated GitHistory artifacts from the retired protocol."""
    gitignore = os.path.join(root, ".gitignore")
    try:
        with open(gitignore, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        lines = None
    if lines is not None:
        kept = [line for line in lines if line.strip() != "shared/src/ServerStorage/GitHistory/"]
        if kept != lines:
            with open(gitignore, "w", encoding="utf-8") as f:
                f.writelines(kept)

    directory = os.path.join(root, "shared", "src", "ServerStorage", "GitHistory")
    try:
        names = os.listdir(directory)
    except OSError:
        return
    generated = re.compile(r"^Remote_[0-9a-f]{16}_[0-9a-f]{40}\.luau$")
    for name in names:
        if name in (".gitignore", ".owner") or generated.fullmatch(name):
            try:
                os.remove(os.path.join(directory, name))
            except OSError:
                pass
    try:
        os.rmdir(directory)
    except OSError:
        pass


def relink(root, host="all"):
    """Re-creates, never re-scaffolds: the link set and the settings block are
    gitignored and owned by this scaffolder, so rebuilding them from
    .roblox-harness's canonical form is deterministic. This is the bootstrap path:
    it can install static configuration and hooks, but it never creates live
    session authorization."""
    if not gatelib.is_roblox_project(root):
        print("REFUSED|.roblox sentinel absent|this project is not harness-managed")
        return 2
    if not require_project_harness(root):
        return 2
    discovery_before = discovery_snapshot(root, host)
    hooks_before = hook_discovery_snapshot(root, host)
    discovery_baseline = read_discovery_baseline(root, host)
    if refresh_instruction_files(root, announce=False) != 0:
        return 2
    remove_legacy_git_history(root)
    profile_ok, _ = gatelib.permissions_harness()
    profile_changed = False
    if not profile_ok:
        installed, detail, profile_changed = gatelib.install_permissions_harness()
        if not installed:
            print(gatelib.permissions_harness_block("profile installation failed: %s" % detail))
            return 2
    agents_dir = os.path.join(root, ".claude", "agents")
    skills_dir = os.path.join(root, ".claude", "skills")
    os.makedirs(agents_dir, exist_ok=True)
    os.makedirs(skills_dir, exist_ok=True)
    for name in ("reviewer", "debugger", "optimizer", "researcher", "maintainer"):
        src = os.path.join(HARNESS, "claude", "agents", name + ".md")
        dst = os.path.join(agents_dir, name + ".md")
        deliver_managed_source(src, dst)
    writer_dst = os.path.join(skills_dir, "roblox-writer")
    deliver_managed_source(
        os.path.join(HARNESS, "shared", "skills", "roblox-writer"),
        writer_dst,
        directory=True,
    )

    with open(os.path.join(HARNESS, "claude", "settings", "project.json"), encoding="utf-8") as f:
        canonical = json.load(f)
    canonical.pop("__doc", None)
    settings_path = os.path.join(root, ".claude", "settings.json")
    existing = {}
    if os.path.exists(settings_path):
        try:
            with open(settings_path, encoding="utf-8") as f:
                existing = json.load(f)
        except (OSError, ValueError):
            existing = {}
    existing.update(canonical)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=1)
        f.write("\n")
    emit_codex(root)
    discovery_after = discovery_snapshot(root, host)
    historical_discovery_changed = (
        discovery_baseline is not None
        and discovery_baseline != normalized_discovery_snapshot(discovery_after)
    )
    project_hooks_changed = hooks_before != hook_discovery_snapshot(root, host)
    codex_discovery = host in ("all", "codex")
    discovery_changed = (
        (codex_discovery and profile_changed)
        or historical_discovery_changed
        or discovery_before != discovery_after
    )
    try:
        write_discovery_baseline(root, discovery_after, host)
    except OSError as error:
        print("Fix discovery cache write: %s → rerun relink." % str(error)[:160])
        return 2
    print("relinked|instructions, agents, roblox-writer, settings hook block, codex hooks + agents")
    status = "permissions-harness|%s|project-hooks=%s" % (
        "installed" if profile_changed else "exact",
        "installed" if project_hooks_changed else "exact",
    )
    print(
        discovery_status(
            status,
            discovery_changed,
            profile_changed=codex_discovery and profile_changed,
            hooks_changed=project_hooks_changed,
            host=host,
        )
    )
    return 0


def cmd_emit(root, name):
    if not scaffold_preflight(root):
        return 2
    if not require_project_harness(root):
        return 2
    criteria = load_criteria(root)
    missing = [
        question
        for flag, question in BLOCKING_SET.items()
        if not isinstance(criteria.get(flag), str) or not criteria[flag].strip()
    ]
    invalid, warnings = criteria_validation(criteria)
    if missing:
        print("REFUSED - the blocking set is not answered:")
        for q in missing:
            print("missing|%s" % q)
    if invalid:
        print("REFUSED - blocking answers are invalid:")
        for flag in BLOCKING_SET:
            for error in invalid.get(flag, ()):
                print("invalid|%s|%s" % (flag, error))
    if missing or invalid:
        return 2
    for flag, warning in warnings:
        print("ADVISORY|%s|%s" % (flag, warning))

    summary = architecture_summary(criteria)
    places = parse_places(criteria)

    shared = os.path.join(root, "shared")
    for rel in (
        "shared/src/ReplicatedStorage/Types",
        "shared/src/ReplicatedStorage/Data",
        "shared/src/ServerScriptService/Services",
        "shared/src/ServerScriptService/Modules",
        "shared/src/ServerStorage",
        "shared/src/StarterPlayer/StarterPlayerScripts/Controllers",
    ):
        os.makedirs(os.path.join(root, rel), exist_ok=True)
    for place in places:
        for rel in (
            "places/%s/src/ServerScriptService/Services" % place,
            "places/%s/src/StarterPlayer/StarterPlayerScripts/Controllers" % place,
            "tests/%s/server" % place,
            "tests/%s/client" % place,
        ) + tuple(
            "places/%s/src/StarterPlayer/StarterPlayerScripts/%s" % (place, root) for root in PLACE_CHILD_ROOTS
        ):
            os.makedirs(os.path.join(root, rel), exist_ok=True)
            with open(os.path.join(root, rel, ".gitkeep"), "w") as f:
                f.write("")

    with open(os.path.join(root, ".gitignore"), "w", encoding="utf-8") as f:
        f.write(GITIGNORE)
    with open(os.path.join(root, "shared", "src", ".luaurc"), "w", encoding="utf-8") as f:
        f.write('{\n\t"languageMode": "nonstrict"\n}\n')
    with open(os.path.join(root, "shared", "src", "ReplicatedStorage", "Types", ".luaurc"), "w", encoding="utf-8") as f:
        f.write('{\n\t"languageMode": "strict"\n}\n')

    # the entries are named children, never init.<type>.luau: an init script
    # directly under a service directory makes Argon emit the SERVICE itself as
    # that script, which is not a thing the DataModel has. init.luau stays legal
    # one level down — Services/Shop/init.luau is a directory package.
    with open(os.path.join(root, "shared", "src", "ServerScriptService", "Server.server.luau"), "w", encoding="utf-8") as f:
        f.write(SERVER_ENTRY)
    with open(
        os.path.join(root, "shared", "src", "StarterPlayer", "StarterPlayerScripts", "Client.client.luau"), "w", encoding="utf-8"
    ) as f:
        f.write(CLIENT_ENTRY)

    # both runtime instruction files carry the same project-owned fields in
    # host-native wrappers.
    write_instruction_files(root, summary, tuple("%s|0" % place for place in places))

    materialize = materialized_runtime()
    for i, place in enumerate(places):
        with open(os.path.join(root, "%s.project.json" % place), "w", encoding="utf-8") as f:
            f.write(place_project(name, place))
        if i == 0:
            emit_default_project(root, place, materialize=materialize)

    emit_museum_links(shared, copy=materialize)
    emit_museum_items(shared, copy=materialize)
    emit_prescribed(shared)
    if not emit_keystones(root, criteria, places):
        return 2
    if relink(root) != 0:
        return 2

    os.remove(criteria_path(root))  # consumed: nothing reads it afterward
    print("EMITTED|%s|%s" % (name, ",".join(places)))
    return 0


def main(argv):
    if not argv:
        print(__doc__.strip())
        return 2
    cmd = argv[0]
    root = os.getcwd()
    kwargs = {}
    rest = []
    i = 1
    while i < len(argv):
        if argv[i] in ("--root", "--name", "--shared", "--host") and i + 1 < len(argv):
            kwargs[argv[i][2:]] = argv[i + 1]
            i += 2
        elif argv[i] == "--milestone":
            print("REFUSED|--milestone|new-game has no build-stage mode")
            return 2
        elif argv[i] == "--copy":
            kwargs[argv[i][2:]] = True
            i += 1
        else:
            rest.append(argv[i])
            i += 1
    root = kwargs.get("root", root)

    if cmd in ("install", "install-profile"):
        ok, detail, changed = gatelib.install_permissions_harness()
        if not ok:
            print(gatelib.permissions_harness_block("profile installation failed: %s" % detail))
            return 2
        status = "permissions-harness|%s" % ("installed" if changed else "exact")
        print(
            discovery_status(
                status,
                changed,
                profile_changed=changed,
            )
        )
        return 0

    if cmd == "bootstrap":
        return cmd_bootstrap(root)

    if cmd == "answer":
        if len(rest) < 2:
            print("usage: answer <flag> <text>")
            return 2
        return cmd_answer(root, rest[0], " ".join(rest[1:]))
    if cmd == "status":
        return cmd_status(root)
    if cmd == "refresh-instructions":
        if not gatelib.is_roblox_project(root):
            print("REFUSED|.roblox sentinel absent|this project is not harness-managed")
            return 2
        if not require_project_harness(root):
            return 2
        return refresh_instruction_files(root)
    if cmd == "materialize-default":
        if not gatelib.is_roblox_project(root):
            print("REFUSED|.roblox sentinel absent|this project is not harness-managed")
            return 2
        if not require_project_harness(root):
            return 2
        return materialize_default_project(root)
    if cmd == "emit":
        if not kwargs.get("name"):
            print("REFUSED|--name required")
            return 2
        return cmd_emit(root, kwargs["name"])
    if cmd == "relink":
        host = kwargs.get("host", "all")
        if host not in ("all", "codex", "claude"):
            print("REFUSED|--host|use codex or claude")
            return 2
        return relink(root, host=host)
    if cmd == "backfill":
        if not permission_preflight(root):
            return 2
        shared = kwargs.get("shared")
        if not shared:
            print("usage: backfill --shared DIR [--copy]")
            return 2
        copy = bool(kwargs.get("copy", False))  # --copy is the opt-in Windows path
        emit_museum_links(shared, copy=copy)
        emit_museum_items(shared, copy=copy)
        emit_prescribed(shared)
        print("backfilled|%s" % shared)
        return 0
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as e:
        sys.stderr.write("scaffold: CRASH %s: %s - nothing was emitted\n" % (type(e).__name__, e))
        sys.exit(2)
