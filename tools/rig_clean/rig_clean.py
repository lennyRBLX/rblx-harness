#!/usr/bin/env python3
"""rig_clean — finds every instance named AnimSaves, anywhere in the
DataModel, any class. AnimSaves is the Animation Editor's working storage;
an unconditional sweep would destroy a human's unsaved keyframe work, so the
default never mutates: rig_clean scans and reports, rig_clean --delete
performs the deletion and is invoked only after the human says so.

Output: path|status records — found on a scan, done/fail on a delete. Silent
at exit 0 when there is nothing to find; any fail row makes the verdict
FAILED and the exit 2. Studio unreachable exits 3 (GATE4 already blocks
writes in that state).

Usage: rig_clean.py [--delete] [--root DIR] [--mcp-cmd CMD] [--session ID]
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import studio_rpc  # noqa: E402
from studio_rpc import EnvError, StudioRPC  # noqa: E402

SCAN_LUAU = """
local found = {}
for _, service in game:GetChildren() do
\tlocal ok, descendants = pcall(function()
\t\treturn service:GetDescendants()
\tend)
\tif ok then
\t\tfor _, inst in descendants do
\t\t\tif inst.Name == "AnimSaves" then
\t\t\t\ttable.insert(found, inst:GetFullName())
\t\t\tend
\t\tend
\tend
end
print("<<RIGS " .. #found)
print(table.concat(found, "\\n"))
print("RIGS>>")
"""

DELETE_LUAU = """
local results = {}
for _, service in game:GetChildren() do
\tlocal ok, descendants = pcall(function()
\t\treturn service:GetDescendants()
\tend)
\tif ok then
\t\tfor _, inst in descendants do
\t\t\tif inst.Name == "AnimSaves" then
\t\t\t\tlocal path = inst:GetFullName()
\t\t\t\tlocal deleted = pcall(function()
\t\t\t\t\tinst:Destroy()
\t\t\t\tend)
\t\t\t\ttable.insert(results, path .. "|" .. (deleted and "done" or "fail"))
\t\t\tend
\t\tend
\tend
end
print("<<RIGS " .. #results)
print(table.concat(results, "\\n"))
print("RIGS>>")
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


def parse_records(console):
    m = re.search(r"<<RIGS (\d+)\n(.*?)RIGS>>", console, re.DOTALL)
    if not m:
        raise EnvError("scan-unparseable", "sentinels missing from execute_luau console; rerun")
    count = int(m.group(1))
    records = [ln for ln in m.group(2).strip().split("\n") if ln.strip()]
    if len(records) != count:
        raise EnvError("scan-truncated", "expected %d records, got %d" % (count, len(records)))
    return records


def main(argv):
    delete = "--delete" in argv
    root = os.getcwd()
    mcp_cmd = None
    session = "local"
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
            i += 1

    mapping = read_places_map(root)
    with StudioRPC(mcp_cmd) as rpc:
        _, place_id = rpc.select_studio(set(mapping.values()))
        if place_id == 0:
            raise EnvError("unpublished-place", "publish the place before running Studio checks")
        studio_rpc.acquire_lock(place_id, session, "rig_clean")
        try:
            console = rpc.call("execute_luau", {"code": DELETE_LUAU if delete else SCAN_LUAU})
        finally:
            studio_rpc.release_lock(place_id)

    records = parse_records(console)
    if not records:
        return 0  # silent when there is nothing to find

    if delete:
        failed = any(r.endswith("|fail") for r in records)
        print("rig_clean: %s" % ("FAILED" if failed else "CLEANED"))
        print()
        for r in records:
            print(r)
        return 2 if failed else 0
    print("rig_clean: FOUND")
    print()
    for r in records:
        print("%s|found" % r)
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
        sys.stderr.write("rig_clean: CRASH %s: %s - nothing was scanned\n" % (type(e).__name__, e))
        sys.exit(2)
