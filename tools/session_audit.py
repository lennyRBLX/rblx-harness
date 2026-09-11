#!/usr/bin/env python3
"""Audit local Codex rollouts without executing transcript contents.

Counts are unique outer tool calls (an exec batch counts once). Categories
are exclusive, first matching rule wins. Token estimates cover visible call
and result characters / 4, rounded up; they are not billed token usage.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re


RULES = [
    ("Edits and patch generation", r"apply_patch|\.write_text\(|\.write_bytes\("),
    ("Studio execution", r"execute_luau|studio_rpc|boot_smoke"),
    ("Studio output and state", r"get_console_output|get_studio_state|list_roblox_studios|screen_capture|inspect_instance|search_game_tree"),
    ("API and type evidence", r"api_dump\.py|type_lookup\.py|web__run|web\.run"),
    ("Validation and build", r"run_verify\.py|lint_driver|style_assess|deny_scan|luau-lsp|luau-analyze|\bpytest\b|\bunittest\b|argon (?:build|sourcemap)|project_gate\.py|compileall|py_compile"),
    ("Rules and skill retrieval", r"(?:cat|sed|read_text|rg)[\s\S]*(?:CORE\.md|SKILL\.md|AGENTS\.md|references/engine\.md|HANDOFF\.md)"),
    ("Git inspection", r"git\s+(?:diff|status|show|log|ls-files|rev-parse)\b"),
    ("Source retrieval and search", r"\b(?:cat|sed|rg|grep|head|tail)\b|read_text\(|get_symbols_overview|find_symbol"),
    ("Agent dispatch and messages", r"spawn_agent|send_message|followup_task|interrupt_agent"),
    ("Waits and status checks", r"wait_agent|list_agents|write_stdin|\bsleep\b|^wait\s"),
]
CIPHER = re.compile(r"gAAAAA[A-Za-z0-9_=-]{60,}")


def visible(value):
    if isinstance(value, str):
        return CIPHER.sub("", value)
    if isinstance(value, list):
        return "\n".join(visible(item) for item in value)
    if isinstance(value, dict):
        if value.get("type") in ("encrypted_content", "image", "input_image", "audio"):
            return ""
        return "\n".join(visible(v) for k, v in value.items()
                         if k not in ("encrypted_content", "data", "image_url"))
    return ""


def classify(name, arguments):
    text = name + " " + visible(arguments)
    return next((label for label, pattern in RULES if re.search(pattern, text, re.I)), "Other tool work")


def matches(meta, project):
    cwd = Path(meta.get("cwd") or "/")
    if "/" in project or "\\" in project:
        return cwd == Path(project).expanduser().resolve()
    remote = meta.get("git", {}).get("repository_url", "").removesuffix(".git").rstrip("/")
    return cwd.name.casefold() == project.casefold() or remote.rsplit("/", 1)[-1].casefold() == project.casefold()


def audit(codex_home, project):
    inventory, scan_errors = [], []
    for folder in ("sessions", "archived_sessions"):
        for path in sorted((codex_home / folder).rglob("*.jsonl")):
            try:
                with path.open(encoding="utf-8") as stream:
                    first = json.loads(next(stream))
                    if not isinstance(first, dict) or first.get("type") != "session_meta":
                        raise ValueError("missing session metadata")
                    meta = first.get("payload", {})
                    if not isinstance(meta, dict) or not isinstance(meta.get("id"), str) or not meta["id"]:
                        raise ValueError("missing session ID")
                inventory.append((path, meta))
            except (OSError, ValueError, StopIteration) as error:
                scan_errors.append({"file": str(path.relative_to(codex_home)), "error": type(error).__name__})
    selected = {m.get("id") for _, m in inventory if matches(m, project)}
    # Include descendant sessions whose cwd moved during the task.
    while True:
        children = {m.get("id") for _, m in inventory if m.get("parent_thread_id") in selected}
        if children <= selected:
            break
        selected |= children
    calls, outputs, usage, sessions = {}, {}, {}, []
    duplicate_calls = 0
    for path, meta in inventory:
        if meta.get("id") not in selected:
            continue
        raw = path.read_bytes()
        session = {"id": meta.get("id"), "parent": meta.get("parent_thread_id"),
                   "source": str(path.relative_to(codex_home)), "sha256": hashlib.sha256(raw).hexdigest(),
                   "bytes": len(raw), "started": meta.get("timestamp"), "malformed_lines": 0,
                   "usage_records": 0, "legacy_usage_seen": False}
        sessions.append(session)
        for line_number, line in enumerate(raw.splitlines(), 1):
            try:
                record = json.loads(line)
            except ValueError:
                session["malformed_lines"] += 1
                continue
            payload = record.get("payload", {})
            kind = payload.get("type")
            if record.get("type") == "token_usage_record":
                # Inherited records carry the originating thread ID.
                key = payload.get("response_id")
                if key and key not in usage and payload.get("thread_id") in selected:
                    usage[key] = payload.get("usage", {})
                    session["usage_records"] += 1
            if kind == "token_count":
                session["legacy_usage_seen"] = True
            if record.get("type") != "response_item":
                continue
            key = payload.get("call_id") or payload.get("id")
            if kind in ("function_call", "custom_tool_call"):
                if not key:
                    key = hashlib.sha256(line).hexdigest()
                if key in calls:
                    duplicate_calls += 1
                    continue
                arguments = payload.get("arguments", payload.get("input", ""))
                name = payload.get("name", "unknown")
                text = visible(arguments)
                fingerprint = hashlib.sha256((name + "\n" + str(arguments)).encode()).hexdigest()
                calls[key] = {"call_id": key, "session": meta.get("id"), "source": session["source"], "line": line_number,
                              "tool": name, "category": classify(name, arguments),
                              "input_chars": len(text), "fingerprint": fingerprint,
                              "opaque": bool(CIPHER.search(str(arguments)))}
            elif kind in ("function_call_output", "custom_tool_call_output") and key:
                outputs[key] = max(outputs.get(key, 0), len(visible(payload.get("output", ""))))
    groups, repeated = defaultdict(list), defaultdict(list)
    for call in calls.values():
        call["output_chars"] = outputs.get(call["call_id"], 0)
        call["estimated_tokens"] = (call["input_chars"] + call["output_chars"] + 3) // 4
        groups[call["category"]].append(call)
        repeated[call["fingerprint"]].append(call)
    categories = []
    for label, rows in groups.items():
        categories.append({"work": label, "count": len(rows),
                           "estimated_tokens": sum(r["estimated_tokens"] for r in rows),
                           "sessions": len({r["session"] for r in rows}),
                           "examples": sorted(rows, key=lambda r: -r["estimated_tokens"])[:3]})
    totals = Counter()
    for value in usage.values():
        totals.update({k: v for k, v in value.items() if isinstance(v, int)})
    return {"schema": "harness-session-audit-v1", "project": project,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "method": "Unique outer calls; exec batches count once; first matching category. Visible characters/4 rounded up per call, excluding ciphertext and media. Estimates exclude reasoning, hidden context and repeated cached inputs. Recorded usage is deduplicated by response_id; legacy counters are not added.",
            "coverage": {"session_files": len(sessions), "session_ids": len(selected),
                         "root_sessions": len({s["id"] for s in sessions if not s["parent"]}),
                         "agent_sessions": len({s["id"] for s in sessions if s["parent"]}),
                         "archived_files": sum(s["source"].startswith("archived_sessions/") for s in sessions),
                         "unique_calls": len(calls), "copied_calls_removed": duplicate_calls,
                         "calls_missing_output": sum(c["call_id"] not in outputs for c in calls.values()),
                         "opaque_calls": sum(c["opaque"] for c in calls.values()),
                         "usage_responses": len(usage), "inventory_errors": scan_errors},
            "recorded_usage": dict(totals), "categories": categories,
            "identical_calls": sorted([
                {"fingerprint": key, "count": len(rows), "repeat_count": len(rows) - 1,
                 "work": rows[0]["category"], "estimated_tokens": sum(r["estimated_tokens"] for r in rows),
                 "examples": rows[:3]}
                for key, rows in repeated.items() if len(rows) > 1], key=lambda r: (-r["count"], r["fingerprint"])),
            "sessions": sessions}


def markdown(report):
    c = report["coverage"]
    lines = ["# Arena session audit" if report["project"] == "arena" else "# Session audit", "",
             f"Snapshot: {report['created_utc']}", "", report["method"], "",
             f"Reviewed {c['session_files']} files for {c['session_ids']} sessions ({c['root_sessions']} roots, {c['agent_sessions']} agents; {c['archived_files']} archived files), "
             f"{c['unique_calls']} unique call batches. Removed {c['copied_calls_removed']} copied calls. "
             f"{c['opaque_calls']} calls contain unreadable encrypted text; {c['calls_missing_output']} have no recorded result.", ""]
    lines += [f"Inventory errors: {len(c['inventory_errors'])}; malformed lines in selected files: "
              f"{sum(s['malformed_lines'] for s in report['sessions'])}.", ""]
    for label, field in (("Count: highest to lowest", "count"), ("Estimated token cost: highest to lowest", "estimated_tokens")):
        lines += ["## " + label, "", "| Repeated work | Count | Estimated tokens | Sessions |",
                  "|---|---:|---:|---:|"]
        for row in sorted(report["categories"], key=lambda r: (-r[field], r["work"])):
            lines.append(f"| {row['work']} | {row['count']:,} | {row['estimated_tokens']:,} | {row['sessions']} |")
        lines.append("")
    lines += ["## Recorded model usage", "", f"{c['usage_responses']:,} unique response usage records: `" +
              json.dumps(report["recorded_usage"], sort_keys=True) + "`.", "",
              "Cached input is part of input; reasoning output is part of output. Do not add either twice. "
              "These totals are not attributed to work categories. Sessions with only legacy counters or encrypted work have incomplete accounting.", "",
              "## Exact repeated calls", "", "Identical call name and arguments; repetition may be needed after state changes.", "",
              "| Work | Total | Repeats after first | Estimated tokens | Evidence (session / line) |",
              "|---|---:|---:|---:|---|"]
    for row in report["identical_calls"][:20]:
        example = row["examples"][0]
        lines.append(f"| {row['work']} | {row['count']} | {row['repeat_count']} | {row['estimated_tokens']:,} | {example['session']} / {example['line']} |")
    lines += ["", "The adjacent JSON records every selected session, its content hash, category evidence, and all exact-repeat groups. "
              "Call counts identify repeated activity, not proven redundant work. No claimed token savings have been measured.", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="project directory or exact basename/remote name")
    parser.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--output", type=Path, required=True, help="output stem for .json and .md")
    args = parser.parse_args(argv)
    report = audit(args.codex_home.expanduser(), args.project)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    print(json.dumps(report["coverage"], separators=(",", ":")))
    return 0 if report["coverage"]["session_files"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
