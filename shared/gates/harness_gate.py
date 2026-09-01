#!/usr/bin/env python3
"""Bind a project, validate before final output, and verify the Stop receipt."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(os.path.dirname(HERE))
TOOLS = os.path.join(HARNESS, "tools")
sys.path.insert(0, HERE)
import gatelib  # noqa: E402


def key(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:20]


def state_path(session_id):
    return os.path.join(gatelib.CACHE, "harness-project-gate", key(session_id) + ".json")


def write_state(session_id, state):
    path = state_path(session_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".%d.tmp" % os.getpid()
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(state, handle, sort_keys=True)
        handle.write("\n")
    os.replace(temporary, path)


def read_state(session_id):
    try:
        with open(state_path(session_id), encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, ValueError, UnicodeError):
        return None
    return state if isinstance(state, dict) else None


def state_authorization_failure(session_id, state, host):
    """Explain the exact persisted-state failure for later lifecycle hooks."""
    if not isinstance(state, dict):
        condition = "absent" if not os.path.exists(state_path(session_id)) else "unreadable or malformed"
        return (
            "SessionStart authorization record is %s for this harness task; "
            "the SessionStart hook did not complete. Start a new harness task after approving its hooks."
            % condition
        )
    if state.get("schema") != 1:
        return "SessionStart authorization record has an unsupported schema; start a new harness task."
    if state.get("host") != host:
        return (
            "SessionStart authorized this harness task for %s, not %s; start a new harness task."
            % (state.get("host") or "an unknown host", host)
        )
    if state.get("session") != key(session_id):
        return "SessionStart authorization belongs to a different harness task; start a new harness task."
    return ""


def parse_project(prompt):
    if not isinstance(prompt, str):
        return None
    values = [match.group(1).strip() for match in re.finditer(r"(?mi)^project-root:\s*(\S.*)$", prompt)]
    if not values:
        return None
    return values[0] if len(values) == 1 else ""


NEGATED_OPERATION = re.compile(
    r"(?:\b(?:do\s+not|don['’]?t|does\s+not|doesn['’]?t|did\s+not|didn['’]?t|"
    r"is\s+not|isn['’]?t|are\s+not|aren['’]?t|will\s+not|won['’]?t|"
    r"not|never|without|avoid|exclude|excluding|omit|omitting|skip|"
    r"no(?:\s+need\s+to)?)\b|\bnon[-\s]*)[^.;,\n]{0,64}$",
    re.IGNORECASE,
)
POST_NEGATED_OPERATION = re.compile(
    r"^(?:\s+(?:is|are|was|were|will|would|should|must|does|do|needs?|needed)){0,3}"
    r"\s+(?:not|never|unnecessary|optional)\b"
    r"|^\s+(?:isn['’]?t|aren['’]?t|wasn['’]?t|weren['’]?t|won['’]?t|"
    r"wouldn['’]?t|shouldn['’]?t|doesn['’]?t|don['’]?t)\b"
    r"|^\s+(?:(?:is|are|was|were|will|would|should|must)\s+)?(?:be\s+)?"
    r"(?:avoided|excluded|omitted|skipped|unused|unneeded)\b"
    r"|^\s*-(?:free|less|independent)\b",
    re.IGNORECASE,
)
STUDIO_OPERATION = re.compile(
    r"\b(?:roblox\s+studio|studio|play[- ]?tests?|play[- ]?testing|"
    r"boot[_ -]?smoke|run[- ]?time\s+tests?|in[- ]?game\s+tests?)\b",
    re.IGNORECASE,
)
API_OPERATION = re.compile(
    r"\b(?:roblox\s+api|api(?:\s+(?:dump|docs?|globals?|lookup|surface|reference))?|"
    r"creator\s+docs?)\b",
    re.IGNORECASE,
)
SOURCE_OPERATION = re.compile(
    r"\b(?:lua|luau|source|code|scripts?|modules?|implementation|implement|"
    r"edit|modify|refactor|fix|build|write)\b",
    re.IGNORECASE,
)


def operation_requested(prompt, pattern):
    """Return whether a prompt positively requests one conditional surface."""
    if not isinstance(prompt, str):
        return False
    # A selected path is metadata, not task intent; do not infer capabilities
    # from directory names such as ``/work/api`` or ``/work/studio``.
    text = re.sub(r"(?mi)^project-root:\s*\S.*$", "", prompt)
    for match in pattern.finditer(text):
        clause_start = max(
            text.rfind("\n", 0, match.start()),
            text.rfind(".", 0, match.start()),
            text.rfind(";", 0, match.start()),
            text.rfind(",", 0, match.start()),
        )
        if (
            not NEGATED_OPERATION.search(text[clause_start + 1:match.start()])
            and not POST_NEGATED_OPERATION.search(text[match.end():])
        ):
            return True
    return False


def requested_operations(prompt):
    return {
        "require_api": operation_requested(prompt, API_OPERATION),
        "require_source": operation_requested(prompt, SOURCE_OPERATION),
        "require_studio": operation_requested(prompt, STUDIO_OPERATION),
    }


def hook_digest(host):
    path = os.path.join(HARNESS, ".codex", "hooks.json") if host == "codex" else os.path.join(HARNESS, ".claude", "settings.json")
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
        document = json.loads(raw)
    except (OSError, ValueError, UnicodeError) as error:
        return None, "hook definition unreadable: %s" % str(error)[:160]
    hooks = document.get("hooks") if isinstance(document, dict) else None
    if not isinstance(hooks, dict):
        return None, "hook definition has no hooks object"
    for event in ("SessionStart", "UserPromptSubmit", "Stop"):
        commands = [
            gatelib.hook_handler_text(handler)
            for entry in hooks.get(event, [])
            if isinstance(entry, dict)
            for handler in entry.get("hooks", [])
            if isinstance(handler, dict)
        ]
        if not any("harness_gate.py" in command and "--host %s" % host in command and "--event %s" % event in command for command in commands):
            return None, "%s hook is absent or obsolete" % event
    return hashlib.sha256(raw).hexdigest(), ""


def authorization_snapshot(payload, host):
    digest, detail = hook_digest(host)
    if not digest:
        return None, detail
    snapshot = {"hook_definition": digest, "host": host}
    if host == "codex":
        profile, detail = gatelib.permissions_harness_digest()
        if not profile:
            return None, detail
        trusted, detail = gatelib.project_trust_status(HARNESS)
        if not trusted:
            return None, detail
        permission_mode = payload.get("permission_mode")
        if permission_mode not in gatelib.SAFE_PERMISSION_MODES:
            return None, "permission mode is unknown: %s" % (permission_mode or "absent")
        snapshot.update({"permission_mode": permission_mode, "profile_definition": profile})
    return snapshot, ""


def valid_payload(payload, host, event):
    if not isinstance(payload, dict):
        return False, "malformed hook payload"
    if payload.get("hook_event_name") != event:
        return False, "hook event mismatch"
    if "_harness_host" in payload and payload.get("_harness_host") != host:
        return False, "hook host mismatch"
    if not payload.get("session_id"):
        return False, "session identity absent"
    if event in ("UserPromptSubmit", "Stop") and not str(payload.get("turn_id") or "").strip():
        return False, "turn identity absent"
    if os.path.realpath(payload.get("cwd") or os.getcwd()) != os.path.realpath(HARNESS):
        return False, "hook is not running in harness"
    return True, ""


def validation_key(state):
    project = os.path.realpath(state.get("project") or HARNESS)
    payload = {
        "harness": gatelib.workspace_digest(HARNESS),
        "host": state.get("host"),
        "project": project,
        "project_workspace": gatelib.workspace_digest(project) if project != os.path.realpath(HARNESS) else "",
        "require_api": bool(state.get("require_api")),
        "require_source": bool(state.get("require_source")),
        "require_studio": bool(state.get("require_studio")),
        "selection_turn": str(state.get("selection_turn") or ""),
    }
    if not payload["harness"] or (project != os.path.realpath(HARNESS) and not payload["project_workspace"]):
        return ""
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def validation_required(state):
    project = os.path.realpath(state.get("project") or HARNESS)
    if project != os.path.realpath(HARNESS):
        return True
    if any(bool(state.get(name)) for name in ("require_api", "require_source", "require_studio")):
        return True
    baseline = state.get("turn_baseline")
    current = gatelib.workspace_digest(HARNESS)
    return not baseline or not current or baseline != current


def project_gate_command(state, session_id):
    project = os.path.realpath(state.get("project") or HARNESS)
    command = [
        sys.executable,
        os.path.join(TOOLS, "project_gate", "project_gate.py"),
        "check",
        "--project-root",
        project,
        "--host",
        state["host"],
        "--session-id",
        session_id,
    ]
    permission_mode = state.get("permission_mode")
    if isinstance(permission_mode, str) and permission_mode:
        command += ["--permission-mode", permission_mode]
    require_studio = bool(state.get("require_studio"))
    selected_turn = str(state.get("selection_turn") or "")
    project_turn = gatelib.read_turn_record(project, session_id)
    if (
        project_turn
        and selected_turn
        and str(project_turn.get("turn_id") or "") == selected_turn
        and gatelib.studio_required(project, session_id)
    ):
        require_studio = True
    if require_studio:
        command.append("--require-studio")
    if state.get("require_api"):
        command.append("--require-api")
    if state.get("require_source"):
        command.append("--require-source")
    if project != os.path.realpath(HARNESS):
        command.append("--read-only-project")
    return command


def validate_before_final(session_id):
    state = read_state(session_id)
    host = state.get("host") if isinstance(state, dict) else ""
    state_failure = state_authorization_failure(session_id, state, host)
    if state_failure:
        sys.stderr.write("project-gate: %s\n" % state_failure)
        return 2
    payload = {
        "cwd": os.path.realpath(HARNESS),
        "hook_event_name": "Stop",
        "session_id": session_id,
        "turn_id": str(state.get("selection_turn") or ""),
        "_harness_host": host,
    }
    if host == "codex":
        payload["permission_mode"] = state.get("permission_mode")
    snapshot, detail = authorization_snapshot(payload, host)
    if snapshot is None or any(state.get(name) != value for name, value in (snapshot or {}).items()):
        sys.stderr.write("project-gate: current harness authorization changed: %s\n" % (detail or "restart required"))
        return 2
    if not payload["turn_id"]:
        sys.stderr.write("project-gate: current turn identity is unavailable\n")
        return 2
    result = subprocess.run(
        project_gate_command(state, session_id),
        cwd=HARNESS,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )
    if result.returncode != 0:
        return result.returncode
    settled_key = validation_key(state)
    if not settled_key:
        sys.stderr.write("project-gate: settled validation key is unavailable\n")
        return 2
    state["validation"] = {
        "completed_at": time.time(),
        "key": settled_key,
        "schema": 1,
        "turn": payload["turn_id"],
    }
    write_state(session_id, state)
    print("FINALIZED|harness|ready")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--host", choices=("codex", "claude"))
    parser.add_argument("--event", choices=("SessionStart", "UserPromptSubmit", "Stop"))
    args = parser.parse_args(argv)
    if args.validate:
        if not args.session_id:
            sys.stderr.write("project-gate: session identity absent\n")
            return 2
        return validate_before_final(args.session_id)
    if not args.host or not args.event:
        parser.error("--host and --event are required for hook invocation")
    try:
        payload = json.load(sys.stdin)
    except (TypeError, ValueError):
        sys.stderr.write("project-gate: malformed hook payload\n")
        return 2
    ok, detail = valid_payload(payload, args.host, args.event)
    if not ok:
        sys.stderr.write("project-gate: %s\n" % detail)
        return 2
    session_id = str(payload["session_id"])
    if args.event == "SessionStart":
        snapshot, detail = authorization_snapshot(payload, args.host)
        if snapshot is None:
            sys.stderr.write("project-gate: authorization failed: %s\n" % detail)
            return 2
        write_state(
            session_id,
            dict(
                snapshot,
                schema=1,
                root=os.path.realpath(HARNESS),
                session=key(session_id),
                project=os.path.realpath(HARNESS),
            ),
        )
        return 0
    state = read_state(session_id)
    state_failure = state_authorization_failure(session_id, state, args.host)
    if state_failure:
        sys.stderr.write("project-gate: %s\n" % state_failure)
        return 2
    snapshot, detail = authorization_snapshot(payload, args.host)
    if snapshot is None or any(state.get(name) != value for name, value in (snapshot or {}).items()):
        sys.stderr.write("project-gate: current harness authorization changed: %s\n" % (detail or "restart required"))
        return 2
    if args.event == "UserPromptSubmit":
        prompt = payload.get("prompt")
        supplied = parse_project(prompt)
        state["selection_turn"] = str(payload["turn_id"])
        state.update(requested_operations(prompt))
        if supplied is None:
            state["project"] = os.path.realpath(HARNESS)
        else:
            if not os.path.isabs(supplied):
                sys.stderr.write("project-gate: project-root must be absolute\n")
                return 2
            project = os.path.realpath(supplied)
            if project != os.path.realpath(HARNESS) and not gatelib.is_roblox_project(project):
                sys.stderr.write("project-gate: project-root must contain .roblox\n")
                return 2
            if project != os.path.realpath(HARNESS) and os.path.realpath(
                os.path.join(os.path.dirname(project), "harness")
            ) != os.path.realpath(HARNESS):
                sys.stderr.write("project-gate: project-root must be beside harness\n")
                return 2
            state["project"] = project
        state["turn_baseline"] = gatelib.workspace_digest(HARNESS)
        state.pop("validation", None)
        write_state(session_id, state)
        gatelib.emit_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": (
                        "If this turn changes the workspace or requests project validation, run this "
                        "command as the last tool before the final response: %s"
                        % gatelib.finalization_command(HARNESS, session_id)
                    ),
                }
            }
        )
        return 0

    project = state.get("project") or os.path.realpath(HARNESS)
    selected_turn = str(state.get("selection_turn") or "")
    stop_turn = str(payload["turn_id"])
    # A task that was already running when the pre-final lifecycle was installed
    # has SessionStart authorization but no UserPromptSubmit selection. Bind that
    # one in-flight harness turn from the authenticated Stop payload so the exact
    # finalizer command can issue its receipt on retry.
    if not selected_turn and os.path.realpath(project) == os.path.realpath(HARNESS):
        state["selection_turn"] = stop_turn
        state.pop("validation", None)
        write_state(session_id, state)
        selected_turn = stop_turn
    if (selected_turn and selected_turn != stop_turn) or (
        not selected_turn and project != os.path.realpath(HARNESS)
    ):
        sys.stderr.write("project-gate: project-root selection belongs to a different turn\n")
        return 2
    if not validation_required(state):
        return 0
    current_key = validation_key(state)
    receipt = state.get("validation")
    if (
        current_key
        and isinstance(receipt, dict)
        and receipt.get("schema") == 1
        and receipt.get("turn") == stop_turn
        and receipt.get("key") == current_key
    ):
        return 0
    sys.stderr.write(
        "project-gate: pre-final validation receipt is absent or stale; run before the final response: %s\n"
        % gatelib.finalization_command(HARNESS, session_id)
    )
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as error:
        sys.stderr.write("project-gate: ERROR %s: %s\n" % (type(error).__name__, error))
        sys.exit(3)
