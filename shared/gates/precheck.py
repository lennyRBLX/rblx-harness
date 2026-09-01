#!/usr/bin/env python3
"""precheck — the eleven session checks, and the ONLY writer of
gates/.preconditions. It re-runs everything and rewrites the file from the
result — it never edits entries, so an entry disappears only because the
check now passes, and nothing can clear a failure it did not fix.
session-gate calls it at session start; an agent may call it at any time.

Usage: precheck.py [--root DIR] [--session-id ID]
Prints the verdict: READY when all ran and passed, DEGRADED otherwise —
a check that could not run prints SKIPPED <n>, because a fallback that
changes the verdict without saying so is the failure the convention stops.
"""

import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gatelib  # noqa: E402
from studio_rpc import EnvError  # noqa: E402

TOOLS = gatelib.TOOLS
HARNESS = gatelib.HARNESS

GATE_SCRIPTS = ["write_gate.py", "done_gate.py", "finalize.py", "session_gate.py", "compact_gate.py", "agent_start.py", "agent_ack.py", "record_check.py", "turn_stamp.py", "harness_gate.py"]
DENY_IDS = {"BC3", "WRIT18", "DATA29", "OPT11", "WRIT11", "BC1", "OPT12", "BC7"}
HOOK_SCRIPTS = {
    "PreToolUse": "write_gate.py",
    "Stop": "done_gate.py",
    "SessionStart": "session_gate.py",
    "PreCompact": "compact_gate.py",
    "SubagentStart": "agent_start.py",
    "SubagentStop": "record_check.py",
    "UserPromptSubmit": "turn_stamp.py",
}


def run(cmd, timeout=180):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        class R:
            returncode = 1
            stdout = ""
            stderr = str(e)

        return R()


def gate_field(value, limit=200):
    return " ".join(str(value).replace("|", "/").split())[:limit]


def report_instruction(number, message, root):
    if number == 1:
        name = message.split(" ", 1)[0]
        if "missing or empty" in message:
            return "Restore %s in harness; retry." % name
        if "does not compile" in message:
            return "Fix the syntax error in %s; retry." % name
        if "type cache" in message:
            return (
                "Rebuild the type cache; retry: python3 %s ensure --root %s"
                % (os.path.join(TOOLS, "type_cache", "type_cache.py"), os.path.realpath(root))
            )
    if number == 2 or number == 9:
        return gatelib.blocker_instruction("hooks", root)
    if number == 3:
        return "Fix %s; retry." % os.path.join(TOOLS, "deny_scan", "deny_table.luau")
    if number == 6:
        return message
    if number == 8:
        entry = message.partition("overlay entry dead:")[2].partition(" - ")[0].strip() or "the dead entry"
        return "Update or remove API overlay entry %s; retry." % entry
    return "Run harness verification; fix the failure; retry."


def studio_instruction(cause, root):
    return {
        "no-studio": gatelib.blocker_instruction("studio-connect", root),
        "no-place": gatelib.blocker_instruction("studio-place", root),
        "wrong-place": gatelib.blocker_instruction("studio-place", root),
        "unpublished-place": gatelib.blocker_instruction("studio-publish", root),
        "ambiguous-studio": gatelib.blocker_instruction("studio-ambiguous", root),
        "studiomcp-absent": gatelib.blocker_instruction("studio-install", root),
        "studiomcp-spawn-failed": gatelib.blocker_instruction("studio-install", root),
        "studiomcp-unreachable": gatelib.blocker_instruction("studio-restart", root),
        "studiomcp-timeout": gatelib.blocker_instruction("studio-restart", root),
        "studiomcp-error": gatelib.blocker_instruction("studio-restart", root),
    }.get(cause, gatelib.blocker_instruction("studio-place", root))


def place_map_instruction(cause, detail, root):
    if detail.startswith("Open the right project experience"):
        return detail.replace("project", gatelib.project_name(root), 1)
    if detail.startswith(("Give ", "Link ", "Add ", "Restart ", "Open ", "Enable ", "Publish ", "Close ")):
        return detail
    if cause == "no-studio":
        return gatelib.blocker_instruction("studio-connect", root)
    if cause in ("no-place", "wrong-place"):
        return gatelib.blocker_instruction("studio-place", root)
    if cause == "unpublished-place":
        return gatelib.blocker_instruction("studio-publish", root)
    if cause in ("studiomcp-unreachable", "studiomcp-timeout", "studiomcp-error"):
        return gatelib.blocker_instruction("studio-restart", root)
    if cause in ("studiomcp-absent", "studiomcp-spawn-failed"):
        return gatelib.blocker_instruction("studio-install", root)
    if cause == "ambiguous-studio":
        return gatelib.blocker_instruction("studio-ambiguous", root)
    if cause == "stale-mapping":
        place = re.search(r"places/([^\s]+)", detail)
        return "Open the right %s experience; update places/%s PlaceId; retry." % (
            gatelib.project_name(root), place.group(1) if place else "{place}",
        )
    if cause == "duplicate-mapping":
        places = re.findall(r"places/([^\s]+)", detail)
        first, second = (places + ["{first}", "{second}"])[:2]
        return "Give places/%s and places/%s unique PlaceIds; retry." % (first, second)
    if cause == "unmapped-child":
        place = re.search(r"places/([^\s]+)", detail)
        return "Link places/%s to its Roblox PlaceId; retry." % (place.group(1) if place else "{place}")
    if cause == "unmapped-place":
        match = re.search(r'(\d+)\s+"([^"]+)"', detail)
        place_id, place = match.groups() if match else ("{place_id}", "{place}")
        return "Add places/%s for PlaceId %s; retry." % (place, place_id)
    return gatelib.blocker_instruction("new-task", root)


def probe_studio(root):
    """Probe Studio through its supported stdio MCP seam.

    Process and listening-port discovery are not reliable inside a Codex
    sandbox and must not decide whether the open place is reachable.
    """
    try:
        return gatelib.studio_attached("precheck", raise_errors=True), ""
    except EnvError as error:
        return None, studio_instruction(error.cause, root)


def session_studio_probe(host, root):
    """Return the live probe result, or defer to Codex's native MCP client.

    Codex owns the configured stdio process. During SessionStart a second
    StudioMCP process can run before that client has attached, so its empty
    Studio list is not evidence about the connection available to the turn.
    """
    if host == "codex":
        return None, "", True
    place, instruction = probe_studio(root)
    return place, instruction, False


def hook_registration_reports(path, host):
    label = "Codex" if host == "codex" else "Claude"
    try:
        with open(path, encoding="utf-8") as f:
            document = json.load(f)
    except (OSError, ValueError) as e:
        return ["%s hook file unreadable: %s" % (label, str(e)[:120])]
    hooks = document.get("hooks")
    if not isinstance(hooks, dict):
        return ["%s hook file has no hooks object" % label]
    reports = []
    adapter = "%s/hooks/adapter.py" % ("openai" if host == "codex" else "claude")
    for event in HOOK_SCRIPTS:
        entries = hooks.get(event)
        commands = []
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                for hook in entry.get("hooks", []):
                    if isinstance(hook, dict):
                        commands.append(gatelib.hook_handler_text(hook))
        if not any(
            adapter in command.replace("\\", "/")
            and "--event %s" % event in command.replace("\\", "/")
            and "--hook-scope project" in command.replace("\\", "/")
            and gatelib.hook_command_disables_bytecode(command.replace("\\", "/"))
            for command in commands
        ):
            reports.append("%s %s not registered with project scope - roblox-new-game --relink" % (label, event))
    for event in ("SubagentStart", "SubagentStop"):
        if any(isinstance(entry, dict) and "matcher" in entry for entry in hooks.get(event, [])):
            reports.append("%s %s matcher hides null/default agent roles - roblox-new-game --relink" % (label, event))
    pretool = hooks.get("PreToolUse")
    if not isinstance(pretool, list) or not any(
        isinstance(entry, dict) and entry.get("matcher") == ".*" for entry in pretool
    ):
        reports.append("%s PreToolUse does not cover every supported local tool - roblox-new-game --relink" % label)
    session = hooks.get("SessionStart")
    sources = ("startup", "resume", "clear", "compact")
    if host == "claude":
        sources += ("fork",)
    if not isinstance(session, list) or not any(
        isinstance(entry, dict)
        and isinstance(entry.get("matcher"), str)
        and all(re.search(entry["matcher"], source) for source in sources)
        for entry in session
    ):
        reports.append("%s SessionStart does not cover every start source - roblox-new-game --relink" % label)
    return reports


def place_map_preconditions(result, root=""):
    """Translate every place-map failure into a durable GATE4 precondition."""
    if result.returncode == 0:
        return []
    if result.returncode == 3:
        records = [line for line in result.stdout.splitlines() if line.startswith("ENV|")]
        if records:
            out = []
            for record in records:
                parts = record.split("|", 2)
                cause = parts[1]
                raw_detail = parts[2] if len(parts) == 3 else ""
                detail = gate_field(cause + (": " + raw_detail if raw_detail else ""))
                out.append("GATE4|place_map %s|%s" % (detail, place_map_instruction(cause, raw_detail, root)))
            return out
        return ["GATE4|place_map failed w/o an ENV record|%s" % gatelib.blocker_instruction("new-task", root)]
    detail = gate_field(result.stderr or result.stdout, 120) or "no diagnostic"
    return ["GATE4|place_map crashed: %s|Run place_map; fix the err; retry." % detail]


def corpus_preconditions(root=""):
    """Validate the corpus; stale or missing shared state synchronizes once."""
    state, detail = gatelib.corpus_status()
    if state == "malformed":
        return False, [
            "GATE4|corpus malformed: %s|Sync the harness API cache: %s"
            % (gate_field(detail), gatelib.recovery_command(gatelib.RECOVERY_API_SYNC, root or os.getcwd()))
        ]
    if state in ("missing", "stale"):
        cache_ok, cache_detail = gatelib.cache_sync_ready()
        if not cache_ok:
            return False, [
                "GATE4|cache permission failure: %s|Allow writes to ~/.cache/harness; retry api_dump --sync."
                % gate_field(cache_detail)
            ]
        result = run(
            [sys.executable, os.path.join(TOOLS, "api_dump", "api_dump.py"), "--sync"],
            timeout=600,
        )
        if result.returncode != 0:
            diagnostic = gate_field(result.stdout or result.stderr) or "no diagnostic"
            return False, [
                "GATE4|required corpus synchronization failed: %s|Allow github.com, codeload.github.com and raw.githubusercontent.com; sync the harness API cache; retry."
                % diagnostic
            ]
        state, detail = gatelib.corpus_status()
    if state != "fresh":
        return False, [
            "GATE4|corpus synchronization did not establish a fresh corpus: %s|Sync the harness API cache: %s"
            % (gate_field(detail), gatelib.recovery_command(gatelib.RECOVERY_API_SYNC, root or os.getcwd()))
        ]
    return True, []


def api_globals_preconditions(root):
    updates_dir = os.path.join(root, "shared", "src", "ServerScriptService", "Services", "Updates")
    command = [sys.executable, os.path.join(TOOLS, "api_dump", "api_dump.py"), "--emit-globals"]
    if os.path.isdir(updates_dir):
        command += ["--updates", updates_dir]
    result = run(command, timeout=300)
    if result.returncode == 0 and gatelib.api_globals_present():
        return []
    detail = gate_field(result.stderr or result.stdout, 160) or "api_globals.luau was not generated"
    return [
        "GATE4|api_globals regeneration failed: %s|Gen API globals: %s"
        % (detail, gatelib.recovery_command(gatelib.RECOVERY_API_GLOBALS, root))
    ]


def api_globals_readonly_preconditions():
    if gatelib.api_globals_present():
        return []
    return [
        "GATE4|api_globals.luau absent or unreadable|Generate API globals; retry: python3 %s --emit-globals"
        % os.path.join(TOOLS, "api_dump", "api_dump.py")
    ]


def execute_luau_approval_preconditions(root):
    ok, detail = gatelib.execute_luau_approval_override(root)
    if ok:
        return []
    return [
        "GATE4|StudioMCP execute_luau approval override invalid: %s|%s"
        % (
            gate_field(detail),
            gate_field(gatelib.execute_luau_approval_instruction(root), 1000),
        )
    ]


def bootstrap_preconditions(root, host, session_id):
    """Validate only state required to authorize the current project task."""
    records = []
    if not session_id:
        records.append(
            "GATE4|session identity absent|%s" % gatelib.blocker_instruction("new-task", root)
        )
    for name in GATE_SCRIPTS:
        path = os.path.join(HERE, name)
        try:
            with open(path, encoding="utf-8") as handle:
                source = handle.read()
            if not source:
                raise ValueError("empty")
            compile(source, path, "exec")
        except Exception as error:
            records.append(
                "GATE4|required checker %s is unavailable: %s|Repair the harness checker."
                % (name, gate_field(error))
            )
    hook_path = (
        os.path.join(root, ".codex", "hooks.json")
        if host == "codex"
        else os.path.join(root, ".claude", "settings.json")
    )
    for report in hook_registration_reports(hook_path, host):
        records.append(
            "GATE4|generated %s integration invalid: %s|%s"
            % (host, gate_field(report), gatelib.blocker_instruction("hooks", root))
        )
    if host == "codex":
        agents_ok, detail = gatelib.required_codex_agents_status(root)
        if not agents_ok:
            records.append(
                "GATE4|generated Codex agents invalid: %s|%s"
                % (gate_field(detail), gatelib.blocker_instruction("hooks", root))
            )
    return records


def main(argv):
    if any(argument in ("-h", "--help") for argument in argv):
        print(
            "usage: precheck.py [--root DIR] [--session-id ID] "
            "[--session-start] [--host {codex,claude}] [--operation {bootstrap,full}]"
        )
        return 0
    root = os.getcwd()
    session_id = ""
    session_start = False
    host = "codex"
    operation = "full"
    i = 0
    while i < len(argv):
        if argv[i] == "--root" and i + 1 < len(argv):
            root = argv[i + 1]
            i += 2
        elif argv[i] == "--session-id" and i + 1 < len(argv):
            session_id = argv[i + 1]
            i += 2
        elif argv[i] == "--session-start":
            session_start = True
            i += 1
        elif argv[i] == "--host" and i + 1 < len(argv):
            host = argv[i + 1]
            i += 2
        elif argv[i] == "--operation" and i + 1 < len(argv):
            operation = argv[i + 1]
            i += 2
        else:
            i += 1

    if not gatelib.is_roblox_project(root):
        print("session-gate: READY")
        return 0

    if host == "codex":
        ok, message = gatelib.require_permissions_harness()
        if not ok:
            print(message)
            return 2

    if operation == "bootstrap":
        records = bootstrap_preconditions(root, host, session_id)
        print("session-gate: READY" if not records else "session-gate: DEGRADED")
        for record in records:
            print(record)
        return 0 if not records else 2

    if not session_start and not gatelib.revoke_session(root, session_id):
        print("session-gate: DEGRADED")
        print("GATE4|session auth revoke failed|Allow writes to ~/.cache/harness; retry the current task.")
        return 2

    reports = []       # (check#, message) — reports only
    preconditions = [] # entries with teeth: write-gate and done-gate block on these
    skipped = []       # dependency telemetry only; never a user-facing cause
    human = []         # systemMessage material

    # Codex must approve only execute_luau before dispatch. GATE5 still
    # inspects its code in PreToolUse and blocks Studio source mutation.
    if host == "codex":
        preconditions.extend(execute_luau_approval_preconditions(root))

    # 4/5 — establish the once-daily corpus and generated globals before any
    # project mutation can be authorized. SessionStart owns this shared-cache
    # preparation after its profile, trust, and hook definition are verified.
    corpus_ready, corpus_errors = corpus_preconditions(root)
    preconditions.extend(corpus_errors)
    if corpus_ready:
        globals_errors = api_globals_preconditions(root)
        preconditions.extend(globals_errors)
        corpus_ready = not globals_errors

    # 1 — each gate script exists, is non-empty, compiles (reports only)
    for name in GATE_SCRIPTS:
        path = os.path.join(HERE, name)
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            reports.append((1, "%s missing or empty - an empty gate exits 0 and waves everything through" % name))
            continue
        try:
            with open(path, encoding="utf-8") as f:
                compile(f.read(), path, "exec")
        except Exception as e:
            reports.append((1, "%s does not compile: %s" % (name, str(e)[:120])))

    for relative in (
        "type_core/core.py",
        "type_cache/type_cache.py",
        "type_lookup/type_lookup.py",
        "type_write/type_write.py",
    ):
        path = os.path.join(TOOLS, relative)
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            reports.append((1, "%s missing or empty" % relative))
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                compile(handle.read(), path, "exec")
        except Exception as error:
            reports.append((1, "%s does not compile: %s" % (relative, str(error)[:120])))

    try:
        from type_cache.type_cache import ensure as ensure_type_cache, verify as verify_type_cache

        ensure_type_cache(root)
        cache_status, _, _ = verify_type_cache(root)
        if cache_status != "current":
            reports.append((1, "type cache did not verify after rebuild: %s" % cache_status))
    except Exception as error:
        reports.append((1, "type cache or recovery unavailable: %s" % str(error)[:120]))

    # 2 — each gate registered; subagent hooks run without matchers because
    # Codex can report a task-named agent as null/default (reports only)
    for path, hook_host in (
        (os.path.join(root, ".claude", "settings.json"), "claude"),
        (os.path.join(root, ".codex", "hooks.json"), "codex"),
    ):
        if os.path.exists(path):
            reports.extend((2, message) for message in hook_registration_reports(path, hook_host))
        elif not gatelib.is_harness(root):
            label = "Codex" if hook_host == "codex" else "Claude"
            reports.append((2, "no %s hook file - roblox-new-game --relink" % label))

    # 3 — the pinned floor exists, then deny_scan's table parses.
    if not gatelib.toolchain_present():
        preconditions.append(
            "GATE4|toolchain absent: lute or luau-lsp|Install the harness toolchain: %s"
            % gatelib.recovery_command(gatelib.RECOVERY_TOOLCHAIN, root)
        )
        skipped.append(3)
    else:
        r = run([gatelib.LUTE, "run", os.path.join(TOOLS, "deny_scan", "check_table.luau")])
        if r.returncode != 0 or not r.stdout.startswith("ok "):
            reports.append((3, "deny_scan table malformed: %s" % (r.stderr.strip()[:120] or "did not parse")))

    # 6 — GATE4 probe primed; only success is cached
    place = None
    if not corpus_ready:
        skipped.append(6)
    else:
        place, instruction, deferred = session_studio_probe(host, root)
        if deferred:
            skipped.append(6)
        elif instruction:
            reports.append((6, instruction))

    # 7 — GATE6: fetch the live canonical branch. Remote drift is repairable
    # inside an authorized session; structural Git failures are not.
    if not gatelib.is_harness(root):
        state, detail = gatelib.gate6_state(root, fetch=True)
        disposition = gatelib.gate6_disposition(state)
        if disposition == "repair":
            human.append(gatelib.gate6_instruction(root, state, detail))
        elif disposition == "advisory":
            human.append("GATE6 advisory: fetch-failed: %s" % gate_field(detail))
        elif disposition == "hard":
            repair = gatelib.gate6_instruction(root, state, detail)
            preconditions.append("GATE6|%s: %s|%s" % (state, gate_field(detail), gate_field(repair)))
            human.append(repair)

    # 8 — house-overlay entries still name a live class or member (reports only)
    if corpus_ready:
        r = run([sys.executable, os.path.join(TOOLS, "api_dump", "api_dump.py"), "--check-overlay"])
        if r.returncode == 2:
            for line in r.stdout.splitlines():
                reports.append((8, "overlay entry dead: %s - a .roblox-harness/ session repairs it" % line))
        elif r.returncode == 3:
            reports.append((8, "API overlay check failed"))
    else:
        skipped.append(8)

    # 9 — required standalone Codex agents must be complete and discoverable.
    if host == "codex":
        codex_agents_ok, codex_agents_detail = gatelib.required_codex_agents_status(root)
        if not codex_agents_ok:
            reports.append((9, "%s - roblox-new-game --relink" % codex_agents_detail))

    # Other generated package, agent, and skill links must also resolve.
    for base in (
        os.path.join(HARNESS, "packages"),
        os.path.join(root, ".claude", "agents"),
        os.path.join(root, ".claude", "skills"),
        os.path.join(root, ".codex", "agents"),
        os.path.join(root, ".agents", "skills"),
    ):
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            for entry in dirnames + filenames:
                p = os.path.join(dirpath, entry)
                if os.path.islink(p) and not os.path.exists(p):
                    reports.append((9, "dead symlink %s - roblox-new-game --relink" % p))

    # 10 — either skill installed at the wrong scope (precondition file).
    # A misinstall test, not a shadowing test: collision is impossible by
    # construction.
    for user_writer in (os.path.expanduser("~/.claude/skills/roblox-writer"), os.path.expanduser("~/.agents/skills/roblox-writer")):
        if os.path.exists(user_writer):
            preconditions.append("GATE4|roblox-writer found at user scope|%s" % gatelib.blocker_instruction("hooks", root))
    project_newgame = os.path.join(root, ".claude", "skills", "roblox-new-game")
    codex_project_newgame = os.path.join(root, ".agents", "skills", "roblox-new-game")
    if os.path.exists(codex_project_newgame):
        preconditions.append("GATE4|roblox-new-game found in a project (.agents/skills)|%s" % gatelib.blocker_instruction("hooks", root))
    if os.path.exists(project_newgame):
        preconditions.append("GATE4|roblox-new-game found in a project|%s" % gatelib.blocker_instruction("hooks", root))

    # 11 — place_map: every places/ child mapped, every universe place
    # recognised (precondition file). Runs only at the origin tip — another
    # developer has likely already fixed the mapping upstream.
    if os.path.isdir(os.path.join(root, "places")) and (reports or preconditions or skipped):
        skipped.append(11)
    elif os.path.isdir(os.path.join(root, "places")):
        r = run([sys.executable, os.path.join(TOOLS, "place_map", "place_map.py"), "--root", root], timeout=120)
        preconditions.extend(place_map_preconditions(r, root))

    # Every causal report has teeth. Dependency skips never replace their
    # causal failure.
    for n, message in reports:
        preconditions.append(
            "GATE4|session precheck %d: %s|%s"
            % (n, gate_field(message), gate_field(report_instruction(n, message, root), 1000))
        )
    if not session_id:
        preconditions.append(
            "GATE4|session identity absent|%s" % gatelib.blocker_instruction("new-task", root)
        )

    all_clean = not reports and not preconditions
    if session_start:
        if all_clean:
            print("session-gate: READY")
            return 0
        print("session-gate: DEGRADED")
        for n, msg in reports:
            print("%d|%s" % (n, msg))
        for record in preconditions:
            print(record)
        return 2

    # Manual preparation retains the durable precondition report. SessionStart
    # uses the read-only branch above and writes only its final authorization.
    try:
        gatelib.write_preconditions(root, session_id, preconditions)
    except OSError as e:
        gatelib.revoke_session(root, session_id)
        print("session-gate: DEGRADED")
        print("GATE4|preconditions write failed: %s|Allow writes to %s/gates; retry the current task." % (str(e)[:120], root))
        return 2

    if all_clean:
        if not gatelib.revoke_session(root, session_id):
            all_clean = False
            preconditions.append(
                "GATE4|stale session auth could not be removed|Allow writes to ~/.cache/harness; retry the current task."
            )
        if not all_clean:
            gatelib.revoke_session(root, session_id)
            try:
                gatelib.write_preconditions(root, session_id, preconditions)
            except OSError:
                pass
    print("session-gate: READY" if all_clean else "session-gate: DEGRADED")
    for n, msg in reports:
        print("%d|%s" % (n, msg))
    for p in preconditions:
        print(p)
    if human:
        gatelib.emit_json({"systemMessage": "\n".join(human)})
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as e:
        print("session-gate: DEGRADED")
        print(
            "GATE4|precheck crashed: %s: %s|Run harness verification; fix the failure; retry: python3 %s"
            % (type(e).__name__, e, os.path.join(TOOLS, "tests", "run_verify.py"))
        )
        sys.exit(2)
