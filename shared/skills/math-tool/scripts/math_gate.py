#!/usr/bin/env python3
"""Unified Codex and Claude lifecycle gate for math-tool."""

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time

import math_state
import math_tool


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
SKILL_PATH = os.path.join(SKILL_DIR, "SKILL.md")
PROTOCOL_PATH = os.path.join(SKILL_DIR, "references", "protocol.md")
TOOL_PATH = os.path.join(SCRIPT_DIR, "math_tool.py")
LOCK_PATH = os.path.join(SCRIPT_DIR, "runtime.lock.json")
HOST_EVENTS = {
    "codex": ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "PreCompact", "SessionEnd"),
    "claude": (
        "SessionStart",
        "UserPromptSubmit",
        "PreToolUse",
        "PostToolUse",
        "PostToolUseFailure",
        "Stop",
        "PreCompact",
        "SessionEnd",
    ),
}
MAX_HOOK_INPUT_BYTES = 1024 * 1024
MAX_PROMPT_CONTEXT_BYTES = 720
MAX_REPAIR_CONTEXT_BYTES = 384
_MARKER_RE = re.compile(r"\[math-tool:v1:([0-9a-f]{32}):([0-9a-f]{64})\]")


class GateError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = " ".join(str(message).split())[:384]


def _emit(value):
    if value is not None:
        sys.stdout.write(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def _hook_context(event, text):
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


def _deny(event, reason):
    reason = " ".join(str(reason).split())[:384]
    if event == "PreToolUse":
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    return {"decision": "block", "reason": reason}


def _post_feedback(event, reason, context):
    reason = " ".join(str(reason).split())[:384]
    output = {"decision": "block", "reason": reason}
    output.update(_hook_context(event, context[:MAX_REPAIR_CONTEXT_BYTES]))
    return output


def _payload(event):
    raw = sys.stdin.buffer.read(MAX_HOOK_INPUT_BYTES + 1)
    if len(raw) > MAX_HOOK_INPUT_BYTES:
        raise GateError("payload_limit", "math-tool hook payload exceeds its byte limit")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise GateError("invalid_payload", "math-tool hook payload must be one JSON object")
    if not isinstance(value, dict) or value.get("hook_event_name") != event:
        raise GateError("invalid_event", "math-tool hook event identity does not match")
    session_id = value.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip() or len(session_id) > 512:
        raise GateError("invalid_session", "math-tool session identity is absent or malformed")
    cwd = value.get("cwd")
    if not isinstance(cwd, str) or not cwd or len(cwd.encode("utf-8")) > 8192:
        raise GateError("invalid_cwd", "math-tool hook working directory is absent or malformed")
    return value


def _validate_native_fields(host, event, payload):
    if event == "SessionStart":
        allowed = ("startup", "resume", "clear", "compact") + (("fork",) if host == "claude" else ())
        if payload.get("source") not in allowed:
            raise GateError("invalid_source", "math-tool SessionStart source is absent or malformed")
    if event == "UserPromptSubmit" and not isinstance(payload.get("prompt"), str):
        raise GateError("invalid_prompt", "math-tool prompt is absent or malformed")
    if event in ("PreToolUse", "PostToolUse", "PostToolUseFailure"):
        if not isinstance(payload.get("tool_name"), str) or not isinstance(payload.get("tool_input"), dict):
            raise GateError("invalid_tool", "math-tool tool identity is absent or malformed")
        if not isinstance(payload.get("tool_use_id"), str) or not payload.get("tool_use_id"):
            raise GateError("invalid_tool_use", "math-tool tool-use identity is absent or malformed")
    if event == "PreCompact" and payload.get("trigger") not in ("manual", "auto"):
        raise GateError("invalid_compact", "math-tool compaction trigger is absent or malformed")
    if event == "Stop" and not isinstance(payload.get("stop_hook_active"), bool):
        raise GateError("invalid_stop", "math-tool stop state is absent or malformed")
    if host == "codex" and event in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "PreCompact"):
        turn = payload.get("turn_id")
        if not isinstance(turn, str) or not turn.strip() or len(turn) > 512:
            raise GateError("invalid_turn", "math-tool turn identity is absent or malformed")


def _read_json(path):
    with open(path, encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise GateError("runtime_mismatch", "pinned runtime metadata is malformed")
    return value


def _runtime_status(run_probe=False):
    try:
        with open(LOCK_PATH, "rb") as handle:
            lock_bytes = handle.read()
        lock = json.loads(lock_bytes)
        stamp = _read_json(os.path.join(math_state.cache_root(), "runtime.json"))
    except (OSError, ValueError, UnicodeError) as error:
        raise GateError("runtime_unavailable", "pinned math runtime is unavailable: %s" % type(error).__name__)
    lock_digest = hashlib.sha256(lock_bytes).hexdigest()
    if lock.get("v") != 1 or stamp.get("v") != 1 or stamp.get("lock_digest") != lock_digest:
        raise GateError("runtime_mismatch", "pinned math runtime lock does not match")
    versions = {package.get("name"): package.get("version") for package in lock.get("packages", []) if isinstance(package, dict)}
    if versions != {"sympy": math_tool.SYMPY_VERSION, "mpmath": math_tool.MPMATH_VERSION}:
        raise GateError("runtime_mismatch", "runtime package pins do not match the tool")
    if stamp.get("sympy") != math_tool.SYMPY_VERSION or stamp.get("mpmath") != math_tool.MPMATH_VERSION:
        raise GateError("runtime_mismatch", "installed runtime versions do not match")
    runtime_python = stamp.get("python")
    venv = stamp.get("venv")
    if not isinstance(runtime_python, str) or not os.path.isfile(runtime_python) or not isinstance(venv, str):
        raise GateError("runtime_unavailable", "pinned runtime interpreter is unavailable")
    if run_probe:
        probe = subprocess.run(
            [runtime_python, "-B", "-c", "import json,mpmath,sympy;print(json.dumps([sympy.__version__,mpmath.__version__]))"],
            capture_output=True,
            text=True,
            timeout=15,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        )
        if probe.returncode != 0:
            raise GateError("runtime_unavailable", "pinned runtime probe failed")
        try:
            observed = json.loads(probe.stdout)
        except ValueError:
            raise GateError("runtime_mismatch", "pinned runtime probe returned malformed output")
        if observed != [math_tool.SYMPY_VERSION, math_tool.MPMATH_VERSION]:
            raise GateError("runtime_mismatch", "pinned runtime probe returned different versions")
    return {
        "runtime_python": os.path.realpath(runtime_python),
        "venv": os.path.realpath(venv),
        "runtime_lock_digest": lock_digest,
        "sympy": math_tool.SYMPY_VERSION,
        "mpmath": math_tool.MPMATH_VERSION,
    }


def _integrity(host, session_id, run_probe=False):
    runtime = _runtime_status(run_probe=run_probe)
    value = {
        "host": host,
        "session": math_state.session_key(session_id),
        "protocol": math_tool.PROTOCOL_VERSION,
        "classifier": math_state.CLASSIFIER_VERSION,
        "skill_digest": math_state.file_digest(SKILL_PATH),
        "protocol_digest": math_state.file_digest(PROTOCOL_PATH),
        "tool_digest": math_state.file_digest(TOOL_PATH),
        "gate_digest": math_state.file_digest(os.path.abspath(__file__)),
        "tool_path": os.path.realpath(TOOL_PATH),
    }
    value.update(runtime)
    return value


def _authorization_matches(authorization, host, session_id):
    if not authorization or authorization.get("status") != "ready":
        return False
    try:
        current = _integrity(host, session_id, run_probe=False)
    except GateError:
        return False
    for key, value in current.items():
        if authorization.get(key) != value:
            return False
    return True


def _turn_id(host, payload):
    if host == "codex":
        return payload["turn_id"]
    prompt = payload.get("prompt", "")
    return hashlib.sha256((payload["session_id"] + "\0" + prompt).encode("utf-8")).hexdigest()[:32]


def _split_command(command):
    if os.name != "nt":
        return shlex.split(command, posix=True)
    import ctypes

    count = ctypes.c_int()
    pointer = ctypes.windll.shell32.CommandLineToArgvW(command, ctypes.byref(count))
    if not pointer:
        raise ValueError("invalid Windows command")
    try:
        return [pointer[index] for index in range(count.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(pointer)


def canonical_command(authorization, request):
    arguments = [
        authorization["runtime_python"],
        "-B",
        authorization["tool_path"],
        "--request",
        math_state.canonical_json(request),
    ]
    return subprocess.list2cmdline(arguments) if os.name == "nt" else shlex.join(arguments)


def _command_form(authorization, obligation_id):
    example = {
        "v": 1,
        "obligation": obligation_id,
        "op": "<operation>",
        "ast": {"type": "<node>"},
    }
    return canonical_command(authorization, example)


def _prompt_context(authorization, obligation):
    text = (
        "%s%s Use $math-tool. Required pinned command form: %s. "
        "Canonical JSON: recursively sorted keys, no spaces. "
        "Run one call; use one repair only on gate request; no search or delegation. "
        "Final: exact canonical plus [math-tool:v1:%s:<digest>]."
        % (
            math_state.CONTINUATION_PREFIX,
            obligation["id"],
            _command_form(authorization, obligation["id"]),
            obligation["id"],
        )
    )
    if len(text.encode("utf-8")) > MAX_PROMPT_CONTEXT_BYTES:
        raise GateError("context_limit", "math-tool prompt context exceeds its token-safe byte limit")
    return text


def _load_current(directory):
    return (
        math_state.read_state(directory, "authorization"),
        math_state.read_state(directory, "obligation"),
        math_state.read_state(directory, "receipt"),
    )


def on_session_start(host, payload):
    directory = math_state.state_dir(host, payload["session_id"])
    math_state.cleanup()
    with math_state.state_lock(directory):
        try:
            record = _integrity(host, payload["session_id"], run_probe=True)
            record["status"] = "ready"
        except GateError as error:
            record = {
                "host": host,
                "session": math_state.session_key(payload["session_id"]),
                "status": "blocked",
                "failure": {"code": error.code, "message": error.message},
            }
        math_state.authorize(directory, record)
    return None


def on_prompt(host, payload):
    directory = math_state.state_dir(host, payload["session_id"])
    with math_state.state_lock(directory):
        authorization = math_state.read_state(directory, "authorization")
        obligation = math_state.read_state(directory, "obligation")
        task_class = math_state.classify_prompt(payload["prompt"], active=obligation)
        if task_class is None:
            return None
        if not _authorization_matches(authorization, host, payload["session_id"]):
            failure = (authorization or {}).get("failure", {})
            detail = failure.get("message", "pinned runtime or installed skill is not authorized")
            return _deny("UserPromptSubmit", "math-tool environment blocked: %s" % detail)
        turn = _turn_id(host, payload)
        continuation = (
            obligation
            and obligation.get("status") == "active"
            and (math_state.CONTINUATION_PREFIX + obligation.get("id", "")) in payload["prompt"]
        )
        if continuation:
            obligation = dict(obligation)
            obligation["turn"] = turn
            math_state.atomic_write(os.path.join(directory, "obligation.json"), obligation)
        else:
            if obligation and obligation.get("status") == "active" and not obligation.get("terminal_recorded"):
                math_state.mark_terminal(directory, obligation, "blocked", failure="superseded_turn")
            obligation = math_state.create_obligation(
                directory,
                authorization,
                payload["prompt"],
                task_class,
                turn,
                route=payload.get("model"),
                reasoning=payload.get("reasoning_effort"),
            )
        return _hook_context("UserPromptSubmit", _prompt_context(authorization, obligation))


def _active_for_turn(host, payload, obligation):
    if not obligation or obligation.get("status") != "active":
        return False
    return host != "codex" or obligation.get("turn") == payload.get("turn_id")


def _shell_tool(host, tool_name):
    return tool_name == "Bash" or (host == "claude" and tool_name == "PowerShell")


def _command(payload):
    command = payload.get("tool_input", {}).get("command")
    return command if isinstance(command, str) else ""


def _addresses_math_tool(command, authorization):
    normalized = command.replace("\\", "/")
    exact_path = authorization.get("tool_path", "").replace("\\", "/")
    return exact_path in normalized or "math_tool.py" in normalized


def _register_call_failure(directory, obligation, code, count_call=True):
    value = dict(obligation)
    if count_call:
        value["tool_calls"] = min(2, value.get("tool_calls", 0) + 1)
    value["retries"] = max(0, value["tool_calls"] - 1)
    value["repair_allowed"] = value["tool_calls"] < 2
    value["last_failure"] = code
    value.pop("pending", None)
    math_state.atomic_write(os.path.join(directory, "obligation.json"), value)
    return value


def on_pre_tool(host, payload):
    directory = math_state.state_dir(host, payload["session_id"])
    with math_state.state_lock(directory):
        authorization = math_state.read_state(directory, "authorization")
        obligation = math_state.read_state(directory, "obligation")
        if not _active_for_turn(host, payload, obligation):
            return None
        if not _shell_tool(host, payload["tool_name"]):
            return None
        command = _command(payload)
        if not _addresses_math_tool(command, authorization or {}):
            return None
        if not _authorization_matches(authorization, host, payload["session_id"]):
            return _deny("PreToolUse", "math-tool authorization, runtime, or installed bytes changed")
        try:
            arguments = _split_command(command)
            if len(arguments) != 5 or arguments[3] != "--request":
                raise GateError("invalid_command", "math-tool command must contain only the pinned interpreter, tool, and --request")
            request = math_tool.validate_request(arguments[4])
            if request["obligation"] != obligation["id"]:
                raise GateError("wrong_obligation", "math-tool request obligation does not match the current turn")
            expected = canonical_command(authorization, request)
            if command != expected:
                raise GateError("altered_command", "math-tool command is not the exact canonical command")
            calls = obligation.get("tool_calls", 0)
            if calls >= 2 or (calls == 1 and not obligation.get("repair_allowed")):
                raise GateError("call_limit", "math-tool call budget is exhausted")
            pending = obligation.get("pending")
            if pending:
                if pending.get("tool_use_id") == payload["tool_use_id"] and pending.get("command") == command:
                    return None
                raise GateError("pending_call", "another math-tool call is already pending")
            value = dict(obligation)
            value["tool_calls"] = calls + 1
            value["retries"] = max(0, value["tool_calls"] - 1)
            value["repair_allowed"] = False
            value["pending"] = {
                "tool_use_id": payload["tool_use_id"],
                "command": command,
                "command_digest": hashlib.sha256(command.encode("utf-8")).hexdigest(),
                "request_digest": math_state.digest_json(request),
                "request": request,
                "started": time.time(),
            }
            math_state.atomic_write(os.path.join(directory, "obligation.json"), value)
            return None
        except (GateError, math_tool.MathToolError, ValueError) as error:
            code = getattr(error, "code", "invalid_command")
            detail = getattr(error, "message", str(error))
            value = _register_call_failure(directory, obligation, code)
            repair = " Read math-tool protocol and issue the one corrected canonical request." if value.get("repair_allowed") else " Call budget exhausted."
            return _deny("PreToolUse", "%s.%s" % (detail, repair))


def _response_text(payload):
    response = payload.get("tool_response")
    if isinstance(response, str):
        return response, None
    if not isinstance(response, dict):
        return "", None
    exit_code = response.get("exit_code", response.get("exitCode"))
    if not isinstance(exit_code, int):
        metadata = response.get("metadata")
        exit_code = metadata.get("exit_code") if isinstance(metadata, dict) and isinstance(metadata.get("exit_code"), int) else None
    for key in ("output", "stdout", "content"):
        if isinstance(response.get(key), str):
            return response[key], exit_code
    return math_state.canonical_json(response), exit_code


def _result_from_response(payload):
    text, exit_code = _response_text(payload)
    objects = []
    for line in text.splitlines():
        candidate = line.strip()
        if not candidate.startswith("{") or not candidate.endswith("}"):
            continue
        try:
            value = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(value, dict) and value.get("v") == 1 and value.get("status") in ("accepted", "blocked"):
            objects.append((candidate, value))
    if len(objects) != 1:
        raise GateError("invalid_result", "math-tool output must contain one protocol result")
    raw, result = objects[0]
    if len(raw.encode("utf-8")) > math_tool.LIMITS["result_bytes"] or len(raw.encode("utf-8")) > math_tool.LIMITS["result_tokens"]:
        raise GateError("result_limit", "math-tool output exceeds its token or byte limit")
    if exit_code not in (None, 0):
        raise GateError("tool_failed", "math-tool process returned a nonzero exit status")
    allowed = {"v", "status", "obligation", "canonical", "exact", "approximate", "digest", "failure"}
    if not set(result).issubset(allowed):
        raise GateError("invalid_result", "math-tool result has unknown fields")
    return result


def _repair_command(obligation):
    pending = obligation.get("pending", {})
    command = pending.get("command") if isinstance(pending, dict) else None
    if isinstance(command, str):
        return command
    return "the corrected canonical command from $math-tool"


def on_post_tool(host, event, payload):
    directory = math_state.state_dir(host, payload["session_id"])
    with math_state.state_lock(directory):
        authorization = math_state.read_state(directory, "authorization")
        obligation = math_state.read_state(directory, "obligation")
        if not _active_for_turn(host, payload, obligation):
            return None
        if not _shell_tool(host, payload["tool_name"]):
            return None
        command = _command(payload)
        if not _addresses_math_tool(command, authorization or {}):
            return None
        pending = obligation.get("pending")
        try:
            if not _authorization_matches(authorization, host, payload["session_id"]):
                raise GateError("authorization_changed", "math-tool authorization, runtime, or installed bytes changed")
            if not isinstance(pending, dict) or pending.get("tool_use_id") != payload["tool_use_id"] or pending.get("command") != command:
                raise GateError("wrong_tool_use", "math-tool result does not match the authorized tool call")
            if event == "PostToolUseFailure":
                raise GateError("tool_failed", "math-tool execution failed")
            result = _result_from_response(payload)
            if result.get("status") != "accepted":
                failure = result.get("failure", {})
                raise GateError(failure.get("code", "tool_blocked"), failure.get("message", "math-tool returned blocked"))
            if result.get("obligation") != obligation["id"] or not isinstance(result.get("canonical"), str) or result.get("exact") != result.get("canonical"):
                raise GateError("invalid_result", "math-tool result identity or canonical value does not match")
            digest = result.get("digest")
            base = dict(result)
            base.pop("digest", None)
            if not isinstance(digest, str) or digest != math_state.digest_json(base):
                raise GateError("forged_result", "math-tool result digest does not match")
            receipt = math_state.seal_receipt(
                directory,
                obligation,
                pending["request_digest"],
                result,
                payload["tool_use_id"],
                authorization,
            )
            marker = "[math-tool:v1:%s:%s]" % (obligation["id"], receipt["result_digest"])
            context = "math-tool accepted. Use exact canonical %s and exact marker %s in the visible final." % (
                json.dumps(receipt["canonical"], ensure_ascii=False),
                marker,
            )
            return _hook_context(event, context[:MAX_REPAIR_CONTEXT_BYTES])
        except GateError as error:
            value = _register_call_failure(directory, obligation, error.code, count_call=False)
            if value.get("repair_allowed"):
                context = "%s%s Retry once with: %s" % (
                    math_state.CONTINUATION_PREFIX,
                    value["id"],
                    _repair_command(obligation),
                )
            else:
                context = "%s%s Call budget exhausted; report status: blocked and failure %s." % (
                    math_state.CONTINUATION_PREFIX,
                    value["id"],
                    error.code,
                )
            return _post_feedback(event, error.message, context)


def _valid_receipt(authorization, obligation, receipt):
    if not authorization or not obligation or not receipt:
        return False
    return (
        receipt.get("obligation") == obligation.get("id")
        and receipt.get("tool_digest") == authorization.get("tool_digest")
        and receipt.get("protocol_digest") == authorization.get("protocol_digest")
        and receipt.get("runtime_lock_digest") == authorization.get("runtime_lock_digest")
        and receipt.get("sympy") == authorization.get("sympy")
        and isinstance(receipt.get("canonical"), str)
        and isinstance(receipt.get("result_digest"), str)
    )


def _final_matches(receipt, message):
    if not isinstance(message, str):
        return False
    marker = "[math-tool:v1:%s:%s]" % (receipt["obligation"], receipt["result_digest"])
    observed = _MARKER_RE.findall(message)
    return message.count(marker) == 1 and observed == [(receipt["obligation"], receipt["result_digest"])] and receipt["canonical"] in message


def on_stop(host, payload):
    directory = math_state.state_dir(host, payload["session_id"])
    with math_state.state_lock(directory):
        authorization, obligation, receipt = _load_current(directory)
        if not _active_for_turn(host, payload, obligation):
            return None
        if _valid_receipt(authorization, obligation, receipt) and _final_matches(receipt, payload.get("last_assistant_message")):
            math_state.mark_terminal(directory, obligation, "accepted")
            return None
        if not payload["stop_hook_active"] and obligation.get("continuations", 0) < 1:
            value = dict(obligation)
            value["continuations"] = 1
            math_state.atomic_write(os.path.join(directory, "obligation.json"), value)
            if _valid_receipt(authorization, obligation, receipt):
                marker = "[math-tool:v1:%s:%s]" % (receipt["obligation"], receipt["result_digest"])
                reason = "%s%s Use exact canonical %s and exact marker %s in the visible final." % (
                    math_state.CONTINUATION_PREFIX,
                    obligation["id"],
                    json.dumps(receipt["canonical"], ensure_ascii=False),
                    marker,
                )
            else:
                reason = "%s%s Complete the pinned call once, or its one allowed repair, then include its canonical result and receipt marker." % (
                    math_state.CONTINUATION_PREFIX,
                    obligation["id"],
                )
            return {"decision": "block", "reason": reason[:MAX_REPAIR_CONTEXT_BYTES]}
        failure = obligation.get("last_failure", "missing_or_inconsistent_receipt")
        math_state.mark_terminal(directory, obligation, "blocked", failure=failure)
        message = "math-tool blocked: %s; obligation %s" % (failure, obligation["id"])
        return {"continue": False, "stopReason": message, "systemMessage": message}


def on_pre_compact(host, payload):
    directory = math_state.state_dir(host, payload["session_id"])
    with math_state.state_lock(directory):
        authorization = math_state.read_state(directory, "authorization")
        obligation = math_state.read_state(directory, "obligation")
        if obligation and obligation.get("status") == "active" and not _authorization_matches(authorization, host, payload["session_id"]):
            return {"continue": False, "stopReason": "active math-tool obligation lost its authorization"}
    return None


def on_session_end(host, payload):
    try:
        math_state.cleanup()
    except (OSError, ValueError):
        pass
    return None


def _active_obligation(host, payload):
    try:
        directory = math_state.state_dir(host, payload.get("session_id", ""))
        with math_state.state_lock(directory):
            return math_state.read_state(directory, "obligation")
    except (OSError, ValueError):
        return None


def _crash_output(host, event, payload, error):
    obligation = _active_obligation(host, payload)
    if not obligation or obligation.get("status") != "active":
        return None
    reason = "math-tool gate failed closed for active obligation: %s" % error.code
    if event == "PreToolUse":
        return _deny(event, reason)
    if event in ("PostToolUse", "PostToolUseFailure"):
        return _post_feedback(event, reason, reason)
    if event == "Stop":
        return {"continue": False, "stopReason": reason, "systemMessage": reason}
    if event in ("UserPromptSubmit", "PreCompact"):
        return {"decision": "block", "reason": reason} if event == "UserPromptSubmit" else {"continue": False, "stopReason": reason}
    return None


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", choices=tuple(HOST_EVENTS), required=True)
    parser.add_argument("--event", required=True)
    args = parser.parse_args(argv)
    if args.event not in HOST_EVENTS[args.host]:
        parser.error("event is not supported by this host")
    payload = {}
    try:
        payload = _payload(args.event)
        _validate_native_fields(args.host, args.event, payload)
        handlers = {
            "SessionStart": lambda: on_session_start(args.host, payload),
            "UserPromptSubmit": lambda: on_prompt(args.host, payload),
            "PreToolUse": lambda: on_pre_tool(args.host, payload),
            "PostToolUse": lambda: on_post_tool(args.host, args.event, payload),
            "PostToolUseFailure": lambda: on_post_tool(args.host, args.event, payload),
            "Stop": lambda: on_stop(args.host, payload),
            "PreCompact": lambda: on_pre_compact(args.host, payload),
            "SessionEnd": lambda: on_session_end(args.host, payload),
        }
        _emit(handlers[args.event]())
        return 0
    except GateError as error:
        _emit(_crash_output(args.host, args.event, payload, error))
        return 0
    except BaseException as error:
        gate_error = GateError("internal_error", type(error).__name__)
        _emit(_crash_output(args.host, args.event, payload, gate_error))
        return 0


if __name__ == "__main__":
    sys.exit(main())
