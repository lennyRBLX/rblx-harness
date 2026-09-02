#!/usr/bin/env python3
"""Enforce agent tool boundaries without authorizing or restarting sessions."""

import argparse
import json
import re
import sys


ROLES = ("researcher", "optimizer", "reviewer", "debugger")
READ_ONLY = ("researcher", "optimizer", "reviewer")
SPAWN_WORDS = ("spawn_agent", "create_agent", "delegate")
MUTATION_WORDS = ("apply_patch", "write", "edit", "delete", "move")
DATA_PATH = re.compile(
    r"(?:ReplicatedStorage/(?:Data|Types)/|/(?:Default|Development|Typed)\.luau\b)",
    re.IGNORECASE,
)
FORBIDDEN_SOURCE = re.compile(r"\b(?:loadstring|getfenv|setfenv)\s*\(")
SHELL_MUTATION = re.compile(
    r"(?:^|[;&|]\s*|\s)(?:rm|mv|cp|install|touch|truncate|tee)\s|"
    r"\bsed\s+-[^\n]*i\b|\bperl\s+-[^\n]*i\b|(?:^|[^<])>{1,2}(?:[^>]|$)"
)
DATA_TOOLS = ("tools/data_write/data_write.py", "tools/type_write/type_write.py")
READ_DATA_TOOLS = (
    "tools/data_check/data_check.luau",
    "tools/data_shape_diff/data_shape_diff.luau",
    "tools/type_lookup/type_lookup.py",
)
READ_SHELL = re.compile(
    r"^\s*(?:(?:[A-Z_][A-Z0-9_]*)=[^\s]+\s+)*(?:"
    r"cat\b|head\b|tail\b|wc\b|stat\b|ls\b|rg\b|grep\b|sed\s+-n\b|git\s+(?:diff|show|status)\b)"
)


def role_from(payload):
    for key in ("agent_type", "agent_name", "subagent_type"):
        value = str(payload.get(key) or "").strip().casefold()
        if value in ROLES:
            return value
    return ""


def text_input(tool_input):
    if isinstance(tool_input, str):
        return tool_input
    if isinstance(tool_input, dict):
        return "\n".join(str(value) for value in tool_input.values() if isinstance(value, (str, int, float)))
    return ""


def requested_role(tool_input):
    if not isinstance(tool_input, dict):
        return ""
    for key in ("agent_type", "name", "task_name", "role"):
        value = str(tool_input.get(key) or "").strip().casefold()
        if value in ROLES:
            return value
    prompt = str(tool_input.get("prompt") or tool_input.get("message") or "").casefold()
    return next((role for role in ROLES if re.search(r"\b" + role + r"\b", prompt)), "")


def block(reason):
    sys.stderr.write("tool-gate: BLOCKED %s\n" % reason)
    return 2


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", choices=("PreToolUse",), required=True)
    parser.parse_args(argv)
    try:
        payload = json.load(sys.stdin)
    except (TypeError, ValueError):
        return block("malformed hook payload")
    if not isinstance(payload, dict):
        return block("hook payload is not an object")
    tool = str(payload.get("tool_name") or "").casefold().replace("-", "_")
    tool_input = payload.get("tool_input", {})
    role = role_from(payload)
    if tool == "agent" or any(word in tool for word in SPAWN_WORDS):
        if role:
            return block("agents cannot spawn agents [AGENT1]")
        if not requested_role(tool_input):
            return block("dispatch one of: researcher, optimizer, reviewer, debugger [AGENT1]")
        return 0
    if not role:
        return 0
    raw = text_input(tool_input)
    normalized = raw.replace("\\", "/")
    mutation = any(word in tool for word in MUTATION_WORDS)
    if role in READ_ONLY and mutation:
        return block("%s is read-only [AGENT1]" % role)
    if mutation and "rblx-harness/" in normalized:
        return block("agents cannot edit the harness dependency")
    data_tool = any(path in normalized for path in DATA_TOOLS)
    data_reader = any(path in normalized for path in READ_DATA_TOOLS) or bool(READ_SHELL.search(raw))
    shell_data_mutation = DATA_PATH.search(normalized) and SHELL_MUTATION.search(raw)
    unknown_shell_data_use = DATA_PATH.search(normalized) and "exec" in tool and not data_reader
    if DATA_PATH.search(normalized) and not data_tool and (mutation or shell_data_mutation or unknown_shell_data_use):
        return block("data and public types require data_write or type_write [TOOL1]")
    if mutation and FORBIDDEN_SOURCE.search(raw):
        return block("forbidden dynamic environment API [CODE1]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
