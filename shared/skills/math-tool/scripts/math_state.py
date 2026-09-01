#!/usr/bin/env python3
"""Deterministic classification and bounded external state for math-tool."""

import contextlib
import hashlib
import json
import os
import re
import shutil
import stat
import time
import unicodedata


PROTOCOL_VERSION = 1
CLASSIFIER_VERSION = "math-trigger-v1"
TRIGGER_CLASSES = (
    "arithmetic",
    "algebra",
    "calculus",
    "linear_algebra",
    "probability_statistics",
    "number_theory",
    "geometry_trigonometry",
)
CONTINUATION_PREFIX = "MATH_TOOL_GATE:v1:"
STATE_TTL_SECONDS = 24 * 60 * 60
RECEIPT_RETENTION_SECONDS = 7 * 24 * 60 * 60
TELEMETRY_LIMIT_BYTES = 1024 * 1024
TELEMETRY_FILES = 4
MAX_STATE_BYTES = 64 * 1024
_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def digest_json(value):
    return digest_bytes(canonical_json(value).encode("utf-8"))


def file_digest(path):
    with open(path, "rb") as handle:
        return digest_bytes(handle.read())


def session_key(session_id):
    return digest_bytes(str(session_id).encode("utf-8"))


def cache_root():
    configured = os.environ.get("MATH_TOOL_RUNTIME_ROOT")
    if configured:
        return os.path.realpath(configured)
    return os.path.realpath(os.path.join(os.path.expanduser("~"), ".cache", "harness", "math-tool"))


def state_dir(host, session_id, root=None):
    if host not in ("codex", "claude"):
        raise ValueError("unsupported math-tool host")
    return os.path.join(os.path.realpath(root or cache_root()), host, session_key(session_id))


def _ensure_private_dir(path):
    os.makedirs(path, mode=0o700, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


@contextlib.contextmanager
def state_lock(directory):
    """Take the one session lock used by all state operations."""
    _ensure_private_dir(directory)
    path = os.path.join(directory, "state.lock")
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    os.chmod(path, 0o600)
    handle = os.fdopen(descriptor, "r+b", buffering=0)
    try:
        if os.name == "nt":
            import msvcrt

            if os.path.getsize(path) == 0:
                handle.write(b"\0")
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def atomic_write(path, value):
    """Write one mode-0600 JSON object with atomic replacement."""
    if not isinstance(value, dict):
        raise ValueError("state value must be an object")
    encoded = (canonical_json(value) + "\n").encode("utf-8")
    if len(encoded) > MAX_STATE_BYTES:
        raise ValueError("state object exceeds size limit")
    directory = os.path.dirname(path)
    _ensure_private_dir(directory)
    temporary = os.path.join(directory, ".%s.%d.tmp" % (os.path.basename(path), os.getpid()))
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def read_state(directory, name, now=None):
    if name not in ("authorization", "obligation", "receipt"):
        raise ValueError("unknown state record")
    path = os.path.join(directory, name + ".json")
    try:
        if os.path.getsize(path) > MAX_STATE_BYTES:
            raise ValueError("state file exceeds size limit")
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError:
        return None
    if not isinstance(value, dict) or value.get("v") != PROTOCOL_VERSION:
        raise ValueError("state record is malformed")
    timestamp = value.get("sealed") if name == "receipt" else value.get("created")
    limit = RECEIPT_RETENTION_SECONDS if name == "receipt" else STATE_TTL_SECONDS
    current = time.time() if now is None else now
    if not isinstance(timestamp, (int, float)) or current - timestamp > limit or timestamp > current + 300:
        return None
    return value


def authorize(directory, record):
    value = dict(record)
    value.update({"v": PROTOCOL_VERSION, "created": time.time()})
    atomic_write(os.path.join(directory, "authorization.json"), value)
    return value


def _normalize_prompt(text):
    normalized = unicodedata.normalize("NFKC", text)
    characters = []
    for character in normalized:
        try:
            characters.append(str(unicodedata.digit(character)))
        except (TypeError, ValueError):
            characters.append(character)
    return "".join(characters).translate(str.maketrans({"×": "*", "÷": "/", "−": "-", "＋": "+"}))


def _remove_quoted_and_code(text):
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`[^`\n]*`", " ", text)
    text = re.sub(r'"(?:\\.|[^"\\])*"', " ", text)
    text = re.sub(r"'[^'\n]{1,200}'", " ", text)
    return text


def classify_prompt(prompt, active=None):
    """Return one supported task class, or None, without an LLM call."""
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt.encode("utf-8")) > 128 * 1024:
        return None
    normalized = _normalize_prompt(prompt)
    continuation = re.search(r"(?:^|\s)%s([0-9a-f]{32})(?:\s|$)" % re.escape(CONTINUATION_PREFIX), normalized)
    if continuation:
        if active and continuation.group(1) == active.get("id") and active.get("status") == "active":
            return active.get("task_class")
        return None
    visible = _remove_quoted_and_code(normalized).strip().casefold()
    if not visible:
        return None
    if re.search(
        r"\b(?:do not|don't|dont|no need to|without)\s+(?:use\s+(?:the\s+)?math[- ]tool|calculate|compute|evaluate|solve|differentiate|integrate|simplify)\b",
        visible,
    ):
        return None

    patterns = (
        (
            "linear_algebra",
            r"\b(?:matrix|matrices|determinant|eigenvalue|eigenvector|rref|row[- ]reduce|matrix inverse|matrix rank|trace of (?:the )?matrix)\b",
        ),
        (
            "calculus",
            r"\b(?:differentiat(?:e|ion)|derivative|integrat(?:e|ion|al)|antiderivative|limit\s+(?:of|as)|calculus)\b",
        ),
        (
            "probability_statistics",
            r"\b(?:probability|mean|median|variance|standard deviation|std\.? dev|average|permutation|combination|binomial)\b",
        ),
        (
            "number_theory",
            r"\b(?:greatest common divisor|least common multiple|\bgcd\b|\blcm\b|prime factor|factorial|modular|congruence|divisibility)\b",
        ),
        (
            "geometry_trigonometry",
            r"\b(?:sine|cosine|tangent|\bsin\b|\bcos\b|\btan\b|trigonometry|hypotenuse|pythagorean|area|perimeter|circumference|angle)\b",
        ),
        (
            "algebra",
            r"\b(?:solve\s+(?:for|the equation)|simplify\s+(?:the\s+)?expression|factor\s+(?:the\s+)?(?:polynomial|expression)|expand\s+(?:the\s+)?expression|polynomial|quadratic|algebra)\b",
        ),
    )
    for task_class, pattern in patterns:
        if re.search(pattern, visible):
            return task_class
    numeric_expression = re.search(r"(?<![\w.])[-+]?\d+(?:\.\d+)?\s*(?:\+|\*|/|\^|%|=)\s*[-+]?\d+(?:\.\d+)?(?![\w.])", visible)
    spaced_subtraction = re.search(r"(?<![\w.])[-+]?\d+(?:\.\d+)?\s+-\s+[-+]?\d+(?:\.\d+)?(?![\w.])", visible)
    bare_subtraction = re.fullmatch(r"\s*[-+]?\d+(?:\.\d+)?-[-+]?\d+(?:\.\d+)?[?!.]?\s*", visible)
    math_call = re.search(r"\b(?:sqrt|log|exp)\s*\(|\d+\s*!", visible)
    if numeric_expression or spaced_subtraction or bare_subtraction or math_call:
        return "arithmetic"
    if re.search(r"\b(?:calculate|compute|evaluate|what is|find the (?:sum|product|quotient|difference))\b", visible) and re.search(
        r"\d|\b(?:pi|sqrt|square root|percent)\b", visible
    ):
        return "arithmetic"
    return None


def create_obligation(directory, authorization, prompt, task_class, turn_id, route=None, reasoning=None):
    prompt_digest = digest_bytes(prompt.encode("utf-8"))
    identity = {
        "host": authorization["host"],
        "session": authorization["session"],
        "turn": turn_id,
        "prompt_digest": prompt_digest,
        "classifier": CLASSIFIER_VERSION,
        "skill_digest": authorization["skill_digest"],
        "tool_digest": authorization["tool_digest"],
        "runtime_lock_digest": authorization["runtime_lock_digest"],
    }
    obligation_id = digest_json(identity)[:32]
    now = time.time()
    value = {
        "v": PROTOCOL_VERSION,
        "host": authorization["host"],
        "session": authorization["session"],
        "turn": turn_id,
        "id": obligation_id,
        "task_class": task_class,
        "prompt_digest": prompt_digest,
        "classifier": CLASSIFIER_VERSION,
        "protocol": PROTOCOL_VERSION,
        "protocol_digest": authorization["protocol_digest"],
        "skill_digest": authorization["skill_digest"],
        "tool_digest": authorization["tool_digest"],
        "runtime_lock_digest": authorization["runtime_lock_digest"],
        "sympy": authorization["sympy"],
        "created": now,
        "status": "active",
        "tool_calls": 0,
        "retries": 0,
        "continuations": 0,
        "repair_allowed": False,
        "terminal_recorded": False,
        "route": route,
        "reasoning": reasoning,
    }
    atomic_write(os.path.join(directory, "obligation.json"), value)
    try:
        os.unlink(os.path.join(directory, "receipt.json"))
    except FileNotFoundError:
        pass
    append_telemetry(directory, telemetry_record(value, "start", accepted=None, failure=None))
    return value


def telemetry_record(obligation, event, accepted, failure, latency=None, usage=None, cost=None):
    usage = usage if isinstance(usage, dict) else {}
    input_tokens = usage.get("input_tokens") if isinstance(usage.get("input_tokens"), int) else None
    output_tokens = usage.get("output_tokens") if isinstance(usage.get("output_tokens"), int) else None
    total_tokens = input_tokens + output_tokens if input_tokens is not None and output_tokens is not None else None
    return {
        "v": PROTOCOL_VERSION,
        "event": event,
        "obligation": obligation.get("id"),
        "task_class": obligation.get("task_class"),
        "route": obligation.get("route"),
        "reasoning": obligation.get("reasoning"),
        "agents": 0,
        "tool_calls": obligation.get("tool_calls", 0),
        "retries": obligation.get("retries", 0),
        "steps": min(4, 1 + obligation.get("tool_calls", 0) + obligation.get("continuations", 0)),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": usage.get("cached_input_tokens") if isinstance(usage.get("cached_input_tokens"), int) else None,
        "total_tokens": total_tokens,
        "accepted": accepted,
        "failure": failure,
        "latency": latency,
        "cost": cost,
        "TPA": None,
        "cost_per_accepted": None,
        "recorded": time.time(),
    }


def _rotate_telemetry(path, incoming):
    try:
        current = os.path.getsize(path)
    except OSError:
        current = 0
    if current + incoming <= TELEMETRY_LIMIT_BYTES:
        return
    oldest = path + ".%d" % (TELEMETRY_FILES - 1)
    try:
        os.unlink(oldest)
    except FileNotFoundError:
        pass
    for index in range(TELEMETRY_FILES - 2, 0, -1):
        source = path + ".%d" % index
        destination = path + ".%d" % (index + 1)
        try:
            os.replace(source, destination)
        except FileNotFoundError:
            pass
    try:
        os.replace(path, path + ".1")
    except FileNotFoundError:
        pass


def append_telemetry(directory, record):
    encoded = (canonical_json(record) + "\n").encode("utf-8")
    if len(encoded) > 8192:
        raise ValueError("telemetry record exceeds size limit")
    _ensure_private_dir(directory)
    path = os.path.join(directory, "telemetry.jsonl")
    _rotate_telemetry(path, len(encoded))
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(descriptor, "ab") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(path, 0o600)


def mark_terminal(directory, obligation, status, failure=None, latency=None, usage=None, cost=None):
    if obligation.get("terminal_recorded"):
        return obligation
    value = dict(obligation)
    value["status"] = status
    value["terminal_recorded"] = True
    value["terminal"] = time.time()
    value.pop("pending", None)
    value["repair_allowed"] = False
    if failure:
        value["failure"] = failure
    atomic_write(os.path.join(directory, "obligation.json"), value)
    append_telemetry(
        directory,
        telemetry_record(value, "terminal", accepted=status == "accepted", failure=failure, latency=latency, usage=usage, cost=cost),
    )
    return value


def seal_receipt(directory, obligation, request_digest, result, tool_use_id, authorization):
    receipt = {
        "v": PROTOCOL_VERSION,
        "obligation": obligation["id"],
        "request_digest": request_digest,
        "result_digest": result["digest"],
        "canonical": result["canonical"],
        "tool_use_id": tool_use_id,
        "sympy": authorization["sympy"],
        "tool_digest": authorization["tool_digest"],
        "protocol_digest": authorization["protocol_digest"],
        "runtime_lock_digest": authorization["runtime_lock_digest"],
        "sealed": time.time(),
    }
    atomic_write(os.path.join(directory, "receipt.json"), receipt)
    value = dict(obligation)
    value.pop("pending", None)
    value["repair_allowed"] = False
    value["receipt_sealed"] = receipt["sealed"]
    atomic_write(os.path.join(directory, "obligation.json"), value)
    return receipt


def aggregate_routes(directory):
    records = []
    for suffix in (".3", ".2", ".1", ""):
        path = os.path.join(directory, "telemetry.jsonl" + suffix)
        try:
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    value = json.loads(line)
                    if isinstance(value, dict) and value.get("event") == "terminal":
                        records.append(value)
        except FileNotFoundError:
            continue
    groups = {}
    for record in records:
        key = (record.get("task_class"), record.get("route"), record.get("reasoning"))
        group = groups.setdefault(key, {"tasks": 0, "accepted": 0, "total_tokens": 0, "cost": 0.0, "complete_usage": True, "complete_cost": True})
        group["tasks"] += 1
        group["accepted"] += 1 if record.get("accepted") else 0
        if isinstance(record.get("total_tokens"), int):
            group["total_tokens"] += record["total_tokens"]
        else:
            group["complete_usage"] = False
        if isinstance(record.get("cost"), (int, float)):
            group["cost"] += record["cost"]
        else:
            group["complete_cost"] = False
    output = []
    for key, group in sorted(groups.items(), key=lambda item: str(item[0])):
        accepted = group["accepted"]
        output.append(
            {
                "task_class": key[0],
                "route": key[1],
                "reasoning": key[2],
                "tasks": group["tasks"],
                "accepted": accepted,
                "TPA": group["total_tokens"] / accepted if accepted and group["complete_usage"] else None,
                "cost_per_accepted": group["cost"] / accepted if accepted and group["complete_cost"] else None,
            }
        )
    return output


def cleanup(root=None, now=None):
    """Expire only owned math state; retain receipts for seven days."""
    current = time.time() if now is None else now
    base = os.path.realpath(root or cache_root())
    for host in ("codex", "claude"):
        host_root = os.path.join(base, host)
        try:
            sessions = list(os.scandir(host_root))
        except FileNotFoundError:
            continue
        for session in sessions:
            if not session.is_dir(follow_symlinks=False):
                continue
            directory = session.path
            for name, limit in (("authorization.json", STATE_TTL_SECONDS), ("obligation.json", STATE_TTL_SECONDS), ("receipt.json", RECEIPT_RETENTION_SECONDS)):
                path = os.path.join(directory, name)
                try:
                    if current - os.path.getmtime(path) > limit:
                        os.unlink(path)
                except FileNotFoundError:
                    pass
            try:
                remaining = [entry.name for entry in os.scandir(directory) if entry.name != "state.lock"]
                if not remaining and current - os.path.getmtime(directory) > RECEIPT_RETENTION_SECONDS:
                    shutil.rmtree(directory)
            except FileNotFoundError:
                pass
