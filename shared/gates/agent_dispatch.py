"""Bind a ruled agent role to its documented dispatch before SubagentStart."""

import hashlib
import json
import os
import re
import time
from contextlib import contextmanager


AGENTS = frozenset(("reviewer", "debugger", "optimizer", "researcher", "maintainer"))
WRITERS = frozenset(("debugger",))
SERIAL_ROLES = frozenset(("reviewer", "debugger", "optimizer", "maintainer"))
ACTIVE_STATES = frozenset(("queued", "claimed", "repairable"))
MAX_AGE = 120.0
LOCK_TIMEOUT = 5.0
STALE_LOCK_AGE = 30.0


def _key(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:20]


def _path(cwd, session_id):
    return os.path.join(cwd, "gates", ".agent-dispatch-s%s.json" % _key(session_id))


def _turn_id(cwd, session_id):
    path = os.path.join(cwd, "gates", ".turn-s%s" % _key(session_id))
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, ValueError, UnicodeError):
        return ""
    return str(value.get("turn_id") or "") if isinstance(value, dict) else ""


def normalize_prompt(value):
    return " ".join(str(value or "").split())


def normalize_paths(cwd, paths):
    if isinstance(paths, str):
        paths = [paths]
    if not isinstance(paths, (list, tuple, set)):
        return []
    root = os.path.realpath(cwd)
    normalized = []
    for value in paths:
        if not isinstance(value, str) or not value.strip():
            continue
        path = value if os.path.isabs(value) else os.path.join(root, value)
        path = os.path.realpath(path)
        try:
            if os.path.commonpath((root, path)) != root:
                continue
        except ValueError:
            continue
        relative = os.path.relpath(path, root).replace(os.sep, "/")
        normalized.append(relative.rstrip("/"))
    return sorted(set(normalized))


def fingerprint(cwd, session_id, role, prompt="", target_digest=""):
    payload = "\0".join(
        (
            str(session_id),
            _turn_id(cwd, session_id),
            str(role),
            normalize_prompt(prompt),
            str(target_digest or ""),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@contextmanager
def _locked(cwd, session_id):
    """Serialize queue arbitration across concurrent hook processes."""
    directory = os.path.join(cwd, "gates")
    os.makedirs(directory, exist_ok=True)
    lock = _path(cwd, session_id) + ".lock"
    deadline = time.monotonic() + LOCK_TIMEOUT
    while True:
        try:
            os.mkdir(lock)
            break
        except FileExistsError:
            try:
                stale = time.time() - os.stat(lock).st_mtime > STALE_LOCK_AGE
            except OSError:
                stale = False
            if stale:
                try:
                    os.rmdir(lock)
                    continue
                except OSError:
                    pass
            if time.monotonic() >= deadline:
                raise OSError("agent dispatch lock timed out")
            time.sleep(0.01)
    try:
        yield
    finally:
        try:
            os.rmdir(lock)
        except OSError:
            pass


def _read(cwd, session_id, now=None):
    now = time.time() if now is None else float(now)
    try:
        with open(_path(cwd, session_id), encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, ValueError, UnicodeError):
        return []
    schema = value.get("schema") if isinstance(value, dict) else None
    entries = value.get("entries") if schema in (1, 2) else None
    if not isinstance(entries, list):
        return []
    current_turn = _turn_id(cwd, session_id)
    valid = []
    for source in entries:
        if (
            not isinstance(source, dict)
            or source.get("role") not in AGENTS
            or not isinstance(source.get("queued_at"), (int, float))
            or not 0 <= now - float(source["queued_at"]) <= MAX_AGE
        ):
            continue
        entry = dict(source)
        if schema == 1:
            entry["state"] = "claimed" if entry.get("claimed_by") else "queued"
            entry["turn_id"] = current_turn
            entry["fingerprint"] = fingerprint(
                cwd,
                session_id,
                entry["role"],
                entry.get("task_name", ""),
                "legacy",
            )
            entry.setdefault("lease_paths", [])
            entry.setdefault("repair_count", 0)
        if entry.get("state") not in ACTIVE_STATES | {"accepted"}:
            continue
        if current_turn and entry.get("turn_id") != current_turn:
            continue
        valid.append(entry)
    return valid


def _write(cwd, session_id, entries):
    path = _path(cwd, session_id)
    if not entries:
        try:
            os.remove(path)
        except OSError:
            pass
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp-%d" % os.getpid()
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump({"schema": 2, "entries": entries}, handle, sort_keys=True)
        handle.write("\n")
    os.replace(temporary, path)


def tool_is_spawn(tool_name):
    name = re.sub(r"[^a-z0-9]", "", str(tool_name or "").casefold())
    return name in (
        "agent",
        "spawnagent",
        "collaborationspawnagent",
        "functionsspawnagent",
        "functionscollaborationspawnagent",
    )


def dispatch_role(tool_name, tool_input):
    if not tool_is_spawn(tool_name) or not isinstance(tool_input, dict):
        return ""
    for field in ("agent_type", "agent_name", "subagent_type", "task_name", "name"):
        value = tool_input.get(field)
        if isinstance(value, str) and value in AGENTS:
            return value
    return ""


def queue(cwd, session_id, role, task_name="", now=None, recovery_kind=""):
    reserved, _ = reserve(
        cwd,
        session_id,
        role,
        task_name,
        now,
        enforce_conflicts=False,
        recovery_kind=recovery_kind,
    )
    return reserved


def reserve(
    cwd,
    session_id,
    role,
    task_name="",
    now=None,
    enforce_conflicts=True,
    recovery_kind="",
    prompt="",
    target_digest="",
    paths=None,
):
    """Atomically validate and reserve one dispatch role."""
    if not session_id or role not in AGENTS:
        return False, "invalid"
    requested_now = None if now is None else float(now)
    with _locked(cwd, session_id):
        now = time.time() if requested_now is None else requested_now
        entries = _read(cwd, session_id, now)
        dispatch_fingerprint = fingerprint(cwd, session_id, role, prompt or task_name, target_digest)
        matching = next((entry for entry in entries if entry.get("fingerprint") == dispatch_fingerprint), None)
        if matching:
            if matching.get("state") == "accepted":
                return False, "accepted"
            if matching.get("state") == "repairable" and int(matching.get("repair_count", 0)) < 1:
                matching.update(
                    {
                        "state": "queued",
                        "queued_at": now,
                        "repair_count": 1,
                    }
                )
                matching.pop("claimed_by", None)
                matching.pop("claimed_at", None)
                _write(cwd, session_id, entries)
                return True, "repair"
            return False, "duplicate"
        active = [entry for entry in entries if entry.get("state") in ACTIVE_STATES]
        queued = [entry["role"] for entry in active]
        if enforce_conflicts:
            if role in SERIAL_ROLES and role in queued:
                return False, role
            if role == "reviewer" and any(candidate in WRITERS for candidate in queued):
                return False, "writer"
            if role in WRITERS and "reviewer" in queued:
                return False, "reviewer"
        entry = {
            "role": role,
            "task_name": str(task_name or ""),
            "queued_at": now,
            "turn_id": _turn_id(cwd, session_id),
            "state": "queued",
            "fingerprint": dispatch_fingerprint,
            "target_digest": str(target_digest or ""),
            "lease_paths": normalize_paths(cwd, paths),
            "repair_count": 0,
        }
        if recovery_kind:
            entry["recovery_kind"] = str(recovery_kind)
        entries.append(entry)
        _write(cwd, session_id, entries)
    return True, ""


def roles(cwd, session_id, now=None):
    with _locked(cwd, session_id):
        return [
            entry["role"]
            for entry in _read(cwd, session_id, now)
            if entry.get("state") in ACTIVE_STATES
        ]


def entries(cwd, session_id, now=None):
    with _locked(cwd, session_id):
        return [dict(entry) for entry in _read(cwd, session_id, now)]


def accepted_result(cwd, session_id, role, prompt="", target_digest="", now=None):
    wanted = fingerprint(cwd, session_id, role, prompt, target_digest)
    with _locked(cwd, session_id):
        entry = next(
            (
                item
                for item in _read(cwd, session_id, now)
                if item.get("fingerprint") == wanted and item.get("state") == "accepted"
            ),
            None,
        )
    return str(entry.get("result") or "") if entry else ""


def consume(cwd, session_id, reported_name="", now=None):
    with _locked(cwd, session_id):
        entries = _read(cwd, session_id, now)
        index = _match(entries, reported_name)
        if index is None:
            return ""
        entry = entries.pop(index)
        _write(cwd, session_id, entries)
        return entry["role"]


def _match(entries, reported_name):
    available = [
        (index, entry)
        for index, entry in enumerate(entries)
        if entry.get("state") == "queued" and not entry.get("claimed_by")
    ]
    if not available:
        return None
    if not reported_name:
        return available[0][0]
    for index, entry in available:
        if entry.get("task_name") == reported_name or entry.get("role") == reported_name:
            return index
    return None


def claim(cwd, session_id, agent_id, reported_name="", now=None):
    """Keep a consumed role reserved until its mailbox becomes visible."""
    entry = claim_record(cwd, session_id, agent_id, reported_name, now)
    return entry.get("role", "") if entry else ""


def claim_record(cwd, session_id, agent_id, reported_name="", now=None):
    """Claim and return the complete dispatch authority record."""
    if not agent_id:
        return {}
    requested_now = None if now is None else float(now)
    with _locked(cwd, session_id):
        now = time.time() if requested_now is None else requested_now
        entries = _read(cwd, session_id, now)
        index = _match(entries, reported_name)
        if index is None:
            return {}
        entries[index]["claimed_by"] = str(agent_id)
        entries[index]["claimed_at"] = now
        entries[index]["state"] = "claimed"
        _write(cwd, session_id, entries)
        return dict(entries[index])


def release(cwd, session_id, agent_id):
    if not agent_id:
        return
    with _locked(cwd, session_id):
        entries = _read(cwd, session_id)
        retained = [entry for entry in entries if entry.get("claimed_by") != str(agent_id)]
        _write(cwd, session_id, retained)


def finish(cwd, session_id, agent_id, state, result=""):
    if state not in ("accepted", "repairable") or not agent_id:
        return False
    with _locked(cwd, session_id):
        entries = _read(cwd, session_id)
        entry = next(
            (item for item in entries if item.get("claimed_by") == str(agent_id)),
            None,
        )
        if not entry:
            return False
        entry["state"] = state
        entry["completed_at"] = time.time()
        if state == "accepted":
            entry["result"] = str(result or "")
        _write(cwd, session_id, entries)
    return True


def clear(cwd, session_id):
    with _locked(cwd, session_id):
        _write(cwd, session_id, [])
