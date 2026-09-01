#!/usr/bin/env python3
"""Documented SessionStart authorization gate for Codex and Claude Code.

The gate validates stable configuration and documented payload fields before
it writes authorization state. SessionStart is context-only; blocking is
enforced by later blocking hooks.
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gatelib  # noqa: E402


PROJECT_DISCOVERY_PATHS = {
    "codex": (
        "AGENTS.md",
        ".codex/hooks.json",
        ".codex/config.toml",
        ".agents/skills/roblox-writer/SKILL.md",
        ".agents/skills/roblox-writer/agents/openai.yaml",
    ) + tuple(".codex/agents/%s.toml" % name for name in gatelib.REQUIRED_CODEX_AGENTS),
    "claude": (
        "CLAUDE.md",
        ".claude/settings.json",
        ".claude/skills/roblox-writer/SKILL.md",
    ) + tuple(".claude/agents/%s.md" % name for name in gatelib.REQUIRED_CODEX_AGENTS),
}


def discovery_snapshot(cwd, host="codex"):
    """Capture generated files a host discovers only at task start."""
    root = os.path.realpath(cwd)
    snapshot = []
    paths = [(relative, os.path.join(root, relative)) for relative in PROJECT_DISCOVERY_PATHS.get(host, ())]
    if host == "codex":
        paths += [
            ("<user>/config.toml", gatelib.codex_config_path()),
        ]
    for relative, path in paths:
        if not os.path.lexists(path):
            snapshot.append((relative, "missing", "", b""))
            continue
        link = os.readlink(path) if os.path.islink(path) else ""
        try:
            with open(path, "rb") as handle:
                content = handle.read()
            kind = "link" if link else "file"
        except OSError:
            kind = "broken-link" if link else "unreadable"
            content = b""
        snapshot.append((relative, kind, link, content))
    return tuple(snapshot)


def auto_relink(cwd, host="codex"):
    """Run the canonical relinker and report task-discovery changes."""
    root = os.path.realpath(cwd)
    before = discovery_snapshot(root, host)
    before_by_path = {entry[0]: entry[1:] for entry in before}
    command = [
        sys.executable,
        os.path.join(gatelib.HARNESS, "openai", "setup", "permissions_harness.py"),
        "--relink",
        "--host",
        host,
    ]
    result = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        timeout=180,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )
    if result.returncode != 0:
        return False, False, False
    after = discovery_snapshot(root, host)
    after_by_path = {entry[0]: entry[1:] for entry in after}
    hook_paths = (".codex/hooks.json",) if host == "codex" else (".claude/settings.json",)
    hook_changed = any(before_by_path.get(path) != after_by_path.get(path) for path in hook_paths)
    relink_reported_change = "discovery exact; no new task required." not in result.stdout
    return True, relink_reported_change or before != after, hook_changed


def hook_scope(argv):
    try:
        index = argv.index("--hook-scope")
        value = argv[index + 1]
    except (ValueError, IndexError):
        return ""
    return value if value in ("project", "user") else ""


def stop(message, visible_reason=None, host="codex", cwd="", session_id=""):
    """Keep the session unauthorized and add documented startup context."""
    reason = message or gatelib.session_block(host, "session verification failed", cwd)
    visible = visible_reason or (
        gatelib.permissions_harness_stop_reason(reason, cwd)
        if host == "codex"
        else "Roblox harness did not authorize this Claude Code session."
    )
    gatelib.write_session_failure(cwd, session_id, visible)
    gatelib.emit_json(
        {
            "continue": True,
            "systemMessage": reason,
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": gatelib.permissions_harness_prompt_context(visible),
            },
        }
    )
    return 0


def degraded(message, repairs, snapshot, host="codex", cwd="", session_id=""):
    """Keep normal tools closed while exact prerequisite repairs remain open."""
    context = gatelib.recovery_prompt_context(cwd, repairs)
    if not context or not gatelib.write_session_degraded(cwd, session_id, snapshot, message, repairs):
        return stop(message, host=host, cwd=cwd, session_id=session_id)
    gatelib.emit_json(
        {
            "continue": True,
            "systemMessage": message,
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            },
        }
    )
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    payload = gatelib.read_payload()
    candidate = payload.get("cwd") if isinstance(payload, dict) else os.getcwd()
    if not gatelib.is_roblox_project(candidate):
        return 0
    if not isinstance(payload, dict):
        return stop(gatelib.permissions_harness_block("malformed SessionStart payload"), cwd=candidate)
    scope = hook_scope(argv)
    host = gatelib.hook_host(argv, payload)
    session_id = payload.get("session_id", "")
    advisory = ""
    if not scope:
        return stop(
            gatelib.session_block(host, "approved hook bootstrap is unavailable", candidate),
            host=host,
            cwd=candidate,
            session_id=session_id,
        )
    if not host:
        return stop(gatelib.permissions_harness_block("explicit hook host is unavailable"), cwd=candidate, session_id=session_id)
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return stop(gatelib.session_block(host, "SessionStart workspace is absent", candidate), host=host, cwd=candidate, session_id=session_id)
    sources = ("startup", "resume", "clear", "compact")
    if host == "claude":
        sources += ("fork",)
    if payload.get("source") not in sources:
        return stop(gatelib.session_block(host, "SessionStart source is absent or malformed", cwd), host=host, cwd=cwd, session_id=session_id)
    if payload.get("hook_event_name") != "SessionStart":
        return stop(
            gatelib.session_block(host, "hook event is absent or malformed", cwd),
            host=host,
            cwd=cwd,
            session_id=session_id,
        )
    if not isinstance(session_id, str) or not session_id.strip():
        return stop(
            gatelib.session_block(host, "session identity is absent", cwd),
            host=host,
            cwd=cwd,
            session_id=session_id,
        )

    if scope == "project":
        if not gatelib.project_uses_harness(cwd):
            visible = gatelib.blocker_instruction("hooks", cwd)
            return stop(gatelib.session_block(host, visible, cwd), visible, host, cwd, session_id)
        if host == "codex":
            trusted, trust_detail = gatelib.project_trust_status(cwd)
            if not trusted:
                detail = "project trust verification failed: %s" % trust_detail
                visible = gatelib.permissions_harness_stop_reason(detail, cwd)
                return stop(gatelib.session_block(host, detail, cwd), visible, host, cwd, session_id)
            permission_mode = payload.get("permission_mode")
            if permission_mode not in gatelib.SAFE_PERMISSION_MODES:
                detail = "permission mode is unknown: %s" % (permission_mode or "absent")
                visible = gatelib.permissions_harness_stop_reason(detail, cwd)
                return stop(gatelib.session_block(host, detail, cwd), visible, host, cwd, session_id)
        relinked, discovery_changed, hook_changed = auto_relink(cwd, host)
        if not relinked:
            visible = gatelib.blocker_instruction("hooks", cwd)
            return stop(gatelib.session_block(host, visible, cwd), visible, host, cwd, session_id)
        if discovery_changed:
            runtime = "Codex" if host == "codex" else "Claude"
            advisory = "Harness updated %s %s discovery; continue this task%s." % (
                gatelib.project_name(cwd),
                runtime,
                "; review changed hooks during integration maintenance" if hook_changed else "",
            )

    ok, detail, snapshot = gatelib.verified_session_snapshot(
        payload,
        cwd,
        scope,
        "SessionStart",
        host,
    )
    if not ok:
        visible = (
            gatelib.permissions_harness_stop_reason(detail, cwd)
            if host == "codex"
            else "Roblox harness did not authorize this Claude Code session: %s" % detail[:200]
        )
        return stop(gatelib.session_block(host, detail, cwd), visible, host, cwd, session_id)

    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            os.path.join(HERE, "precheck.py"),
            "--root",
            cwd,
            "--session-id",
            payload["session_id"],
            "--session-start",
            "--host",
            host,
            "--operation",
            "bootstrap",
        ],
        capture_output=True,
        text=True,
        timeout=900,
        env=environment,
    )
    output = result.stdout.strip()
    if result.returncode != 0 or output != "session-gate: READY":
        detail = output or result.stderr.strip() or "session precheck failed without a diagnostic"
        repairs = gatelib.recovery_kinds_from_precheck(detail)
        if repairs:
            return degraded(
                gatelib.session_block(host, gatelib.session_precheck_stop_reason(detail, cwd), cwd),
                repairs,
                snapshot,
                host,
                cwd,
                session_id,
            )
        return stop(
            gatelib.session_block(host, detail, cwd),
            gatelib.session_precheck_stop_reason(detail, cwd),
            host,
            cwd,
            session_id,
        )
    try:
        if not gatelib.authorize_session(cwd, payload["session_id"], snapshot):
            return stop(
                gatelib.session_block(host, "session authorization was not created", cwd),
                host=host,
                cwd=cwd,
                session_id=session_id,
            )
    except OSError as error:
        return stop(
            gatelib.session_block(host, "session authorization cache write failed: %s" % str(error)[:160], cwd),
            host=host,
            cwd=cwd,
            session_id=session_id,
        )
    if advisory:
        gatelib.emit_json(
            {
                "continue": True,
                "systemMessage": "session-gate: READY",
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": "session-gate: READY\n" + advisory,
                },
            }
        )
    else:
        print("session-gate: READY")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as error:
        sys.exit(
            stop(
                gatelib.permissions_harness_block(
                    "SessionStart gate crashed: %s: %s"
                    % (type(error).__name__, str(error)[:160])
                ),
                cwd=os.getcwd(),
            )
        )
