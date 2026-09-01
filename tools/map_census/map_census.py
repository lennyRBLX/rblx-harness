#!/usr/bin/env python3
"""map_census — the only tool that reasons about instances rather than source.
OPT21 against the six static properties; OPT23 at each :Destroy()/:Clone()
site whose target resolves to a census entry with parts > 1000. Both live
here because both need the same instance census, and keeping perf_audit
Studio-free is what lets done-gate's floor run with Studio closed.

  map_census [--root DIR] [--mcp-cmd CMD] [--session ID] [file...]

Fails open: no census, or a target the census does not resolve, prints
SKIPPED and exits 0 — it never guesses a part count.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import houseout  # noqa: E402
import studio_rpc  # noqa: E402
from studio_rpc import EnvError, StudioRPC  # noqa: E402

SOURCE_SUFFIXES = (".lua", ".luau")

# the six static properties [R OPT21]
CENSUS_LUAU = """
local out = {}
local roots = { workspace }
for _, root in roots do
\tfor _, model in root:GetChildren() do
\t\tif model:IsA("Model") or model:IsA("Folder") then
\t\t\tlocal parts, castShadow, canQuery, canCollide, anchored, massless, canTouch = 0, 0, 0, 0, 0, 0, 0
\t\t\tfor _, d in model:GetDescendants() do
\t\t\t\tif d:IsA("BasePart") then
\t\t\t\t\tparts += 1
\t\t\t\t\tif d.CastShadow then castShadow += 1 end
\t\t\t\t\tif d.CanQuery then canQuery += 1 end
\t\t\t\t\tif d.CanCollide then canCollide += 1 end
\t\t\t\t\tif d.Anchored then anchored += 1 end
\t\t\t\t\tif d.Massless then massless += 1 end
\t\t\t\t\tif d.CanTouch then canTouch += 1 end
\t\t\t\tend
\t\t\tend
\t\t\tif parts > 0 then
\t\t\t\ttable.insert(out, model:GetFullName() .. "|" .. parts .. "|" .. castShadow .. "|" .. canQuery .. "|" .. canCollide .. "|" .. anchored .. "|" .. massless .. "|" .. canTouch)
\t\t\tend
\t\tend
\tend
end
print("<<CENSUS " .. #out)
print(table.concat(out, "\\n"))
print("CENSUS>>")
"""


def read_places_map(root):
    mapping = {}
    claude_md = os.path.join(root, "CLAUDE.md")
    if os.path.exists(claude_md):
        with open(claude_md, encoding="utf-8") as f:
            text = f.read()
        m = re.search(r"^## places\s*\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
        if m:
            for line in m.group(1).strip().split("\n"):
                parts = line.strip().split("|")
                if len(parts) == 2 and parts[1].isdigit():
                    mapping[parts[0]] = int(parts[1])
    return mapping


def gather_census(root, mcp_cmd, session):
    mapping = read_places_map(root)
    with StudioRPC(mcp_cmd) as rpc:
        _, place_id = rpc.select_studio(set(mapping.values()))
        if place_id == 0:
            raise EnvError("unpublished-place", "publish the place before running Studio checks")
        studio_rpc.acquire_lock(place_id, session, "map_census")
        try:
            console = rpc.call("execute_luau", {"code": CENSUS_LUAU})
        finally:
            studio_rpc.release_lock(place_id)
    m = re.search(r"<<CENSUS (\d+)\n(.*?)CENSUS>>", console, re.DOTALL)
    if not m:
        raise EnvError("census-unparseable", "sentinels missing; rerun")
    count = int(m.group(1))
    records = [ln for ln in m.group(2).strip().split("\n") if ln.strip()]
    if len(records) != count:
        raise EnvError("census-truncated", "expected %d records, got %d" % (count, len(records)))
    census = {}
    for rec in records:
        parts = rec.split("|")
        if len(parts) == 8:
            census[parts[0]] = {
                "parts": int(parts[1]),
                "CastShadow": int(parts[2]),
                "CanQuery": int(parts[3]),
                "CanCollide": int(parts[4]),
                "Anchored": int(parts[5]),
                "Massless": int(parts[6]),
                "CanTouch": int(parts[7]),
            }
    return census


def scan_sites(files):
    """:Destroy()/:Clone() call sites with a resolvable literal target chain."""
    sites = []
    call_re = re.compile(r"([%\w_.\[\]\"']+):(Destroy|Clone)\s*\(")
    for path in files:
        if not path.endswith(SOURCE_SUFFIXES) or not os.path.exists(path) or os.path.islink(path):
            continue
        with open(path, encoding="utf-8") as f:
            for lineno, line in enumerate(f.read().splitlines(), 1):
                for m in call_re.finditer(line):
                    sites.append((path, lineno, m.start(1) + 1, m.group(1), m.group(2)))
    return sites


def main(argv):
    root = os.getcwd()
    mcp_cmd = None
    session = "local"
    files = []
    i = 0
    while i < len(argv):
        if argv[i] == "--root" and i + 1 < len(argv):
            root = argv[i + 1]
            i += 2
        elif argv[i] == "--mcp-cmd" and i + 1 < len(argv):
            mcp_cmd = argv[i + 1]
            i += 2
        elif argv[i] == "--session" and i + 1 < len(argv):
            session = argv[i + 1]
            i += 2
        else:
            files.append(argv[i])
            i += 1

    census = gather_census(root, mcp_cmd, session)
    findings = []
    notes = []

    # OPT21: report unoptimized static-property counts per container
    for path, info in sorted(census.items()):
        opts = []
        for prop in ("CastShadow", "CanQuery", "CanCollide", "CanTouch"):
            if info[prop] > 0:
                opts.append("%s on %d/%d" % (prop, info[prop], info["parts"]))
        unanchored = info["parts"] - info["Anchored"]
        if unanchored > 0:
            opts.append("unanchored %d/%d" % (unanchored, info["parts"]))
        if opts:
            notes.append("census|%s|%d parts|%s" % (path, info["parts"], ", ".join(opts)))

    # OPT23: Destroy/Clone sites whose target resolves to a census entry
    # with parts > 1000
    if not files:
        for dirpath, dirnames, filenames in os.walk(os.path.join(root, "shared")):
            dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
            for fn in filenames:
                if fn.endswith(SOURCE_SUFFIXES):
                    files.append(os.path.join(dirpath, fn))
    skipped = []
    for path, lineno, col, chain, method in scan_sites(files):
        leaf = chain.split(".")[-1].strip("\"'[]")
        hit = None
        for census_path, info in census.items():
            if census_path.endswith("." + leaf) or census_path == leaf:
                hit = (census_path, info)
                break
        if hit is None:
            skipped.append("%s:%d %s:%s" % (houseout.elide(path, root), lineno, chain, method))
            continue
        census_path, info = hit
        if info["parts"] > 1000:
            findings.append(
                (path, lineno, col, "OPT23", "%s:%s on %s (%d parts)" % (chain, method, census_path, info["parts"]), "frame-stagger - >1000 parts in one frame")
            )

    if findings:
        print("map_census: NOTED")
        print()
        sys.stdout.write(houseout.render_findings("map_census", findings, root, blocked=False))
    else:
        print("map_census: MEASURED")
    print()
    for n in notes[:30]:
        print(n)
    for s in skipped[:10]:
        print("SKIPPED OPT23 %s - census does not resolve the target" % s)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except EnvError as e:
        print("ENV|%s|%s" % (e.cause, e.remedy))
        sys.exit(3)
    except SystemExit:
        raise
    except Exception as e:
        sys.stderr.write("map_census: CRASH %s: %s - nothing was measured\n" % (type(e).__name__, e))
        sys.exit(2)
