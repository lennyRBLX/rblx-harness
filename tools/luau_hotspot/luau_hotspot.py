#!/usr/bin/env python3
"""luau_hotspot — samples Luau call stacks through ScriptProfilerService.
OPT1's measure step; frame_census completes the pair.

  luau_hotspot --emit-harness server|client|both [--seconds N] [--frequency HZ]
  luau_hotspot --from-json FILE [FILE...]

The seam is execute_luau, and it survives GATE5: every ScriptProfilerService
member is PluginSecurity and execute_luau runs at plugin identity; the
harness sets no Source and constructs no script. Parse the raw JSON, never
DeserializeJSON — the service's own deserialiser renames fields and
Functions[].TotalDuration reads nil off the returned table.

Schema Version 2, durations in microseconds (converted to ms — OPT4/OPT5
state thresholds in ms), SessionStart/EndTime in millisecond epoch,
frequency range [1, 10000].

Output: fn|self_ms|total_ms|site|caller|flags records under a MEASURED
verdict line carrying session facts. Fails open — a measurement reporter; no
threshold in it produces a verdict.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import houseout  # noqa: E402

HARNESS = """-- luau_hotspot harness: run through execute_luau in play mode; the console
-- echo between the sentinels is the raw JSON capture. GATE5-clean: no Source
-- writes, no script construction.
local SPS = game:GetService("ScriptProfilerService")
local captured = nil
local connection
connection = SPS.OnNewData:Connect(function(player, jsonString)
	captured = jsonString
end)
SPS:{start}({frequency})
task.wait({seconds})
SPS:{stop}()
SPS:{request}()
local deadline = os.clock() + 5
while captured == nil and os.clock() < deadline do
	task.wait(0.1)
end
connection:Disconnect()
if captured == nil then
	print("<<HOTSPOT-NONE {side} - no data returned; is play mode running?>>")
else
	print("<<HOTSPOT {side}")
	print(captured)
	print("HOTSPOT>>")
end
"""


def emit_harness(side, seconds, frequency):
    sides = ["server", "client"] if side == "both" else [side]
    for s in sides:
        if s == "server":
            body = HARNESS.format(start="ServerStart", stop="ServerStop", request="ServerRequestData", frequency=frequency, seconds=seconds, side=s)
        else:
            body = HARNESS.format(
                start="ClientStart", stop="ClientStop", request="ClientRequestData", frequency=frequency, seconds=seconds, side=s
            ).replace("SPS:ClientStart(", "SPS:ClientStart(game:GetService(\"Players\"):GetPlayers()[1], ").replace(
                "SPS:ClientStop()", "SPS:ClientStop(game:GetService(\"Players\"):GetPlayers()[1])"
            ).replace("SPS:ClientRequestData()", "SPS:ClientRequestData(game:GetService(\"Players\"):GetPlayers()[1])")
        print(body)


def analyze(path, root):
    label = os.path.basename(path)
    for suffix in (".json",):
        if label.endswith(suffix):
            label = label[: -len(suffix)]
    with open(path, encoding="utf-8") as f:
        text = f.read()
    # tolerate a console capture with the sentinels still around the JSON
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        print("ENV|capture-unparseable|%s holds no JSON object" % path)
        return 3
    try:
        data = json.loads(text[start : end + 1])
    except ValueError as e:
        print("ENV|capture-unparseable|%s" % e)
        return 3
    version = data.get("Version")
    if version != 2:
        print("ENV|schema-version|expected Version 2, got %r - refusing to parse fiction" % version)
        return 3

    functions = data.get("Functions", [])
    nodes = data.get("Nodes", [])
    categories = data.get("Categories", [])

    # per-function aggregation: walk the tree from category roots; a node's
    # self time is its total minus its children's totals; the child's
    # function comes from the PARENT's FunctionIds
    agg = {}  # fid -> {self, total, caller}

    def node_children(node):
        fids = node.get("FunctionIds") or []
        nids = node.get("NodeIds") or []
        return list(zip(fids, nids))

    def walk(node_index, fid, caller_fid, seen):
        if node_index in seen:
            return 0.0
        seen = seen | {node_index}
        if not (1 <= node_index <= len(nodes)):
            return 0.0
        node = nodes[node_index - 1]
        total = float(node.get("TotalDuration") or 0.0)
        child_total = 0.0
        for child_fid, child_nid in node_children(node):
            child_total += walk(child_nid, child_fid, fid, seen)
        self_time = max(0.0, total - child_total)
        if fid is not None:
            entry = agg.setdefault(fid, {"self": 0.0, "total": 0.0, "caller": None})
            entry["self"] += self_time
            entry["total"] += total
            if entry["caller"] is None and caller_fid is not None:
                entry["caller"] = caller_fid
        return total

    session_total = 0.0
    for cat in categories:
        nid = cat.get("NodeId")
        if isinstance(nid, int):
            session_total += walk(nid, None, None, frozenset())

    def fn_name(fid):
        if not (isinstance(fid, int) and 1 <= fid <= len(functions)):
            return "anonymous#%s" % fid, "void", "void"
        fn = functions[fid - 1]
        name = fn.get("Name")
        source = fn.get("Source")
        line = fn.get("Line")
        site = "void"
        if source:
            site = houseout.elide(source, root) if os.sep in str(source) or "/" in str(source) else str(source)
            if line:
                site = "%s:%s" % (site, line)
        # unknowns keep their identity and gain their caller: the FunctionId
        # index is stable within a capture, so two unknowns stay two rows
        flags = []
        raw_flags = fn.get("Flags") or 0
        if raw_flags & 1:
            flags.append("native")
        if raw_flags & 2:
            flags.append("plugin")
        return name or ("anonymous#%d" % fid), site, ",".join(flags) or "void"

    rows = []
    plugin_us = 0.0
    for fid, entry in agg.items():
        name, site, flags = fn_name(fid)
        if "plugin" in flags:
            plugin_us += entry["self"]
            continue  # agent machinery excluded from ranking, total on the verdict line
        caller_name = "void"
        if entry["caller"] is not None:
            caller_name, _, _ = fn_name(entry["caller"])
        rows.append((entry["self"] / 1000.0, entry["total"] / 1000.0, name, site, caller_name, flags))
    rows.sort(key=lambda r: -r[0])

    start_ms = data.get("SessionStartTime") or 0
    end_ms = data.get("SessionEndTime") or 0
    duration_ms = max(0, int(end_ms) - int(start_ms))
    samples = len(nodes)
    print(
        "luau_hotspot: MEASURED %s %dms %d samples %.0fms plugin excluded"
        % (label, duration_ms, samples, plugin_us / 1000.0)
    )
    print()
    for self_ms, total_ms, name, site, caller, flags in rows[:25]:
        print("%s|%.1f|%.1f|%s|%s|%s" % (name, self_ms, total_ms, site, caller, flags))
    return 0


def main(argv):
    root = os.getcwd()
    if not argv:
        print(__doc__.strip())
        return 0
    if argv[0] == "--emit-harness":
        side = argv[1] if len(argv) > 1 else "server"
        seconds = 3
        frequency = 1000
        for i, a in enumerate(argv):
            if a == "--seconds" and i + 1 < len(argv):
                seconds = float(argv[i + 1])
            if a == "--frequency" and i + 1 < len(argv):
                frequency = min(10000, max(1, int(argv[i + 1])))
        emit_harness(side, seconds, frequency)
        return 0
    if argv[0] == "--from-json":
        code = 0
        for path in argv[1:]:
            if path.startswith("--"):
                continue
            rc = analyze(path, root)
            code = max(code, rc)
        return code
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as e:
        sys.stderr.write("luau_hotspot: CRASH %s: %s - nothing was analyzed\n" % (type(e).__name__, e))
        sys.exit(2)
