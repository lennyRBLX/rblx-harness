#!/usr/bin/env python3
"""create_boilerplate — the one emitter [R BC4, BC5]. Deterministic
generation, not analysis: same kind and name produce the same bytes, and the
output is a fixed point of the formatter.

  create_boilerplate <kind> <Name> [--root DIR] [--place P] [--side server|client]
  create_boilerplate --test <Mode>.<Name> --place <Place> [--side server|client] [--root DIR]
  create_boilerplate --expand <Name> [--place P] [--root DIR]

With --place, a kind emits under places/<P>/src/ instead of shared/src/ —
for service, controller and tool-handler the same subtree, mounted per-place
by the Argon project (PlaceServices / PlaceControllers). gui is the
exception: the shared tree nests it under Controllers/Gui/, a place mounts
Gui/ directly under StarterPlayerScripts, so gui carries its own per-place
destination rather than the prefix swap. Without --place, shared/src/ as
before. The place must already exist under places/; data-module and update
are shared-tree only — nothing mounts a place Data/ and the Updates runner
scans only the shared folder.

Kinds: service · controller · gui · update · data-module · tool-handler.
The destination is derived from kind and whether --place is given — a path
is never passed [R GATE2]. A new service or controller is a single file
until it needs children; --expand converts the flat file to the folder form
in one deterministic, reversible step.

A Service or Controller suffix produces a naming advisory [R WRIT10] but does
not deny emission. Unsafe path-shaped names remain refused [R GATE2]. An
existing target exits 2 — test sources are also preserved [R
DEBUG2].
"""

import os
import json
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import houseout  # noqa: E402

FRAME = """const m = {}

-- privates

-- functions
function m:Start()
end

-- events

return m
"""

# controller and gui stop at -- functions. A client module's connections are
# made inside Start against instances it has already waited for, so the events
# divider it would be handed is one no writer fills — and an empty divider
# copied forward is a section that collects the connections that belong in
# Start. The divider stays sanctioned [R BC5]; it is earned by content, not
# emitted ahead of it.
CONTROLLER_FRAME = """const m = {}

-- privates

-- functions
function m:Start()
end

return m
"""

# WRIT29 makes the CanYield shape non-negotiable: a timeout and a nil-check,
# never a guard. So the frame ships the whole branch rather than the call
# alone — an emitted frame its own lint blocks teaches the wrong shape at the
# one moment the writer is copying it. Absent PlayerGui, the GUI declines to
# start: Gui/init.luau task.spawns each child's Start under pcall, so the
# return is the whole contract and the warn is what a human reads [R DEBUG8].
GUI_FRAME = """const Players = game:GetService("Players")

const Player = Players.LocalPlayer

const m = {}

-- privates

-- functions
function m:Start()
	local gui = Player:WaitForChild("PlayerGui", 10)
	if not gui then
		warn(script.Name .. " | no PlayerGui after 10s | the GUI does not start")
		return
	end
end

return m
"""

TOOL_FRAME = """const m = {}

-- privates

-- functions
function m:Start()
end

function m:Equipped(player, tool)
end

function m:Activated(player, tool)
end

-- events

return m
"""

UPDATE_FRAME = """const RELEASE_DATE = "{date}"

const m = {{
	ReleaseDate = "{date}"
}}

-- privates

-- functions
function m:Start()
	if m.notLatestUpdate then
		return
	end
end

function m:Destroy()
end

-- events

return m
"""

DATA_FRAME = """export type Entry = {
	Name: string,
}

return {}
"""

TEST_FRAME = """-- {what}
-- {how}
local ENABLED = false
local RunService = game:GetService("RunService")

if not ENABLED or not RunService:IsStudio() then
    return
end

local Runner = require(script.Parent.TestSupport.Runner)
Runner.run(script, {{
    id = "{id}", -- One question; new question needs a new ID.
    timeout = 30,
    setup = function(context)
        -- Own fixtures through context. Declare metrics and spike thresholds here.
    end,
    warmup = function(context)
        -- Warm the representative workload outside measurement.
    end,
    workload = function(context)
        -- Stop on the declared acceptance condition. Missing assertions cannot pass.
        context:check(false, "test question and stopping condition required")
    end,
}})
"""

# Staging remains explicitly gated. Receipt fixtures use the same lifecycle;
# do not install an unowned, unbounded ProcessReceipt wrapper.
LIVE_FRAME = TEST_FRAME.replace(
    'local RunService = game:GetService("RunService")',
    'local STAGING_PLACE_ID = 0',
).replace(
    'not RunService:IsStudio()',
    'game.PlaceId ~= STAGING_PLACE_ID or STAGING_PLACE_ID == 0',
)

KINDS = {
    "service": ("shared/src/ServerScriptService/Services/{name}.luau", FRAME),
    "controller": ("shared/src/StarterPlayer/StarterPlayerScripts/Controllers/{name}.luau", CONTROLLER_FRAME),
    "gui": ("shared/src/StarterPlayer/StarterPlayerScripts/Controllers/Gui/{name}.luau", GUI_FRAME),
    "update": ("shared/src/ServerScriptService/Services/Updates/{name}.luau", None),
    "data-module": ("shared/src/ReplicatedStorage/Data/{name}.luau", DATA_FRAME),
    "tool-handler": ("shared/src/ServerScriptService/Services/{name}.luau", TOOL_FRAME),
}

# the kinds whose place mount is not the shared subtree under a swapped
# prefix: a place mounts Gui/ directly under StarterPlayerScripts, so the
# swap would land it under a Controllers/ that nothing mounts there
PLACE_DESTS = {
    "gui": "places/%s/src/StarterPlayer/StarterPlayerScripts/Gui/{name}.luau",
}


def refuse_name_component(name):
    print("create_boilerplate: REFUSED\n")
    print("%s|GATE2|name is not one safe path component|use letters and digits, beginning with a letter" % name)
    return 2


def advise_name(name, reason, remedy):
    print("create_boilerplate: ADVISORY")
    print("%s|WRIT10|%s|%s" % (name, reason, remedy))


def existing_places(root):
    d = os.path.join(root, "places")
    try:
        return sorted(e for e in os.listdir(d) if os.path.isdir(os.path.join(d, e)))
    except OSError:
        return []


def refuse_place(root, place):
    # membership in the places/ listing, not a path test: a directory entry
    # can never traverse, and a typo names the trees that do exist
    have = ", ".join(existing_places(root)) or "none"
    print("create_boilerplate: REFUSED\n")
    print("%s|GATE2|places/%s/ absent|existing: %s - the scaffold creates place trees" % (place, place, have))
    return 2


def emit_test(root, spec, place, side):
    m = re.match(r"^(Fix|Diagnose|Measure|LIVE)\.([A-Za-z0-9]+)$", spec)
    if not m:
        print("create_boilerplate: REFUSED\n")
        print("%s|DEBUG2|test name is <Mode>.<Name>|Fix.Shop, Diagnose.Pets, LIVE.Shop" % spec)
        return 2
    if not place:
        print("create_boilerplate: REFUSED\n")
        print("%s|DEBUG2|--place required|tests live in tests/<Place>/" % spec)
        return 2
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", place) or side not in (None, "server", "client"):
        return refuse_name_component(place)
    side = side or "server"
    dest = os.path.join(root, "tests", place, side, "%s.%s.luau" % (spec, side))
    mode = spec.split(".")[0]
    header = (LIVE_FRAME if mode == "LIVE" else TEST_FRAME).format(
        what="state one question and its stopping condition",
        how=("Set the staging PlaceId, RunId and confirmed Ready before an authorized staging run."
             if mode == "LIVE" else "In stopped Edit set RunId and confirmed Ready, enable, then MCP Play; collect with studio output."),
        id=spec,
    )
    if os.path.exists(dest):
        print("create_boilerplate: REFUSED|test exists; preserve source and edit explicitly")
        return 2
    canonical = os.path.join(os.path.dirname(os.path.dirname(HERE)), "shared", "test_support")
    mappings = []
    for name in (place + ".project.json", "default.project.json"):
        project = os.path.join(root, name)
        if not os.path.isfile(project):
            continue
        with open(project, encoding="utf-8") as stream:
            document = json.load(stream)
        tree = document.get("tree", {})
        service = tree.get("ServerScriptService", {}) if side == "server" else tree.get("StarterPlayer", {}).get("StarterPlayerScripts", {})
        tests = service.get("Tests", {})
        if tests.get("$path") != "tests/%s/%s" % (place, side):
            continue
        wanted = {"$path": os.path.relpath(canonical, root).replace(os.sep, "/")}
        if "TestSupport" in tests and tests["TestSupport"] != wanted:
            print("create_boilerplate: REFUSED|TestSupport mapping belongs to another source")
            return 2
        tests["TestSupport"] = wanted
        mappings.append((project, document))
    if not mappings:
        print("create_boilerplate: REFUSED|map tests/%s/%s through Argon before authoring" % (place, side))
        return 2
    for project, document in mappings:
        with open(project, "w", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2)
            stream.write("\n")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(header)
    print("create_boilerplate: EMITTED\n")
    print(houseout.elide(dest, root))
    return 0


def expand(root, name, place=None):
    if place and place not in existing_places(root):
        return refuse_place(root, place)
    prefix = "places/%s/src" % place if place else "shared/src"
    flat_candidates = [
        os.path.join(root, prefix, "ServerScriptService/Services", name + ".luau"),
        os.path.join(root, prefix, "StarterPlayer/StarterPlayerScripts/Controllers", name + ".luau"),
    ]
    for flat in flat_candidates:
        if os.path.exists(flat):
            folder = flat[: -len(".luau")]
            target = os.path.join(folder, "init.luau")
            if os.path.exists(folder):
                print("create_boilerplate: REFUSED\n")
                print("%s|GATE2|folder form already exists|nothing moved" % name)
                return 2
            os.makedirs(folder)
            os.rename(flat, target)
            print("create_boilerplate: EXPANDED\n")
            print("%s -> %s" % (houseout.elide(flat, root), houseout.elide(target, root)))
            return 0
    print("create_boilerplate: REFUSED\n")
    print("%s|GATE2|no flat module found|emit it first" % name)
    return 2


def main(argv):
    root = os.getcwd()
    place = None
    side = None
    positional = []
    test_spec = None
    expand_name = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--root" and i + 1 < len(argv):
            root = argv[i + 1]
            i += 2
        elif a == "--place" and i + 1 < len(argv):
            place = argv[i + 1]
            i += 2
        elif a == "--side" and i + 1 < len(argv):
            side = argv[i + 1]
            i += 2
        elif a == "--test" and i + 1 < len(argv):
            test_spec = argv[i + 1]
            i += 2
        elif a == "--expand" and i + 1 < len(argv):
            expand_name = argv[i + 1]
            i += 2
        else:
            positional.append(a)
            i += 1

    if test_spec:
        return emit_test(root, test_spec, place, side)
    if expand_name:
        return expand(root, expand_name, place)
    if len(positional) != 2:
        print(__doc__.strip())
        return 2
    kind, name = positional
    if kind not in KINDS:
        print("create_boilerplate: REFUSED\n")
        print("%s|BC4|unknown kind|service controller gui update data-module tool-handler" % kind)
        return 2

    # Destination containment remains hard. House naming is advisory and the
    # emitter never silently renames the requested component.
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", name):
        return refuse_name_component(name)
    suffix = re.search(r"(Service|Controller)$", name, re.IGNORECASE)
    if suffix:
        bare = name[: -len(suffix.group(1))] or "the feature"
        advise_name(name, "%s suffix" % suffix.group(1), "prefer " + bare)
    if not re.match(r"^[A-Z][A-Za-z0-9]*$", name):
        advise_name(name, "not a PascalCase feature noun", "prefer a PascalCase feature noun")

    dest_rel, frame = KINDS[kind]
    if place:
        if kind in ("data-module", "update"):
            # nothing mounts a place Data/, and the Updates runner scans
            # only the shared folder's children — a place emission is a
            # dead file, refused rather than stranded
            print("create_boilerplate: REFUSED\n")
            print("%s|GATE2|%s has no per-place mount|only Services and Controllers mount per place - emit without --place" % (name, kind))
            return 2
        if place not in existing_places(root):
            return refuse_place(root, place)
        if kind in PLACE_DESTS:
            # its own destination, not the shared subtree re-rooted
            dest_rel = PLACE_DESTS[kind] % place
        else:
            # same subtree, place-mounted root: PlaceServices / PlaceControllers
            assert dest_rel.startswith("shared/src/")
            dest_rel = "places/%s/src/" % place + dest_rel[len("shared/src/") :]
    dest = os.path.join(root, dest_rel.format(name=name))
    if kind == "update":
        import datetime

        frame = UPDATE_FRAME.format(date=datetime.date.today().isoformat())
    if os.path.exists(dest):
        print("create_boilerplate: REFUSED\n")
        print("%s|BC4|target exists|edit the existing file - the emitter never overwrites" % houseout.elide(dest, root))
        return 2
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(frame)
    print("create_boilerplate: EMITTED\n")
    print(houseout.elide(dest, root))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as e:
        sys.stderr.write("create_boilerplate: CRASH %s: %s - nothing was emitted\n" % (type(e).__name__, e))
        sys.exit(2)
