#!/usr/bin/env python3
"""place_map — reconcile places/ against the Studio universe and update the
AGENTS.md places block.

The map is also the wrong-place verification: GetGamePlacesAsync returns the
universe of the place the proxy is attached to, so a proxy answering for a
different Studio matches none of this project's mapped ids — and that mismatch
is the refusal.

Both sides of places/<Name> -> PlaceId are static; the Studio name is never
stored, so a Studio rename drifts nothing. The name appears only in this
tool's messages, where it tells the developer which place is unmapped.

Exit 0: every places/ child mapped, every universe place recognised (block
written). Exit 3 with ENV records otherwise.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
from studio_rpc import EnvError, StudioRPC  # noqa: E402

# Sentinels and a count make a truncated response fail closed: the tool takes
# only the lines between the sentinels and asserts it received exactly n
# records. Sets no Source and constructs no script, so GATE5 permits it.
UNIVERSE_LUAU = """
local AssetService = game:GetService("AssetService")
local pages = AssetService:GetGamePlacesAsync()
local out = {}
while true do
\tfor _, place in pages:GetCurrentPage() do
\t\ttable.insert(out, place.PlaceId .. "|" .. place.Name)
\tend
\tif pages.IsFinished then break end
\tpages:AdvanceToNextPageAsync()
end
return "<<PLACES " .. #out .. "\\n" .. table.concat(out, "\\n") .. "\\nPLACES>>"
"""


def read_places_block(agents_md):
    """Name -> PlaceId from the ## places block."""
    mapping = {}
    if not os.path.exists(agents_md):
        return mapping
    with open(agents_md, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"^## places\s*\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if not m:
        return mapping
    for line in m.group(1).strip().split("\n"):
        parts = line.strip().split("|")
        if len(parts) == 2 and parts[1].isdigit():
            mapping[parts[0]] = int(parts[1])
    return mapping


def write_places_block(agents_md, mapping):
    lines = "\n".join("%s|%d" % (name, pid) for name, pid in sorted(mapping.items()))
    block = "## places\n\n%s\n" % lines
    if os.path.exists(agents_md):
        with open(agents_md, encoding="utf-8") as f:
            text = f.read()
        if re.search(r"^## places\s*\n", text, re.MULTILINE):
            text = re.sub(r"^## places\s*\n.*?(?=^## |\Z)", block, text, flags=re.MULTILINE | re.DOTALL)
        else:
            text = text.rstrip("\n") + "\n\n" + block
    else:
        text = block
    with open(agents_md, "w", encoding="utf-8") as f:
        f.write(text)


def parse_universe(response):
    m = re.search(r"<<PLACES (\d+)\n(.*?)PLACES>>", response, re.DOTALL)
    if not m:
        raise EnvError("universe-unparseable", "Restart Roblox Studio, open the project place, enable MCP, then retry.")
    count = int(m.group(1))
    records = [ln for ln in m.group(2).strip().split("\n") if ln.strip()]
    if len(records) != count:
        raise EnvError("universe-truncated", "Restart Roblox Studio, open the project place, enable MCP, then retry.")
    out = {}
    for rec in records:
        pid, _, name = rec.partition("|")
        if not pid.isdigit():
            raise EnvError("universe-unparseable", "Restart Roblox Studio, open the project place, enable MCP, then retry.")
        out[int(pid)] = name
    return out


def positive_place_ids(mapping):
    return {place_id for place_id in mapping.values() if place_id > 0}


def reconcile_places(children, mapping, universe):
    """Return a complete child -> PlaceId map, problems, and new name maps.

    Zero is the scaffold sentinel, never a mapped PlaceId. A zero or absent
    entry may bootstrap by exact Studio name; a nonzero entry is the static
    identity and must belong to this universe. Every PlaceId has one owner.
    """
    new_mapping = {}
    problems = []
    mapped = []
    owners = {}

    for name in children:
        place_id = mapping.get(name, 0)
        if place_id > 0:
            if place_id not in universe:
                problems.append(
                    "ENV|stale-mapping|Open the right project experience, update places/%s PlaceId, then retry."
                    % name
                )
                continue
            if place_id in owners:
                problems.append(
                    "ENV|duplicate-mapping|Give places/%s and places/%s unique PlaceIds, then retry."
                    % (owners[place_id], name)
                )
                continue
            new_mapping[name] = place_id
            owners[place_id] = name
            continue

        by_name = [pid for pid, universe_name in universe.items() if universe_name == name and pid not in owners]
        if len(by_name) == 1:
            place_id = by_name[0]
            new_mapping[name] = place_id
            owners[place_id] = name
            mapped.append((name, place_id))
        else:
            problems.append("ENV|unmapped-child|Link places/%s to its Roblox PlaceId, then retry." % name)

    known_ids = set(new_mapping.values())
    for place_id, universe_name in sorted(universe.items()):
        if place_id not in known_ids:
            problems.append('ENV|unmapped-place|Add places/%s for PlaceId %d, then retry.' % (universe_name, place_id))

    return new_mapping, problems, mapped


def main(argv):
    root = os.getcwd()
    mcp_cmd = None
    i = 0
    while i < len(argv):
        if argv[i] == "--root" and i + 1 < len(argv):
            root = argv[i + 1]
            i += 2
        elif argv[i] == "--mcp-cmd" and i + 1 < len(argv):
            mcp_cmd = argv[i + 1]
            i += 2
        else:
            i += 1

    places_dir = os.path.join(root, "places")
    children = sorted(
        d for d in (os.listdir(places_dir) if os.path.isdir(places_dir) else []) if os.path.isdir(os.path.join(places_dir, d))
    )
    agents_md = os.path.join(root, "AGENTS.md")
    mapping = read_places_block(agents_md)
    wanted_place_ids = positive_place_ids(mapping)

    with StudioRPC(mcp_cmd) as rpc:
        rpc.select_studio(wanted_place_ids)
        response = rpc.call("execute_luau", {"code": UNIVERSE_LUAU, "datamodel_type": "Edit"})
        universe = parse_universe(response)

    new_mapping, problems, mapped = reconcile_places(children, mapping, universe)
    for name, place_id in mapped:
        print("mapped|%s|%d" % (name, place_id))

    if problems:
        for p in problems:
            print(p)
        return 3
    write_places_block(agents_md, new_mapping)
    for name, pid in sorted(new_mapping.items()):
        print("place|%s|%d" % (name, pid))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except EnvError as e:
        print("ENV|%s|%s" % (e.cause, e.remedy))
        sys.exit(3)
    except Exception as e:
        sys.stderr.write("Run place_map; fix the err; retry.\n")
        sys.exit(2)
