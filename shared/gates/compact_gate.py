#!/usr/bin/env python3
"""compact-gate — PreCompact handoff normalizer [R GATE7].

Every compaction receives the same bounded four-scalar handoff. Missing,
stale, and legacy handoffs are repaired atomically; only missing session
identity or a failed write denies compaction.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gatelib  # noqa: E402

HANDOFF_FIELDS = ("session", "tried", "where", "open")
MAX_SCALAR_BYTES = 1024
MAX_HANDOFF_BYTES = len(HANDOFF_FIELDS) * (MAX_SCALAR_BYTES + 16)
AUTO_STATE_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:agents|changed|review|session|turn)\s*=",
    re.IGNORECASE,
)
FAILURE_RE = re.compile(r"\b(?:blocked|crash(?:ed)?|error|fail(?:ed|ure)?|missing|rejected|timeout|unavailable)\b", re.IGNORECASE)
UNFINISHED_RE = re.compile(r"\b(?:awaiting|blocked|broken|failing|incomplete|pending|unfinished|working)\b", re.IGNORECASE)
DECISION_RE = re.compile(r"\b(?:approve|choose|confirm|decide|decision|human|select|whether)\b", re.IGNORECASE)


def bounded_scalar(value):
    """Return one printable, bounded line; ``void`` is the empty scalar."""
    if not isinstance(value, str):
        return "void"
    value = "".join(" " if ord(character) < 32 or ord(character) == 127 else character for character in value)
    value = " ".join(value.split())
    if not value:
        return "void"
    encoded = value.encode("utf-8")
    if len(encoded) <= MAX_SCALAR_BYTES:
        return value
    encoded = encoded[:MAX_SCALAR_BYTES]
    while True:
        try:
            return encoded.decode("utf-8").rstrip() or "void"
        except UnicodeDecodeError as error:
            encoded = encoded[: error.start]


def derived_handoff(cwd, session_id):
    """Return no invented facts; disk state cannot identify these semantics."""
    del cwd, session_id
    return {"tried": "void", "where": "void", "open": "void"}


def same_turn_evidence(cwd, session_id, handoff_path):
    """Return validation evidence without rendering machine state into handoff."""
    turn = gatelib.read_turn_record(cwd, session_id)
    if not turn:
        return {"active": False, "changed": set()}
    try:
        handoff_mtime = os.stat(handoff_path).st_mtime
    except OSError:
        handoff_mtime = 0
    if handoff_mtime < float(turn.get("started_at", 0)):
        return {"active": False, "changed": set()}
    try:
        changed = {
            path.replace(os.sep, "/")
            for path in gatelib.changed_paths_since_turn(cwd, turn)
            if path.replace(os.sep, "/") != gatelib.HANDOFF_RELATIVE
        }
    except OSError:
        changed = set()
    mailboxes = gatelib.agent_mailbox_entries(cwd, session_id)
    mutation = gatelib.mutation_check_current(cwd, session_id, turn)
    return {
        "active": bool(changed or mailboxes or mutation),
        "changed": changed,
    }


def mentions_changed_path(value, changed):
    normalized = value.replace("\\", "/")
    return any(path and path in normalized for path in changed)


def valid_handoff_fact(field, value, evidence):
    if value == "void" or AUTO_STATE_RE.search(value) or not evidence["active"]:
        return False
    if field == "tried":
        return bool(FAILURE_RE.search(value)) and mentions_changed_path(value, evidence["changed"])
    if field == "where":
        return bool(UNFINISHED_RE.search(value)) and mentions_changed_path(value, evidence["changed"])
    if field == "open":
        return bool(DECISION_RE.search(value))
    return False


def normalize_handoff(path, session_id, cwd=None):
    facts = {}
    current = ""
    try:
        with open(path, encoding="utf-8") as handle:
            current = handle.read(MAX_HANDOFF_BYTES + 1)
    except (OSError, UnicodeError):
        pass

    for line in current.splitlines():
        key, separator, value = line.partition(":")
        if separator and key in HANDOFF_FIELDS and key not in facts:
            facts[key] = bounded_scalar(value)
    current_session = bounded_scalar(session_id)
    if facts.get("session") != current_session:
        facts = {}
    facts["session"] = current_session
    project_root = cwd or os.path.dirname(os.path.dirname(os.path.abspath(path)))
    derived = derived_handoff(project_root, session_id)
    evidence = same_turn_evidence(project_root, session_id, path)
    for field in HANDOFF_FIELDS[1:]:
        existing = facts.get(field, "void")
        if not valid_handoff_fact(field, existing, evidence):
            facts[field] = derived[field]
    normalized = "".join(
        "%s: %s\n" % (field, facts.get(field, "void"))
        for field in HANDOFF_FIELDS
    )
    if current != normalized:
        gatelib._atomic_text(path, normalized)
    return normalized


def main(argv=None):
    payload = gatelib.read_payload()
    candidate = payload.get("cwd") if isinstance(payload, dict) else os.getcwd()
    if not gatelib.is_roblox_project(candidate):
        return 0
    if not isinstance(payload, dict):
        sys.stderr.write(
            "compact-gate: BLOCKED\n\n"
            "0|0|GATE7|session identity absent|start a new session before compacting\n"
        )
        return 2
    cwd = payload.get("cwd") or os.getcwd()
    session_id = payload.get("session_id", "")
    if not isinstance(session_id, str) or not session_id.split():
        sys.stderr.write(
            "compact-gate: BLOCKED\n\n"
            "0|0|GATE7|session identity absent|start a new session before compacting\n"
        )
        return 2
    handoff = os.path.join(cwd, gatelib.HANDOFF_RELATIVE)
    try:
        content = normalize_handoff(handoff, session_id, cwd)
    except (OSError, UnicodeError) as error:
        sys.stderr.write(
            "compact-gate: BLOCKED\n\n"
            "0|0|GATE7|handoff cannot be written: %s|repair project write access, then compact again\n"
            % str(error)[:160]
        )
        return 2
    sys.stdout.write(content)  # becomes newCustomInstructions
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        sys.stderr.write("compact-gate: BLOCKED\n\ngate crashed: %s: %s\n" % (type(e).__name__, e))
        sys.exit(2)
