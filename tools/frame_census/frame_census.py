#!/usr/bin/env python3
"""frame_census — reads a MicroProfiler capture: the three exports sharing the
dump's stem. Never the HTML — its payload is an undocumented binary format
and nothing recovers numbers from it.

  frame_census <stem-or-any-of-the-trio> [--root DIR] [--downloads DIR]

The trio: <stem>.csv, <stem>_counters.csv, <stem>_summary.json, found in
~/Downloads when a bare stem is given. A missing anchor is exit 3, never a
parse. The dump's general_info.PlaceId is a free wrong-place check, applied
before analysing a word of it.

Five parse rules, each of which produces fiction if skipped:
  1 $-families are a viewer bug — collapse and recompute from the detail log
  2 never rank containers
  3 de-duplicate bare and suffixed job pairs
  4 rank by exclusive time
  5 thread class matters — worker width is occupancy, not critical path

Exit 0 measured, with OPT5 threshold notes when present · 3 environment.
Columns are asserted on ingest and differ -> exit 3: there is no official
schema to pin, so the only defensible posture is to fail loudly on a shape
change rather than parse it into fiction.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scope_table  # noqa: E402

EXPORT_HELP = (
    "export summary.json + counters.csv + csv from the web UI: open the dump "
    "in the browser, use the flame-graph Export menu - Summary JSON, Counters "
    "CSV, Timeline CSV save to Downloads beside the dump"
)


def env_fail(cause, remedy):
    print("ENV|%s|%s" % (cause, remedy))
    sys.exit(3)


def find_trio(arg, downloads):
    stem = arg
    for suffix in (".csv", "_counters.csv", "_summary.json"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    candidates = [stem, os.path.join(downloads, os.path.basename(stem))]
    for base in candidates:
        trio = (base + ".csv", base + "_counters.csv", base + "_summary.json")
        if all(os.path.isfile(p) for p in trio):
            return trio
    missing = [base + s for base in candidates[:1] for s in (".csv", "_counters.csv", "_summary.json") if not os.path.isfile(base + s)]
    env_fail("html-binary-format", EXPORT_HELP + " (missing: %s)" % ", ".join(os.path.basename(m) for m in missing))


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


def load_summary(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        env_fail("summary-unparseable", str(e))
    for anchor in ("num_frames", "cpu_time_median"):
        if anchor not in data:
            env_fail("summary-shape-changed", "missing %s - schema drifted, refusing to parse fiction" % anchor)
    return data


def load_counters(path):
    counters = {}
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as e:
        env_fail("counters-unreadable", str(e))
    if not lines or "Name" not in lines[0] or "Value" not in lines[0]:
        env_fail("counters-shape-changed", "header is not Name, Value, Limit - refusing to parse fiction")
    for line in lines[1:]:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2 and parts[0]:
            try:
                counters[parts[0]] = float(parts[1])
            except ValueError:
                pass
    return counters


def load_timeline(path):
    """The multi-section CSV: aggregates up to the first Thread Name: marker,
    then the per-marker detail log — the primary source, not a correction
    pass. Stopping at the first marker loses the only trustworthy data."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        env_fail("csv-unreadable", str(e))
    lines = text.splitlines()
    frames = None
    groups = []  # (group, average, max, total)
    scopes = []  # (name, average, max, total) from aggregate section
    detail = []  # (group, marker, begin, end, labels)
    thread_seen = False
    section = None
    for line in lines:
        cells = [c.strip() for c in line.split(",")]
        if not cells or not cells[0]:
            continue
        if cells[0] == "frames" and len(cells) >= 2:
            try:
                frames = int(cells[1])
            except ValueError:
                pass
            continue
        if cells[0].startswith("Thread Name:"):
            thread_seen = True
            continue
        if thread_seen:
            # detail rows: Group Name, Marker Name, Begin, End, Labels...
            if cells[0] in ("Group Name", "group"):
                continue
            if len(cells) >= 4:
                try:
                    begin, end = float(cells[2]), float(cells[3])
                except ValueError:
                    continue
                labels = ",".join(cells[4:]) if len(cells) > 4 else ""
                detail.append((cells[0], cells[1], begin, end, labels))
            continue
        if cells[0] == "group" and len(cells) >= 4:
            section = "group" if cells[1] == "average" else "groupthread"
            continue
        if cells[0] in ("frametimecpu", "frametimegpu", "Frame"):
            section = None
            continue
        if section == "group" and len(cells) >= 4:
            try:
                groups.append((cells[0], float(cells[1]), float(cells[2]), float(cells[3])))
            except ValueError:
                pass
            continue
        # aggregate scope rows: name,average,max,total (any other numeric row)
        if len(cells) >= 4:
            try:
                scopes.append((cells[0], float(cells[1]), float(cells[2]), float(cells[3])))
            except ValueError:
                pass
    if frames is None and not detail and not scopes:
        env_fail("csv-shape-changed", "no frames anchor, no sections - refusing to parse fiction")
    return frames, groups, scopes, detail


def main(argv):
    root = os.getcwd()
    downloads = os.path.expanduser("~/Downloads")
    args = []
    i = 0
    while i < len(argv):
        if argv[i] == "--root" and i + 1 < len(argv):
            root = argv[i + 1]
            i += 2
        elif argv[i] == "--downloads" and i + 1 < len(argv):
            downloads = argv[i + 1]
            i += 2
        else:
            args.append(argv[i])
            i += 1
    if not args:
        print(__doc__.strip())
        return 0

    csv_path, counters_path, summary_path = find_trio(args[0], downloads)
    summary = load_summary(summary_path)
    counters = load_counters(counters_path)
    frames, groups, scopes, detail = load_timeline(csv_path)

    # wrong-place check before analysing a word of it
    place_id = (summary.get("general_info") or {}).get("PlaceId")
    mapping = read_places_map(root)
    if place_id is not None and mapping and int(place_id) not in mapping.values():
        env_fail("wrong-place", "dump names place %s, this project targets %s" % (place_id, sorted(mapping.values())))

    findings = []

    # OPT5 thresholds, read from structured fields — the tool names which
    # threshold tripped; the finding cites the one id
    gpu_wait = None
    for name, avg, mx, total in scopes:
        if name in ("waitOnGpu", "GPU Wait", "waitUntilCompleted"):
            gpu_wait = max(gpu_wait or 0.0, avg)
    if gpu_wait is not None and gpu_wait > 2.5:
        findings.append("0|0|OPT5|GPU Wait %.1fms|>2.5ms, frame is GPU-bound" % gpu_wait)
    mem_total = counters.get("/memory/total")
    if mem_total is not None:
        gb = mem_total / (1024.0 ** 3) if mem_total > 1024 ** 2 else mem_total
        if gb > 1.3:
            findings.append("0|0|OPT5|/memory/total %.2fgb|>1.3gb, Android crash line" % gb)
    for name, avg, mx, total in scopes:
        if name.startswith("updateInvalidatedFastClusters") and mx > 4.0:
            findings.append("0|0|OPT5|updateInvalidatedFastClusters %.1fms|>4ms, avatar/MeshPart churn" % mx)
            break

    # OPT4: the frame budget, pre-computed by the summary
    median = summary.get("cpu_time_median")
    verdict_bits = []
    if median is not None:
        verdict_bits.append("median %.1fms vs 16.7ms budget" % float(median))
    jobs_heavy = summary.get("num_frames_jobs_heavy", 0) or 0
    render_heavy = summary.get("num_frames_rendering_heavy", 0) or 0
    gpu_heavy = summary.get("num_frames_gpu_heavy", 0) or 0
    total_frames = summary.get("num_frames", 0) or 0
    bottleneck = "balanced"
    peak = max(jobs_heavy, render_heavy, gpu_heavy)
    if peak > 0:
        if peak == gpu_heavy:
            bottleneck = "gpu-bound"
        elif peak == render_heavy:
            bottleneck = "render-bound"
        else:
            bottleneck = "jobs-bound"
    verdict_bits.append("%d/%d heavy frames, %s" % (peak, total_frames, bottleneck))

    # the detail log: recompute per-marker totals the $-family clone destroyed
    per_marker = {}
    ui_rows = {}
    bridge_rows = {}
    for group, marker, begin, end, labels in detail:
        dur = max(0.0, end - begin)
        base = marker
        for fam in scope_table.DOLLAR_FAMILIES:
            bare = fam[1:]
            if marker.startswith(bare + "_"):
                base = marker
                break
        entry = per_marker.setdefault(base, {"group": group, "total": 0.0, "count": 0, "max": 0.0})
        entry["total"] += dur
        entry["count"] += 1
        entry["max"] = max(entry["max"], dur)
        if group == "UI" and marker == "Layout":
            m = re.search(r"Root=(\S+)", labels)
            root_name = m.group(1) if m else "unknown"
            row = ui_rows.setdefault(root_name, {"total": 0.0, "relayouts": 0, "updates": 0, "resizes": 0})
            row["total"] += dur
            for field, key in (("Relayouts", "relayouts"), ("Updates", "updates"), ("Resizes", "resizes")):
                fm = re.search(field + r"=(\d+)", labels)
                if fm:
                    row[key] += int(fm.group(1))
        if group == "LuaBridge":
            cls = labels.split(",")[0].strip() if labels else "void"
            row = bridge_rows.setdefault((marker, cls), {"total": 0.0, "count": 0})
            row["total"] += dur
            row["count"] += 1

    # rank by exclusive-ish time from the detail markers: containers, idle,
    # dollar-family aggregates and worker occupancy excluded
    ranked = []
    for marker, entry in per_marker.items():
        if marker in scope_table.CONTAINERS or marker in scope_table.EXCLUDED_IDLE:
            continue
        if any(marker == f or marker == f[1:] for f in scope_table.DOLLAR_FAMILIES):
            continue
        if marker in scope_table.WORKER_CLASS:
            continue
        base = re.sub(r"\(.*\)$", "", marker)
        if base != marker and base in per_marker:
            continue  # de-duplicate bare and suffixed job pairs
        spike = entry["max"] / (entry["total"] / entry["count"]) if entry["count"] and entry["total"] else 0.0
        ranked.append((entry["total"], spike, marker, entry))
    ranked.sort(key=lambda x: -x[0])

    print("frame_census: %s" % ("NOTED" if findings else "MEASURED"))
    print()
    for f in findings:
        print(f)
    if findings:
        print()
    print("verdict|%s" % "|".join(verdict_bits))
    excluded = sorted(set(per_marker) & (scope_table.EXCLUDED_IDLE | scope_table.CONTAINERS))
    if excluded:
        print("excluded|%s|idle and containers reported, never ranked" % ",".join(excluded[:12]))
    for total, spike, marker, entry in ranked[:15]:
        group, cause, remedy = scope_table.lookup(marker)
        spike_note = "spike x%.0f" % spike if spike >= 8 else "%d calls" % entry["count"]
        print("scope|%s|%s|%.3fms|%s|%s" % (marker, entry.get("group") or group, total, spike_note, remedy))
    for root_name, row in sorted(ui_rows.items(), key=lambda kv: -kv[1]["total"])[:5]:
        print("ui|%s|%.3f|%d relayouts, %d updates, %d resizes" % (root_name, row["total"], row["relayouts"], row["updates"], row["resizes"]))
    for (marker, cls), row in sorted(bridge_rows.items(), key=lambda kv: -kv[1]["total"])[:8]:
        print("bridge|%s|%s|%.3f|%d writes" % (marker, cls, row["total"], row["count"]))
    # counters are session-scoped, not per-frame — never divided by frames
    for cname in ("/Raycasts", "/memory/total", "/instance_count/total"):
        if cname in counters:
            print("counter|%s|%s|session-scoped, never per-frame" % (cname, counters[cname]))

    # the stamp done-gate's OPT1 check reads: this stem was analyzed
    try:
        import time

        cache = os.path.expanduser("~/.cache/harness")
        os.makedirs(cache, exist_ok=True)
        stem = os.path.basename(csv_path)[: -len(".csv")]
        with open(os.path.join(cache, "frame_census.last"), "a", encoding="utf-8") as f:
            f.write("%s|%f\n" % (stem, time.time()))
    except OSError:
        pass

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as e:
        sys.stderr.write("frame_census: CRASH %s: %s - nothing was analyzed\n" % (type(e).__name__, e))
        sys.exit(2)
