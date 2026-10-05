#!/usr/bin/env python3
"""Read saved HTML through the bounded viewer adapter or historical native exports.
HTML statistics require selected workload markers and actual event coverage.
Native CSV reports inclusive event costs only; rolling aggregates are not combined.
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
    env_fail("native-exports-missing", EXPORT_HELP + " (missing: %s)" % ", ".join(os.path.basename(m) for m in missing))


def read_places_map(root):
    mapping = {}
    agents_md = os.path.join(root, "AGENTS.md")
    if os.path.exists(agents_md):
        with open(agents_md, encoding="utf-8") as f:
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
    import argparse
    import tempfile
    from pathlib import Path
    from capture import analyze, export_html, render
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture")
    parser.add_argument("--root", default=os.getcwd())
    parser.add_argument("--downloads", default=os.path.expanduser("~/Downloads"))
    parser.add_argument("--place")
    parser.add_argument("--marker", action="append", default=[])
    parser.add_argument("--coverage", choices=["sample", "full"], default="sample")
    parser.add_argument("--min-frames", type=int, default=1)
    parser.add_argument("--expected-frames", type=int)
    parser.add_argument("--spike-ms", type=float, default=20)
    parser.add_argument("--node", default="node")
    args = parser.parse_args(argv)
    if args.capture.endswith(".html") or args.capture.endswith("viewer-data.json"):
        if not args.marker or not args.place:
            env_fail("window-required", "supply --place and --marker; select sample or full coverage")
        with tempfile.TemporaryDirectory(prefix="harness-viewer-") as temp:
            path = Path(args.capture)
            if path.suffix == ".html":
                path = export_html(path, Path(temp), args.node)
            reports = analyze(json.loads(path.read_text()), args.place, args.marker, args.coverage,
                              args.min_frames, args.expected_frames, args.spike_ms)
            print(render(reports))
        return 0
    csv_path, counters_path, summary_path = find_trio(args.capture, args.downloads)
    summary = load_summary(summary_path)
    load_counters(counters_path)  # Retained native reader; session counters are not window costs.
    _, _, _, detail = load_timeline(csv_path)
    place_id = (summary.get("general_info") or {}).get("PlaceId")
    wanted = {int(args.place)} if args.place else set(read_places_map(args.root).values())
    if wanted and (place_id is None or int(place_id) not in wanted):
        env_fail("wrong-place", "supply the matching native exports")
    if args.coverage == "full":
        env_fail("coverage-unavailable", "native timeline has no workload indices; use saved HTML event arrays")
    import math
    rows = {}
    for group, marker, begin, end, _labels in detail:
        if not math.isfinite(begin) or not math.isfinite(end) or end < begin:
            raise ValueError("invalid event duration")
        if args.marker and marker not in args.marker:
            continue
        values = rows.setdefault((group, marker), [])
        values.append(end - begin)
    if not rows:
        env_fail("missing-events", "native exports contain no selected event details")
    print("PROFILE|native-event-window|inclusive scopes")
    for (group, marker), values in sorted(rows.items(), key=lambda row: -sum(row[1]))[:15]:
        print("scope|%s|%s|average=%.3fms|calls=%d|total=%.3fms|spikes=%d max=%.3fms" %
              (marker, group, sum(values)/len(values), len(values), sum(values),
               sum(v > args.spike_ms for v in values), max(values)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (ValueError, OSError) as error:
        print("PROFILE|rejected|" + str(error))
        sys.exit(2)
