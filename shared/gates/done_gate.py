#!/usr/bin/env python3
"""Pre-final validator and fast Stop receipt gate for a settled change set."""

import argparse
import glob
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gatelib  # noqa: E402
import write_gate  # noqa: E402
from source_fix.source_fix import fix_file as fix_source_file  # noqa: E402
from type_cache.type_cache import CacheError  # noqa: E402
from type_core import metadata_for_path, parse_declarations  # noqa: E402
from type_lookup.type_lookup import affected as affected_consumers, execute as type_lookup_execute  # noqa: E402

TOOLS = gatelib.TOOLS
INCOMPLETE_AGENT_VERDICTS = frozenset(("MISS", "WAITING", "ENV"))
AGENT_VERDICT_RE = re.compile(r"^(reviewer|debugger|optimizer|researcher|maintainer): ([A-Z]+)$")


def run_tool(cmd, timeout=300):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        class R:
            returncode = 2
            stdout = ""
            stderr = "tool crashed: %s" % e

        return R()


FINDING_RE = re.compile(r"^(\d+)\|(\d+)\|([^|]+)\|([^|]*)\|(.*)$")


def collect_required_result(result, checker, findings, output="stderr"):
    """Collect hard records and auto-fix records left after a failed repair."""
    text = getattr(result, output, "") or ""
    parsed = 0
    blocking = 0
    for line in text.splitlines():
        match = FINDING_RE.match(line)
        if not match:
            continue
        parsed += 1
        disposition = gatelib.rule_policy.disposition(match.group(3))
        if disposition == "hard" or (result.returncode != 0 and disposition == "auto-fix"):
            findings.append(line)
            blocking += 1
    if (result.returncode not in (0, 2) and not blocking) or (result.returncode == 2 and not parsed):
        detail = (result.stderr or result.stdout or "no diagnostic").strip().replace("|", "/")[:160]
        findings.append(
            "0|0|GATE4|required checker %s failed|%s" % (checker, detail)
        )


def changed_luau(cwd, session_id):
    """Return the current session's Lua/Luau target and target validity."""
    turn = gatelib.read_turn_record(cwd, session_id)
    digest, files = gatelib.review_target(cwd, turn)
    if turn and digest:
        return turn["head"], files, turn, True
    return (turn["head"] if turn else "HEAD"), [], turn, not bool(turn)


def unauthorized_stop_has_source_work(cwd, session_id):
    """Keep the no-write startup anti-loop, but never waive worked-on source."""
    turn = gatelib.read_turn_record(cwd, session_id)
    if not turn:
        return False, ""
    try:
        changed = gatelib.changed_paths_since_turn(cwd, turn)
    except OSError as error:
        return True, "turn diff unavailable: %s" % str(error)[:160]
    source_changed = any(path.endswith((".lua", ".luau")) for path in changed)
    mutation_started = os.path.exists(gatelib.mutation_check_path(cwd, session_id))
    if source_changed:
        return True, "Lua/Luau source changed in this turn"
    if mutation_started:
        return True, "source mutation began before authorization changed"
    return False, ""


def agent_result_verdict(entry):
    result = entry.get("result")
    first_line = result.split("\n", 1)[0] if isinstance(result, str) else ""
    match = AGENT_VERDICT_RE.fullmatch(first_line)
    if not match or match.group(1) != entry.get("agent_type"):
        return None
    return match.group(2)


def check_agent_mailbox(cwd, session_id):
    if not session_id:
        return None
    entries = [
        entry
        for entry in gatelib.agent_mailbox_entries(cwd, session_id)
        if entry.get("agent_type") != "reviewer"
    ]
    active = [
        entry
        for entry in entries
        if entry.get("state") in ("pending", "overlap", "recovering")
    ]
    if active:
        overlap = [entry for entry in active if entry.get("state") == "overlap" or entry.get("overlap")]
        if overlap:
            ids = ", ".join(str(entry.get("agent_id", "unknown")) for entry in overlap)
            return "agent-mailbox: writers ran concurrently: %s" % ids
        ids = ", ".join(str(entry.get("agent_id", "unknown")) for entry in active)
        return "agent-mailbox: join & ack: %s" % ids
    done = [entry for entry in entries if entry.get("state") == "done"]
    if not done:
        return None
    conflicted = [entry for entry in done if entry.get("overlap")]
    if conflicted:
        ids = ", ".join(str(entry.get("agent_id", "unknown")) for entry in conflicted)
        return "agent-mailbox: concurrent writer return cannot be consumed or acknowledged: %s" % ids
    incomplete = []
    for entry in done:
        verdict = agent_result_verdict(entry)
        if verdict is None or verdict in INCOMPLETE_AGENT_VERDICTS:
            incomplete.append((entry, verdict or "UNVERIFIED"))
    if incomplete:
        notes = []
        for entry, verdict in incomplete:
            notes.append(
                "%s %s\n\n%s"
                % (entry.get("agent_id", "unknown"), verdict, entry.get("result", ""))
            )
            gatelib.agent_mailbox_write(
                cwd,
                session_id,
                entry.get("agent_id", "unknown"),
                state="acked",
            )
        gatelib.emit_json({"systemMessage": "\n\n".join(notes)})
        return (
            "agent-mailbox: delivered %d incomplete return(s); perform the named evidence or human route"
            % len(incomplete)
        )
    notes = []
    for entry in done:
        notes.append("agent-mailbox: %s\n\n%s" % (entry.get("agent_id", "unknown"), entry.get("result", "")))
        gatelib.agent_mailbox_write(cwd, session_id, entry.get("agent_id", "unknown"), state="acked")
    gatelib.emit_json({"systemMessage": "\n\n".join(notes)})
    return "agent-mailbox: delivered %d return(s); resume route" % len(done)


def source_at(cwd, reference, relative):
    rc, source, _ = gatelib.git(cwd, "show", "%s:%s" % (reference, relative))
    return source + ("\n" if source and not source.endswith("\n") else "") if rc == 0 else ""


def declaration_map(cwd, path, source):
    metadata = metadata_for_path(cwd, os.path.join(cwd, path))
    if metadata is None:
        return {}
    return {
        (metadata["path"], declaration.name): declaration.fingerprint
        for declaration in parse_declarations(source or "")
    }


def type_write_provenance(cwd, session_id, reference, changed):
    records = gatelib.current_type_records(cwd, session_id, "type-write")
    written = set()
    operations = set()
    moved_sources = set()
    for record in records:
        for item in record.get("definitions", []):
            written.add((item.get("path"), item.get("definition")))
        for item in record.get("operations", []):
            operations.add((item.get("path"), item.get("type_name"), item.get("outcome")))
            if item.get("outcome") == "moved" and item.get("source_path"):
                moved_sources.add((item.get("source_path"), item.get("type_name")))
    findings = []
    for relative in changed:
        path = os.path.join(cwd, relative)
        try:
            with open(path, encoding="utf-8") as handle:
                current_source = handle.read()
        except OSError:
            current_source = ""
        before = declaration_map(cwd, relative, source_at(cwd, reference, relative))
        current = declaration_map(cwd, relative, current_source)
        for key in sorted(set(before) | set(current)):
            if before.get(key) == current.get(key):
                continue
            if key in current and (key[0], current[key]) in written:
                continue
            if key not in current and (
                key in moved_sources or (key[0], key[1], "deleted") in operations
            ):
                continue
            findings.append(
                "0|0|TYPE8|%s.%s changed without matching type_write output|apply the declaration change through type_write"
                % (key[0], key[1])
            )
    return findings


def final_type_checks(cwd, session_id, reference, changed, index):
    findings = []
    for relative in changed:
        path = os.path.join(cwd, relative)
        try:
            with open(path, encoding="utf-8") as handle:
                current = handle.read()
        except OSError:
            current = ""
        before = source_at(cwd, reference, relative)
        checks = []
        checks += write_gate.check_external_types(path, before, current, cwd, session_id, index)
        checks += write_gate.check_data37(path, before, current, index, cwd)
        checks += write_gate.check_type7_surface(path, before, current, cwd, session_id, index)
        for _, line, col, rule, subject, remedy in checks:
            findings.append("%d|%d|%s|%s|%s" % (line, col, rule, subject, remedy))
    return findings


def validation_payload(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--root", required=True)
    parser.add_argument("--session", required=True)
    args = parser.parse_args(argv)
    cwd = os.path.realpath(args.root)
    authorization = gatelib.read_session_authorization(cwd, args.session)
    turn = gatelib.read_turn_record(cwd, args.session)
    if not isinstance(authorization, dict) or not gatelib.session_authorized(cwd, args.session):
        raise ValueError("current session authorization is unavailable")
    if not isinstance(turn, dict) or not str(turn.get("turn_id") or "").strip():
        raise ValueError("current turn identity is unavailable")
    host = authorization.get("host")
    if host not in ("codex", "claude"):
        raise ValueError("current hook host is unavailable")
    payload = {
        "cwd": cwd,
        "hook_event_name": "Stop",
        "session_id": args.session,
        "turn_id": str(turn["turn_id"]),
        "_harness_host": host,
    }
    if host == "codex":
        payload["permission_mode"] = authorization.get("permission_mode")
    return payload, ["--host", host, "--hook-scope", "project"]


def main(argv=None, payload_override=None, validation_run=False):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--run-validation" in argv:
        validation_run = True
        argv.remove("--run-validation")
    if "--validate" in argv and payload_override is None:
        try:
            payload, hook_argv = validation_payload(argv)
        except (SystemExit, ValueError) as error:
            detail = str(error) if isinstance(error, ValueError) else "invalid validation arguments"
            sys.stderr.write("done-gate: BLOCKED\n\nGATE4|pre-final validation unavailable|%s\n" % detail)
            return 2
        return main(hook_argv, payload_override=payload, validation_run=True)
    if any(argument in ("-h", "--help") for argument in argv):
        print(
            "usage: done_gate.py --validate --root ROOT --session SESSION\n"
            "       done_gate.py --host {codex,claude} "
            "--hook-scope {project,user} < hook-payload.json"
        )
        return 0
    payload = payload_override if payload_override is not None else gatelib.read_payload()
    candidate = payload.get("cwd") if isinstance(payload, dict) else os.getcwd()
    if not gatelib.is_roblox_project(candidate):
        return 0
    if payload is None:
        sys.stderr.write("done-gate: BLOCKED (ENV)\n\nGATE4|malformed Stop payload|nothing was written\n")
        return 2
    cwd = payload.get("cwd") or os.getcwd()
    session_id = payload.get("session_id", "")
    scope = gatelib.hook_scope(argv)
    authorized, detail = gatelib.session_authorization_status(payload, cwd, scope, "Stop")
    if not authorized:
        # SessionStart/UserPromptSubmit deliberately produce one visible
        # remediation reply without granting authorization. Waive Stop only
        # when no source work occurred under the now-invalid envelope.
        worked, work_detail = unauthorized_stop_has_source_work(cwd, session_id)
        if not worked:
            return 0
        sys.stderr.write(
            "done-gate: BLOCKED\n\n"
            "0|0|GATE4|Stop authorization changed after source work: %s|%s\n"
            % (work_detail.replace("|", "/"), detail.replace("|", "/")[:200])
        )
        return 2
    gatelib.cleanup_review_receipts(cwd)
    mailbox_block = check_agent_mailbox(cwd, session_id)
    if mailbox_block:
        sys.stderr.write("done-gate: BLOCKED\n\n%s\n" % mailbox_block)
        return 2
    if gatelib.is_harness(cwd):
        return 0  # the build's own repo carries no game floor

    cached_key = gatelib.stop_cache_key(cwd, session_id)
    if gatelib.stop_cache_hit(cwd, session_id, cached_key):
        if validation_run:
            print("FINALIZED|roblox|cached")
        return 0

    if not validation_run:
        turn = gatelib.read_turn_record(cwd, session_id)
        try:
            changed_paths = gatelib.changed_paths_since_turn(cwd, turn) if turn else []
        except OSError as error:
            sys.stderr.write(
                "done-gate: BLOCKED\n\n"
                "0|0|GATE4|pre-final settled-state check failed|%s\n"
                % str(error)[:160].replace("|", "/")
            )
            return 2
        if not changed_paths:
            gatelib.write_stop_cache(cwd, session_id, cached_key)
            return 0
        sys.stderr.write(
            "done-gate: BLOCKED\n\n"
            "0|0|GATE4|pre-final validation receipt is absent or stale|run before the final response: %s\n"
            % gatelib.finalization_command(cwd, session_id).replace("|", "/")
        )
        return 2

    findings = []
    system_notes = []

    stamp_ref, changed, turn, review_target_valid = changed_luau(cwd, session_id)
    turn_mtime = turn["started_at"] if turn else None
    try:
        changed_paths = gatelib.changed_paths_since_turn(cwd, turn) if turn else []
    except OSError as error:
        changed_paths = []
        findings.append("0|0|GATE4|settled turn diff failed|%s" % str(error)[:160].replace("|", "/"))
    ownership_changed_paths = set(changed_paths)

    # Final remote validation precedes every settled-tree checker. A bounded
    # repair may change HEAD or source bytes; all target, analyzer, and review
    # checks below must observe the post-repair tree.
    source_changed = any(path.endswith((".lua", ".luau")) for path in changed_paths)
    if source_changed and not gatelib.is_harness(cwd):
        state, git_detail = gatelib.gate6_state(cwd, fetch=True)
        if gatelib.gate6_disposition(state) == "repair":
            repaired = run_tool(
                [sys.executable, os.path.join(TOOLS, "git_sync", "git_sync.py"), "repair", "--root", os.path.realpath(cwd)],
                timeout=gatelib.GIT_REPAIR_TIMEOUT,
            )
            if repaired.returncode == 0:
                state, git_detail = gatelib.gate6_state(cwd, fetch=True)
            else:
                git_detail = (repaired.stderr or repaired.stdout or git_detail or "repair failed").strip()[:160]
        disposition = gatelib.gate6_disposition(state)
        if disposition == "advisory":
            system_notes.append(
                "done-gate: NOTED [GATE6] fetch-failed: %s"
                % git_detail.replace("|", "/")[:160]
            )
        elif state != "ok":
            findings.append(
                "0|0|GATE6|%s: %s|%s"
                % (state, git_detail.replace("|", "/")[:160], gatelib.gate6_instruction(cwd, state, git_detail))
            )

        stamp_ref, changed, turn, review_target_valid = changed_luau(cwd, session_id)
        turn_mtime = turn["started_at"] if turn else None
        try:
            changed_paths = gatelib.changed_paths_since_turn(cwd, turn) if turn else []
        except OSError as error:
            changed_paths = []
            review_target_valid = False
            findings.append("0|0|GATE4|post-repair turn diff failed|%s" % str(error)[:160].replace("|", "/"))
        ownership_changed_paths.update(
            path for path in changed_paths if path.endswith((".lua", ".luau"))
        )
        authorized_after, authorization_detail = gatelib.session_authorization_status(
            payload,
            cwd,
            scope,
            "Stop",
        )
        if not authorized_after:
            findings.append(
                "0|0|GATE4|Stop authorization changed during final Git validation|%s"
                % authorization_detail.replace("|", "/")[:200]
            )
    if turn and not review_target_valid:
        findings.append(
            "0|0|GATE4|review target or affected-consumer lookup failed|repair the required target lookup and retry"
        )

    if changed:
        toolchain_error = write_gate.ensure_source_toolchain(cwd)
        if toolchain_error:
            findings.append(
                "0|0|GATE4|required source toolchain unavailable|%s"
                % toolchain_error.replace("|", "/")[:160]
            )
        globals_error = write_gate.ensure_api_globals(cwd)
        if globals_error:
            findings.append(
                "0|0|GATE4|required api_globals repair failed|%s"
                % globals_error.replace("|", "/")[:160]
            )

    # Deterministic source repairs run before the immutable review check.
    # A repair changes the target digest and therefore requires a new receipt.
    for relative in changed:
        path = os.path.join(cwd, relative)
        if not os.path.isfile(path) or os.path.islink(path):
            continue
        _, error = fix_source_file(path, cwd)
        if error:
            findings.append(
                "0|0|GATE4|source auto-fix failed for %s|%s"
                % (relative.replace("|", "/"), error.replace("|", "/")[:160])
            )
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                settled_source = handle.read()
        except OSError:
            settled_source = ""
        settled_role = "debugger" if relative.replace(os.sep, "/").startswith("tests/") else "writer"
        settled_checks = []
        settled_checks += write_gate.check_debug2(path, settled_source, cwd, settled_role)
        settled_checks += write_gate.check_bc1_handler(path, settled_source)
        settled_checks += write_gate.check_data_rules(path, settled_source)
        settled_checks += write_gate.check_payments(path, settled_source)
        for _, line, col, rule, subject, remedy in settled_checks:
            if gatelib.rule_policy.disposition(rule) == "hard":
                findings.append(
                    "%d|%d|%s|%s|%s"
                    % (
                        line,
                        col,
                        rule,
                        subject.replace("|", "/"),
                        remedy.replace("|", "/"),
                    )
                )
        for _, _, _, rule, subject, _ in write_gate.check_bc4(path, settled_source):
            system_notes.append(
                "done-gate: NOTED [%s] %s: %s"
                % (rule, relative, subject)
            )

    type_index = None
    affected = []
    if changed:
        try:
            type_lookup_execute(cwd, [{"scope": "project"}], session_id, record=False)
            from type_cache.type_cache import read as read_type_cache

            type_index = read_type_cache(cwd)
            affected = affected_consumers(cwd, stamp_ref, changed)
            findings.extend(type_write_provenance(cwd, session_id, stamp_ref, changed))
            findings.extend(final_type_checks(cwd, session_id, stamp_ref, changed, type_index))
        except (CacheError, OSError, ValueError, TypeError) as error:
            findings.append("0|0|GATE4|type cache validation failed|%s" % str(error)[:160].replace("|", "/"))

    if changed:
        analysis_files = sorted(set(changed) | set(affected))
        existing = [os.path.join(cwd, f) for f in changed if os.path.exists(os.path.join(cwd, f))]
        analysis_existing = [os.path.join(cwd, f) for f in analysis_files if os.path.exists(os.path.join(cwd, f))]
        if existing:
            # Auto-format, then run each required settled-source checker once.
            style = run_tool(
                [sys.executable, os.path.join(TOOLS, "style_assess", "style_assess.py"), "--fix", "--root", cwd]
                + existing
            )
            collect_required_result(style, "style_assess", findings)
            if style.stdout.strip():
                system_notes.append(style.stdout.strip())

            deny = run_tool(
                [sys.executable, os.path.join(TOOLS, "deny_scan", "deny_scan.py"), "--root", cwd]
                + existing
            )
            collect_required_result(deny, "deny_scan", findings)
            if deny.stdout.strip():
                system_notes.append(deny.stdout.strip())

            replication = run_tool(
                [sys.executable, os.path.join(TOOLS, "replication_audit", "replication_audit.py"), "--root", cwd]
                + existing
            )
            collect_required_result(replication, "replication_audit", findings)
            if replication.stdout.strip():
                system_notes.append(replication.stdout.strip())

            for path in existing:
                data = run_tool(
                    [gatelib.LUTE, "run", os.path.join(TOOLS, "data_check", "data_check.luau"), "--static", path]
                )
                collect_required_result(data, "data_check", findings, output="stdout")

            r = run_tool([sys.executable, os.path.join(TOOLS, "perf_audit", "perf_audit.py"), "--root", cwd] + existing)
            if r.returncode == 0 and r.stdout.strip():
                system_notes.append(r.stdout.strip())  # advisory, never a block

            # luau-lsp analyze under the project's .luaurc — exits 0 on
            # lint-severity findings, so scan for path(line,col): Code:
            lsp = gatelib.LUAU_LSP if os.path.exists(gatelib.LUAU_LSP) else gatelib.which("luau-lsp")
            defs = os.path.join(TOOLS, "globalTypes.d.luau")
            if lsp and os.path.exists(defs):
                import tempfile

                with tempfile.TemporaryDirectory() as tmp:
                    smap = os.path.join(tmp, "sourcemap.json")
                    project = os.path.join(cwd, "default.project.json")
                    have_map = False
                    if os.path.exists(project) and gatelib.which("argon"):
                        g = run_tool(["argon", "sourcemap", project, "-o", smap])
                        have_map = g.returncode == 0 and os.path.exists(smap)
                    cmd = [lsp, "analyze", "--flag:LuauSolverV2=true", "--no-strict-dm-types", "--platform", "roblox",
                           "--definitions", "@roblox=" + defs, "--base-luaurc", os.path.join(TOOLS, "base.luaurc"),
                           "--ignore", "**/_Index/**", "--ignore", "**/Packages/**", "--ignore", "**/Modules/**"]
                    if have_map:
                        cmd += ["--sourcemap", smap]
                    a = run_tool(cmd + analysis_existing)
                    if a.returncode in (0, 1):
                        diag = [ln for ln in (a.stdout + a.stderr).splitlines() if re.match(r"^.+\(\d+,\d+\): \w+", ln)]
                        if diag:
                            for d in diag[:20]:
                                m = re.match(r"^(.+)\((\d+),(\d+)\): (\w+): ?(.*)$", d)
                                if m:
                                    # the definite-error gate firing [R TYPE1]
                                    findings.append("%s|%s|TYPE1|%s|%s" % (m.group(2), m.group(3), m.group(4), m.group(5)[:80].replace("|", "/") or "analyze finding"))
                    else:
                        findings.append(
                            "0|0|GATE4|required checker luau-lsp failed|%s"
                            % ((a.stdout + a.stderr).strip().replace("|", "/")[:160] or "no diagnostic")
                        )
            else:
                findings.append(
                    "0|0|GATE4|required checker luau-lsp is unavailable|install or repair the harness toolchain"
                )

        # REV4 — only CLEAN or NOTED proves an acceptable settled review.
        # BLOCKED remains a hard incomplete state even though its receipt is
        # retained for audit and target binding.
        if not gatelib.valid_review_receipts(cwd, session_id):
            findings.append(
                "0|0|REV4|no parseable reviewer receipt matches current session, turn, and reviewed target digest|dispatch a reviewer on the settled target"
            )

    # Settled-tree ownership sweep. It covers files created by shell commands
    # and scaffolders that did not pass a native edit payload through PreTool.
    for relative in sorted(ownership_changed_paths):
        if relative.replace(os.sep, "/") == gatelib.HANDOFF_RELATIVE:
            continue  # PreCompact owns and validates this generated shared file.
        path = os.path.join(cwd, relative)
        for _, line, col, rule, subject, remedy in write_gate.check_gate2(path, cwd):
            findings.append("%d|%d|%s|%s|%s" % (line, col, rule, subject, remedy))
        for _, line, col, rule, subject, remedy in write_gate.check_gate3(path):
            findings.append("%d|%d|%s|%s|%s" % (line, col, rule, subject, remedy))
        if re.match(r"^places/[^/]+/(?:.*/)?Default\.luau$", relative.replace(os.sep, "/")):
            findings.append("0|0|DATA5|%s|one template serves every place" % relative)

    # OPT1 — a dump supplied without frame_census run against it
    dumps = set()
    for pattern in ("microprofile-*_summary.json", "microprofile-*.csv"):
        for p in glob.glob(os.path.join(cwd, "**", pattern), recursive=True):
            stem = os.path.basename(p).replace("_summary.json", "").replace("_counters.csv", "").replace(".csv", "")
            dumps.add(stem)
    if dumps:
        census_ran = set()
        try:
            with open(os.path.join(gatelib.CACHE, "frame_census.last"), encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split("|")
                    if len(parts) == 2 and turn_mtime is not None and float(parts[1]) >= turn_mtime:
                        census_ran.add(parts[0])
        except (OSError, ValueError):
            pass
        missing_census = sorted(dumps - census_ran)
        if missing_census:
            system_notes.append(
                "done-gate: NOTED [OPT1] frame_census not run for %s"
                % ", ".join(missing_census)
            )

    # boot_smoke [R DEBUG11] + rig_clean on the connection it already holds —
    # only when the stretch wrote something
    if changed and not findings and gatelib.studio_required(cwd, session_id):
        r = run_tool([sys.executable, os.path.join(TOOLS, "boot_smoke", "boot_smoke.py"), "--root", cwd, "--session", session_id or "done-gate"])
        if r.returncode == 2:
            tail = [ln for ln in r.stdout.splitlines() if ln.startswith(("analyze:", "play:", "  error:", "boot_smoke:"))]
            findings.append("0|0|DEBUG11|boot_smoke failed|%s" % ("; ".join(tail)[:200] or "boot errors"))
        elif r.returncode != 0:
            env_line = next((ln for ln in r.stdout.splitlines() if ln.startswith("ENV|")), "ENV|studio|unreachable")
            findings.append(
                "0|0|GATE4|required Studio verification unavailable|%s"
                % env_line.replace("|", "/")[:160]
            )
        rig = run_tool([sys.executable, os.path.join(TOOLS, "rig_clean", "rig_clean.py"), "--root", cwd, "--session", session_id or "done-gate"])
        if rig.returncode == 0 and rig.stdout.strip():
            system_notes.append(rig.stdout.strip() + "\ndeletion is a human decision - rig_clean --delete after you say so")

    # DEBUG1 — surviving test files reported with their delete-when line;
    # it judges nothing
    tests_dir = os.path.join(cwd, "tests")
    test_files = glob.glob(os.path.join(tests_dir, "**", "*.luau"), recursive=True)
    if test_files:
        lines = []
        for t in sorted(test_files):
            when = ""
            try:
                with open(t, encoding="utf-8") as f:
                    m = re.search(r"delete-when:\s*(.+)", f.read())
                    when = m.group(1).strip() if m else "no delete-when line"
            except OSError:
                pass
            lines.append("%s - %s" % (gatelib.elide(t, cwd), when))
        system_notes.append("done-gate: surviving test files [DEBUG1]:\n" + "\n".join(lines))

    if system_notes:
        gatelib.emit_json({"systemMessage": "\n\n".join(system_notes)})
    if findings:
        sys.stderr.write("done-gate: BLOCKED\n\n" + "\n".join(findings) + "\n")
        return 2
    gatelib.write_stop_cache(cwd, session_id, gatelib.stop_cache_key(cwd, session_id))
    if validation_run:
        print("FINALIZED|roblox|ready")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        sys.stderr.write("done-gate: BLOCKED\n\ngate crashed: %s: %s\n" % (type(e).__name__, e))
        sys.exit(2)
