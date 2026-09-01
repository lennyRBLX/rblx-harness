#!/usr/bin/env python3
"""SubagentStart context and state writer.

Reviewers receive one flat pending receipt. Other ruled agents retain the
mailbox and acknowledgement route.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gatelib  # noqa: E402
import agent_payload  # noqa: E402
import agent_dispatch  # noqa: E402

AGENTS = ("reviewer", "debugger", "optimizer", "researcher", "maintainer")
WRITER_AGENTS = frozenset(("debugger",))
SERIAL_AGENTS = frozenset(("debugger", "optimizer", "maintainer"))
ACTIVE_MAILBOX_STATES = frozenset(("pending", "overlap", "recovering"))


def context(message):
    gatelib.emit_json(
        {
            "continue": True,
            "hookSpecificOutput": {
                "hookEventName": "SubagentStart",
                "additionalContext": message,
            },
        }
    )
    return 0


def mailbox_concurrency(cwd, session_id, agent_id, agent):
    active = [
        entry
        for entry in gatelib.agent_mailbox_entries(cwd, session_id)
        if entry.get("cwd") == os.path.realpath(cwd)
        and entry.get("session_id") == str(session_id)
        and entry.get("agent_id") != str(agent_id)
        and entry.get("agent_type") != "reviewer"
        and entry.get("state") in ACTIVE_MAILBOX_STATES
    ]
    writer_conflict = agent in WRITER_AGENTS and any(
        entry.get("agent_type") in WRITER_AGENTS for entry in active
    )
    role_conflict = agent in SERIAL_AGENTS and any(
        entry.get("agent_type") == agent for entry in active
    )
    return active, writer_conflict or role_conflict


def concurrency_context(writer_conflict):
    if writer_conflict:
        return (
            "HARNESS_CONTEXT|this serial role already has an active agent; "
            "return ENV"
        )
    return (
        "HARNESS_CONTEXT|concurrent independent agent work is advisory; "
        "researcher is the only multi-agent role"
    )


def writer_reserved(cwd, session_id):
    active = any(
        entry.get("cwd") == os.path.realpath(cwd)
        and entry.get("session_id") == str(session_id)
        and entry.get("agent_type") in WRITER_AGENTS
        and entry.get("state") in ACTIVE_MAILBOX_STATES
        for entry in gatelib.agent_mailbox_entries(cwd, session_id)
    )
    queued = any(role in WRITER_AGENTS for role in agent_dispatch.roles(cwd, session_id))
    return active or queued


def reviewer_context(cwd, session_id):
    turn = gatelib.read_turn_record(cwd, session_id)
    digest, paths, affected = gatelib.review_target_details(cwd, turn)
    if not turn or not digest:
        return "HARNESS_CONTEXT|review target or affected-consumer evidence is unavailable; return ENV without reviewing", ""
    lines = [
        "HARNESS_REVIEW_CONTEXT|immutable target; do not spawn another agent",
        "review-target|%s|%s|%d" % (turn["head"], digest, len(paths)),
    ]
    lines.extend("changed-path|%s" % path for path in paths)
    lines.extend("affected-path|%s" % path for path in affected)
    return "\n".join(lines), digest


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    payload = gatelib.read_payload()
    candidate = payload.get("cwd") if isinstance(payload, dict) else os.getcwd()
    if not gatelib.is_roblox_project(candidate):
        return 0
    if payload is None:
        return context("HARNESS_CONTEXT|malformed SubagentStart payload; do not mutate project state")
    payload = agent_payload.normalize(payload, "start")
    cwd = payload.get("cwd") or os.getcwd()
    if not gatelib.is_roblox_project(cwd):
        return 0
    scope = gatelib.hook_scope(argv)
    host = gatelib.hook_host(argv, payload)
    authorized, detail = gatelib.session_authorization_status(payload, cwd, scope, "SubagentStart", host)
    degraded = False
    repairs = []
    if not authorized:
        degraded, degraded_detail, repairs, _ = gatelib.session_recovery_status(
            payload,
            cwd,
            scope,
            "SubagentStart",
            host,
        )
        if not degraded:
            return context(
                "HARNESS_CONTEXT|session is not authorized: %s; do not mutate project state"
                % (degraded_detail or detail)
            )
    session_id = payload.get("session_id") or ""
    agent_id = payload.get("agent_id") or ""
    reported_agent = payload.get("agent_type") or ""
    reported_name = payload.get("agent_name") or ""
    agent = reported_agent or reported_name
    if not session_id or not agent_id:
        return context("HARNESS_CONTEXT|SubagentStart identity is incomplete; do not mutate project state")
    claimed = False
    dispatch_record = {}

    def release_dispatch():
        nonlocal claimed
        if claimed:
            agent_dispatch.release(cwd, session_id, agent_id)
            claimed = False

    if degraded:
        gatelib.fail_review_receipt(cwd, session_id, agent_id)
        gatelib.agent_mailbox_delete(cwd, session_id, agent_id)
        return context(
            "HARNESS_CONTEXT|a degraded session cannot dispatch a child; remain read-only. "
            "The primary agent must run the listed exact recovery command"
        )
    turn = gatelib.read_turn_record(cwd, session_id)
    if not isinstance(turn, dict) or not turn.get("turn_id"):
        gatelib.fail_review_receipt(cwd, session_id, agent_id)
        gatelib.agent_mailbox_delete(cwd, session_id, agent_id)
        return context(
            "HARNESS_CONTEXT|no current turn baseline is bound to this agent; "
            "remain read-only and do not return harness evidence"
        )
    gatelib.cleanup_review_receipts(cwd)
    if agent in ("", "default"):
        dispatch_record = agent_dispatch.claim_record(cwd, session_id, agent_id, reported_name)
        if not dispatch_record and reported_name:
            dispatch_record = agent_dispatch.claim_record(cwd, session_id, agent_id)
        agent = dispatch_record.get("role", "")
        claimed = bool(dispatch_record)
        if not agent:
            gatelib.fail_review_receipt(cwd, session_id, agent_id)
            gatelib.agent_mailbox_delete(cwd, session_id, agent_id)
            return context(
                "HARNESS_CONTEXT|this dispatch has no bound harness role; remain read-only, "
                "do not spawn another agent, and do not return harness evidence"
            )
    elif agent in AGENTS:
        dispatch_record = agent_dispatch.claim_record(
            cwd,
            session_id,
            agent_id,
            reported_name or agent,
        )
        claimed = bool(dispatch_record)
    if agent == "maintainer" and (
        not claimed
        or dispatch_record.get("role") != "maintainer"
        or dispatch_record.get("recovery_kind") not in gatelib.RECOVERY_KINDS
    ):
        gatelib.fail_review_receipt(cwd, session_id, agent_id)
        gatelib.agent_mailbox_delete(cwd, session_id, agent_id)
        release_dispatch()
        return context(
            "HARNESS_CONTEXT|maintainer authority is not bound to one exact recovery; "
            "remain read-only and return ENV"
        )
    if agent == "reviewer":
        if writer_reserved(cwd, session_id):
            release_dispatch()
            return context("HARNESS_CONTEXT|a debugger mutation lease is active or queued; return ENV without reviewing")
        if gatelib.pending_review_receipts(cwd, session_id):
            release_dispatch()
            return context("HARNESS_CONTEXT|another reviewer is active; return ENV without reviewing")
        review_context, expected_digest = reviewer_context(cwd, session_id)
        if not expected_digest:
            gatelib.fail_review_receipt(cwd, session_id, agent_id)
            gatelib.agent_mailbox_delete(cwd, session_id, agent_id)
            release_dispatch()
            return context(review_context)
        gatelib.agent_mailbox_write(
            cwd,
            session_id,
            agent_id,
            agent_type="reviewer",
            state="reviewing",
            overlap=False,
            result="",
            repair_attempted=False,
        )
        if not gatelib.start_review_receipt(
            cwd,
            session_id,
            agent_id,
            expected_digest=expected_digest,
        ):
            gatelib.agent_mailbox_delete(cwd, session_id, agent_id)
            release_dispatch()
            return context("HARNESS_CONTEXT|review target is unavailable; return ENV without reviewing")
        return context(review_context)
    if agent not in AGENTS:
        gatelib.fail_review_receipt(cwd, session_id, agent_id)
        gatelib.agent_mailbox_delete(cwd, session_id, agent_id)
        return context("HARNESS_CONTEXT|unknown harness role; remain read-only and do not return harness evidence")
    if agent in WRITER_AGENTS and (
        "reviewer" in agent_dispatch.roles(cwd, session_id)
        or gatelib.pending_review_receipts(cwd, session_id)
    ):
        gatelib.fail_review_receipt(cwd, session_id, agent_id)
        gatelib.agent_mailbox_delete(cwd, session_id, agent_id)
        release_dispatch()
        return context("HARNESS_CONTEXT|a reviewer is active or queued; do not mutate project state; return ENV")
    gatelib.fail_review_receipt(cwd, session_id, agent_id)
    active, writer_conflict = mailbox_concurrency(cwd, session_id, agent_id, agent)
    mailbox_changes = {
        "agent_type": agent,
        "state": "overlap" if writer_conflict else "pending",
        "overlap": writer_conflict,
        "concurrent": bool(active),
        "result": "",
        "repair_attempted": False,
        "lease_paths": dispatch_record.get("lease_paths") or (["tests/"] if agent == "debugger" else []),
        "dispatch_fingerprint": dispatch_record.get("fingerprint", ""),
    }
    if agent == "maintainer":
        mailbox_changes["recovery_kind"] = dispatch_record["recovery_kind"]
    gatelib.agent_mailbox_write(cwd, session_id, agent_id, **mailbox_changes)
    if writer_conflict or active:
        return context(concurrency_context(writer_conflict))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as error:
        sys.exit(context("HARNESS_CONTEXT|SubagentStart gate failed: %s: %s" % (type(error).__name__, str(error)[:160])))
