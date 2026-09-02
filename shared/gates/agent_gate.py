#!/usr/bin/env python3
"""Enforce the four agent roles and their compact return contract."""

import argparse
import json
import os
import sys


ROLES = ("researcher", "optimizer", "reviewer", "debugger")
VERDICTS = {
    "researcher": {"FOUND", "MISS"},
    "optimizer": {"ISSUES", "CLEAR", "WAITING"},
    "reviewer": {"ISSUES", "CLEAN"},
    "debugger": {"TEST", "CAUSE", "FIX", "WAITING"},
}
MAX_BYTES = 8192
MAX_LINES = 96


def role_from(payload):
    values = [
        payload.get("agent_type"),
        payload.get("agent_name"),
        payload.get("subagent_type"),
        payload.get("name"),
    ]
    agent = payload.get("agent")
    if isinstance(agent, dict):
        values.extend((agent.get("name"), agent.get("type")))
    for value in values:
        key = str(value or "").strip().casefold()
        if key in ROLES:
            return key
    return ""


def block(reason):
    sys.stderr.write("agent-gate: BLOCKED %s\n" % reason)
    return 2


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", choices=("SubagentStart", "SubagentStop"), required=True)
    args = parser.parse_args(argv)
    try:
        payload = json.load(sys.stdin)
    except (TypeError, ValueError):
        return block("malformed hook payload")
    if not isinstance(payload, dict):
        return block("hook payload is not an object")
    role = role_from(payload)
    if not role:
        return block("agent role must be researcher, optimizer, reviewer, or debugger")
    depth = payload.get("agent_depth", payload.get("depth", 1))
    try:
        nested = int(depth) > 1
    except (TypeError, ValueError):
        nested = False
    if nested:
        return block("agents cannot spawn agents [AGENT1]")
    if args.event == "SubagentStart":
        rules = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "CORE.md")
        context = (
            "HARNESS|role=%s|read=%s|agents-do-not-spawn-agents|"
            "use data_write/type_write for data or public types|return compact evidence"
        ) % (role, rules)
        sys.stdout.write(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SubagentStart",
                "additionalContext": context,
            }
        }, separators=(",", ":")) + "\n")
        return 0
    message = payload.get("last_assistant_message", payload.get("assistant_message", ""))
    if not isinstance(message, str) or not message.strip():
        return block("agent returned no text")
    if len(message.encode("utf-8")) > MAX_BYTES or len(message.splitlines()) > MAX_LINES:
        return block("agent return exceeds the token-compression limit [TOK1]")
    first = message.strip().splitlines()[0]
    prefix = role + ": "
    if not first.startswith(prefix) or first[len(prefix):].strip() not in VERDICTS[role]:
        return block("%s returned an invalid verdict" % role)
    return 0


if __name__ == "__main__":
    sys.exit(main())
