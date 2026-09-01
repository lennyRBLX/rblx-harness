#!/usr/bin/env python3
"""roblox-new-game scaffolder — refuses to emit until the criteria file is
complete, and names the unanswered items so the skill re-asks exactly those.
The criteria file is consumed when the scaffold lands.

  scaffold.py answer <flag> <text> --root DIR     record an accepted answer
  scaffold.py status --root DIR                   answered / missing
  scaffold.py bootstrap --root DIR                create only the empty .roblox
                                                  managed-project sentinel
  scaffold.py emit --root DIR --name NAME [--milestone]
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
        candidates.append(os.path.join(os.path.dirname(project_root), "harness"))
    current = cwd
    while True:
        candidates.extend((current, os.path.join(current, "harness")))
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    for candidate in candidates:
        root = os.path.realpath(candidate)
        if os.path.isfile(os.path.join(root, "shared", "gates", "gatelib.py")):
            return root
    raise RuntimeError("sibling harness checkout could not be resolved")


SKILL_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
HARNESS = resolve_harness(SKILL_DIR)
PACKAGES = os.path.join(HARNESS, "packages")
MUSEUM_SKIP = {".DS_Store", "README.md", ".luaurc", ".gitignore"}
sys.path.insert(0, os.path.join(HARNESS, "shared", "gates"))
import gatelib  # noqa: E402

# museum canon that lives OUTSIDE the two fully-linked roots. Everything else
# under Services/ and Controllers/ is a project-owned byte-copy, but these are
# prescribed whole — the project supplies the handlers, never the driver — so
# they link back to harness/ per file and a fix lands in every project at once.
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
    "core_loop": "1. scoped core loop (one testable verb-object-reward statement)",
    "services": "2. seed service list (3-5 feature names)",
    "device": "3. target device & bandwidth (the prime lens)",
    "replication": "4. replication picks per state class + generated-world decision",
    "data_shape": "5. data shape + Development fixture + persistence reasoning",
    "gui_ownership": "6. GUI ownership split",
    "security": "7. security surface (remotes + client triggers + server authority)",
    "place_map": "8. place map (each place, what carries over)",
    "camera": "9. camera perspective per place",
    "rig": "10. avatar rig - R6, R15, or R15-R6",
    "streaming": "11. streaming - 'on', or 'off: <explicit reasoning>'",
}

CORE_SUBJECTS = {"a", "the", "player", "players", "user", "users", "you"}
CORE_VAGUE_VERBS = {"be", "do", "enjoy", "have", "make", "play"}
CORE_CONNECTORS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "the",
    "then",
    "through",
    "to",
    "with",
}
REWARD_VERBS = {"collect", "earn", "gain", "get", "obtain", "receive", "score", "unlock", "win"}
REWARD_NOUNS = {
    "coin",
    "coins",
    "currency",
    "gear",
    "gold",
    "loot",
    "point",
    "points",
    "progress",
    "rank",
    "reward",
    "rewards",
    "trophy",
    "trophies",
    "xp",
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
DEVICE_RE = re.compile(
    r"\b(?:android|ios|iphone|ipad|mobile|phone|tablet|pc|desktop|windows|mac|console|xbox|playstation|low[- ]end|high[- ]end)\b",
    re.IGNORECASE,
)
BANDWIDTH_RE = re.compile(
    r"(?:\b\d+(?:\.\d+)?\s*(?:k|m|g)(?:bit/s|bps)\b|\b(?:2g|3g|4g|5g|lte|dial[- ]up)\b|"
    r"\b(?:slow|limited|low[- ]bandwidth|high[- ]latency)\s+(?:wifi|wi-fi|network|connection|cellular|bandwidth)\b)",
    re.IGNORECASE,
)
CAMERA_PERSPECTIVE_RE = re.compile(
    r"\b(?:1st|first[- ]person|3rd|third[- ]person|fixed|top[- ]down|isometric|side[- ]view|over[- ]the[- ]shoulder|orbit)\b",
    re.IGNORECASE,
)
PLACE_RESERVED_NAMES = {
    "carry",
    "carryover",
    "controllers",
    "development",
    "playerdata",
    "services",
}


def permission_preflight(root):
    if not gatelib.is_roblox_project(root):
        print("REFUSED|.roblox sentinel absent|run bootstrap and relink, review changed integration, then retry")
        return False
    sentinel = os.path.join(root, ".roblox")
    if os.path.islink(sentinel) or os.path.getsize(sentinel) != 0:
        print("REFUSED|.roblox sentinel invalid|replace it with an empty regular file, then retry")
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
handoff.md
gates/
.DS_Store
tests/**
!tests/**/
!tests/**/.gitkeep
"""

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


def words(text):
    return [word.casefold() for word in re.findall(r"[A-Za-z][A-Za-z'-]*", text)]


def placeholder_decision(text):
    low = " ".join(text.casefold().split())
    return not low or any(re.search(pattern, low) for pattern in PLACEHOLDER_PATTERNS)


def substantive_reason(text):
    return not placeholder_decision(text) and len(words(text)) >= 4


def camera_mappings(text):
    return [
        (match.group(1), match.group(2).strip())
        for match in re.finditer(r"\b([A-Za-z][A-Za-z0-9]*)\s*=\s*([^,;\n]+)", text)
    ]


def place_clauses(text):
    """Return ``Place: details`` clauses without treating detail nouns as places."""
    matches = [
        match
        for match in re.finditer(r"(?:^|[;\n])\s*([A-Za-z][A-Za-z0-9]*)\s*:", text)
        if match.group(1).casefold() not in PLACE_RESERVED_NAMES
    ]
    clauses = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        clauses.append((match.group(1), text[match.end() : end].strip(" ;\n")))
    return clauses


def core_loop_error(text):
    tokens = words(text)
    if len(tokens) < 3:
        return "state one concrete verb-object-reward loop"
    index = 0
    while index < len(tokens) and tokens[index] in CORE_SUBJECTS:
        index += 1
    if index < len(tokens) and tokens[index] == "to":
        index += 1
    if index >= len(tokens) or tokens[index] in CORE_VAGUE_VERBS:
        return "state a concrete action verb, its object, and the earned reward"

    reward_indexes = [i for i in range(index, len(tokens)) if tokens[i] in REWARD_VERBS]
    reward_index = reward_indexes[0] if reward_indexes else None
    action_end = reward_index if reward_index is not None and reward_index > index else len(tokens)
    action_objects = [token for token in tokens[index + 1 : action_end] if token not in CORE_CONNECTORS]
    if reward_index == index:
        action_objects = [token for token in tokens[index + 1 :] if token not in CORE_CONNECTORS]
    if not action_objects:
        return "state what the player acts on, not only an activity"

    if reward_index is not None:
        reward_objects = [token for token in tokens[reward_index + 1 :] if token not in CORE_CONNECTORS]
        if reward_objects:
            return ""
    if any(token in REWARD_NOUNS for token in tokens[index + 1 :]):
        return ""
    return "state the concrete reward the loop earns or unlocks"


def service_names(text):
    if re.search(r"[,;\n]", text):
        return [name.strip() for name in re.split(r"[,;\n]+", text) if name.strip()]
    return [name for name in text.split() if name]


def validation_result(flag, text):
    """Return hard semantic errors and naming advisories for one answer."""
    errors = []
    warnings = []
    low = " ".join(text.casefold().split())

    if placeholder_decision(text):
        return ["replace filler or placeholder text with an explicit project decision"], warnings

    if flag == "core_loop":
        error = core_loop_error(text)
        if error:
            errors.append(error + "; example: dodge hazards, survive rounds, earn coins")
    elif flag == "services":
        names = service_names(text)
        if not 3 <= len(names) <= 5:
            errors.append("name 3-5 seed services")
        if len({name.casefold() for name in names}) != len(names):
            errors.append("seed service names must be distinct")
        for name in names:
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*(?:[ _-][A-Za-z0-9]+)*", name):
                errors.append("%s: use a concrete feature name made from words" % name)
                continue
            if re.search(r"(?:Service|Controller)$", name, re.IGNORECASE):
                bare = re.sub(r"(?:Service|Controller)$", "", name, flags=re.IGNORECASE) or "feature"
                warnings.append("WRIT10|%s|prefer the bare feature noun %s" % (name, bare))
    elif flag == "device":
        if not DEVICE_RE.search(text):
            errors.append("name the weakest target device or platform")
        if not BANDWIDTH_RE.search(text):
            errors.append("state a concrete or bounded target bandwidth, such as 3G or 1 Mbps")
    elif flag == "replication":
        shared = ("shared" in low or "global" in low) and "folder" in low and (
            "valueobject" in low or "value object" in low
        )
        per_player = ("per-player" in low or "per player" in low) and "exclusive" in low
        events = ("event" in low or "action" in low) and "remote" in low
        if not shared or not per_player or not events:
            errors.append("map shared state to Folders + ValueObjects, per-player state to Exclusive, and events to remotes")

        no_generated_world = bool(
            re.search(r"\bno (?:generated|procedural|streamed)\b", low)
            or re.search(r"\b(?:generated|procedural|streamed)(?: world| geometry)?\s*[:=]\s*(?:none|no|off)\b", low)
            or "hand-built" in low
            or "hand built" in low
            or "static world" in low
        )
        generated_world = any(term in low for term in ("generated world", "procedural world", "streamed geometry"))
        if not no_generated_world and not generated_world:
            errors.append("state the generated-world decision: static/hand-built, or the generated/streamed model")
        elif generated_world and not no_generated_world:
            if "server" not in low and "authority" not in low:
                errors.append("state authority for generated or streamed world geometry")
            if not any(term in low for term in ("chunk", "geometry", "layer", "model", "seed", "tile")):
                errors.append("state the seed/chunk/layer model for generated or streamed world geometry")
    elif flag == "data_shape":
        persistence = any(
            term in low
            for term in ("persist", "save", "session-only", "session only", "ephemeral", "no data")
        )
        reason = "because" in low or bool(re.search(r"\breason\s*:", low))
        fixture = bool(re.search(r"\b(?:development|dev(?:elopment)? fixture|fixture)\b", low))
        filled_fixture = fixture and bool(re.search(r"(?:=|\{|\[)", text))
        if not persistence:
            errors.append("state which data persists or is session-only")
        if not reason:
            errors.append("give explicit persistence reasoning with 'because' or 'reason:'")
        if not filled_fixture:
            errors.append("include a filled Development fixture")
    elif flag == "security":
        remote_decision = "remote" in low
        client_decision = "client" in low and any(
            term in low for term in ("can ", "may ", "send", "trigger", "request", "none")
        )
        authority = bool(
            re.search(r"\bauthority\s*:\s*server\b", low)
            or re.search(r"\bserver[- ]authoritative\b", low)
            or re.search(r"\bserver\b.{0,32}\b(?:authorizes|decides|owns|validates)\b", low)
        )
        if not remote_decision:
            errors.append("name the remotes, or explicitly state that there are no client remotes")
        if not client_decision:
            errors.append("state what the client may trigger")
        if not authority:
            errors.append("state server validation authority explicitly")
        for request_name in re.findall(r"\bRequest[A-Z][A-Za-z0-9]*\b", text):
            warnings.append("WRIT11|%s|prefer a bare-intent remote name" % request_name)
    elif flag == "gui_ownership":
        no_gui = bool(re.search(r"\bno (?:shipped )?gui\b", low))
        if no_gui:
            reason_parts = re.split(r"\bbecause\b", text, maxsplit=1, flags=re.IGNORECASE)
            reason = reason_parts[1] if len(reason_parts) == 2 else ""
            if not substantive_reason(reason):
                errors.append("give explicit reasoning when no GUI ships")
        elif re.search(r"\b(?:agent|assistant|automation|ai|codex|claude)\b", low):
            errors.append("assign GUI ownership to a human, not an agent")
        elif not (
            re.search(r"\b(?:owner|owns|owned by|human|designer|developer|team)\b", low)
            or re.fullmatch(r"[A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+)*", text)
            or re.search(r"\b[A-Z][A-Za-z'-]+\s*:", text)
        ):
            errors.append("name which human owns each GUI surface")
    elif flag == "place_map":
        clauses = place_clauses(text)
        if not clauses:
            errors.append("replace the placeholder with at least one 'Place: ...' decision")
        malformed_headers = []
        for match in re.finditer(r"\b([A-Za-z][A-Za-z0-9]*)\s*:", text):
            name = match.group(1)
            if name.casefold() in PLACE_RESERVED_NAMES:
                continue
            prefix = text[: match.start(1)]
            if re.search(r"(?:^|[;\n])\s*$", prefix):
                continue
            malformed_headers.append(name.casefold())
        if malformed_headers:
            errors.append(
                "separate place clauses with a semicolon or newline: %s"
                % ", ".join(sorted(set(malformed_headers)))
            )
        clause_names = [place.casefold() for place, _ in clauses]
        duplicates = sorted(
            {place for place in clause_names if clause_names.count(place) > 1}
        )
        if duplicates:
            errors.append("name each place once: %s" % ", ".join(duplicates))
        for place, detail in clauses:
            detail_low = detail.casefold()
            if not re.search(r"\bservices?\b", detail_low):
                errors.append("%s: name its services" % place)
            if not re.search(r"\bcontrollers?\b", detail_low):
                errors.append("%s: name its controllers" % place)
            if not re.search(r"\b(?:carry|carries|carryover|persist|reset|teleport|none)\b", detail_low):
                errors.append("%s: state what carries over or explicitly say none" % place)
    elif flag == "camera":
        mappings = camera_mappings(text)
        if not mappings:
            errors.append("map every place to a concrete camera perspective, for example Main=3rd")
        mapping_names = [place.casefold() for place, _ in mappings]
        duplicates = sorted(
            {place for place in mapping_names if mapping_names.count(place) > 1}
        )
        if duplicates:
            errors.append("map each place once: %s" % ", ".join(duplicates))
        for place, perspective in mappings:
            if not CAMERA_PERSPECTIVE_RE.search(perspective):
                errors.append("%s: use a concrete camera perspective" % place)
    elif flag == "streaming":
        reason = text.partition(":")[2].strip() if low.startswith("off:") else ""
        if low != "on" and not substantive_reason(reason):
            errors.append("use 'on' or 'off: <substantive explicit reasoning>'")
    elif flag == "rig" and text not in ("R6", "R15", "R15-R6"):
        errors.append("use R6, R15, or R15-R6")
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
    places = set(extract_places(criteria.get("place_map", "")))
    camera_places = {place for place, _ in camera_mappings(criteria.get("camera", ""))}
    if places and camera_places:
        missing = sorted(places - camera_places)
        extra = sorted(camera_places - places)
        if missing:
            invalid.setdefault("camera", []).append("camera decision missing for %s" % ", ".join(missing))
        if extra:
            invalid.setdefault("camera", []).append("camera decision names unknown place %s" % ", ".join(extra))
    return invalid, warnings


def cmd_answer(root, flag, text):
    if not permission_preflight(root):
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
    for warning in warnings:
        print("ADVISORY|%s|%s" % (flag, warning))
    criteria = load_criteria(root)
    criteria[flag] = text
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


def extract_places(text):
    """Return names from validated ``Place: details`` clauses, deduplicated."""
    names = []
    for name, _ in place_clauses(text):
        if name not in names:
            names.append(name)
    return names


def parse_places(criteria):
    """Place names from the validated place_map answer."""
    return extract_places(criteria.get("place_map", ""))


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
    directory symlinks. Relative, never absolute — sibling repos under one
    parent. Directory packages are recreated as real dirs with every file
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
            f.write("# museum files - delivered by symlink from harness/, never committed\n")
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
            f.write("# museum files - delivered by symlink from harness/, never committed\n")
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


def sibling_harness(root):
    candidate = os.path.join(os.path.dirname(os.path.realpath(root)), "harness")
    return candidate if os.path.realpath(candidate) == os.path.realpath(HARNESS) else ""


def require_sibling_harness(root):
    if sibling_harness(root):
        return True
    print("REFUSED|sibling harness absent|place the .roblox project beside harness/")
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
    harness/'s canonical form is deterministic. This is the bootstrap path:
    it can install static configuration and hooks, but it never creates live
    session authorization."""
    if not gatelib.is_roblox_project(root):
        print("REFUSED|.roblox sentinel absent|this project is not harness-managed")
        return 2
    if not require_sibling_harness(root):
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
    hooks_ok, hooks_detail, hooks_changed = gatelib.install_user_hooks()
    if not hooks_ok:
        print("Fix %s → rerun relink." % hooks_detail)
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
        or (codex_discovery and hooks_changed)
        or historical_discovery_changed
        or discovery_before != discovery_after
    )
    try:
        write_discovery_baseline(root, discovery_after, host)
    except OSError as error:
        print("Fix discovery cache write: %s → rerun relink." % str(error)[:160])
        return 2
    print("relinked|instructions, agents, roblox-writer, settings hook block, codex hooks + agents")
    status = "permissions-harness|%s|user-hooks=%s" % (
        "installed" if profile_changed else "exact",
        "installed" if hooks_changed else "exact",
    )
    print(
        discovery_status(
            status,
            discovery_changed,
            profile_changed=codex_discovery and profile_changed,
            hooks_changed=(codex_discovery and hooks_changed) or project_hooks_changed,
            host=host,
        )
    )
    return 0


def cmd_emit(root, name, milestone=False):
    if not permission_preflight(root):
        return 2
    if not require_sibling_harness(root):
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

    summary = criteria["core_loop"].strip().replace("\n", " ")
    places = parse_places(criteria)

    claude_md = os.path.join(root, "CLAUDE.md")
    agents_md = os.path.join(root, "AGENTS.md")
    if milestone:
        # growth is a re-interview, not a stored plan: rewrite the summary,
        # touch nothing else — in both runtime instruction files
        for md in (claude_md, agents_md):
            if os.path.exists(md):
                with open(md, encoding="utf-8") as f:
                    text = f.read()
                text = re.sub(r"(## summary\s*\n\n).*?(\n\n## )", r"\g<1>%s\g<2>" % summary, text, flags=re.DOTALL)
                with open(md, "w", encoding="utf-8") as f:
                    f.write(text)
        os.remove(criteria_path(root))
        print("milestone|summary rewritten")
        return 0

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
    if criteria.get("rig") == "R15-R6":
        conv_src = os.path.join(PACKAGES, "ServerStorage", "AnimationConverter.luau")
        if os.path.exists(conv_src):
            shutil.copyfile(conv_src, os.path.join(root, "shared", "src", "ServerStorage", "AnimationConverter.luau"))
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
        elif argv[i] in ("--milestone", "--copy"):
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
        hooks_ok, hooks_detail, hooks_changed = gatelib.install_user_hooks()
        if not hooks_ok:
            print("Fix %s → rerun this cmd." % hooks_detail)
            return 2
        status = "permissions-harness|%s|hooks=%s" % (
            "installed" if changed else "exact",
            "installed" if hooks_changed else "exact",
        )
        print(
            discovery_status(
                status,
                changed or hooks_changed,
                profile_changed=changed,
                hooks_changed=hooks_changed,
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
        if not require_sibling_harness(root):
            return 2
        return refresh_instruction_files(root)
    if cmd == "materialize-default":
        if not gatelib.is_roblox_project(root):
            print("REFUSED|.roblox sentinel absent|this project is not harness-managed")
            return 2
        if not require_sibling_harness(root):
            return 2
        return materialize_default_project(root)
    if cmd == "emit":
        if not kwargs.get("name"):
            print("REFUSED|--name required")
            return 2
        return cmd_emit(root, kwargs["name"], milestone=bool(kwargs.get("milestone")))
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
