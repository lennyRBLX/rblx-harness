#!/usr/bin/env python3
"""Host adapter runner for documented OpenAI and Claude hook payloads."""

import argparse
import json
import os
import subprocess
import sys


EVENT_SCRIPTS = {
    "PreToolUse": "write_gate.py",
    "Stop": "done_gate.py",
    "SessionStart": "session_gate.py",
    "PreCompact": "compact_gate.py",
    "SubagentStart": "agent_start.py",
    "SubagentStop": "record_check.py",
    "UserPromptSubmit": "turn_stamp.py",
}


def main(host, argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", choices=sorted(EVENT_SCRIPTS), required=True)
    parser.add_argument("--hook-scope", choices=("project", "user"), required=True)
    args = parser.parse_args(argv)
    try:
        payload = json.load(sys.stdin)
    except (TypeError, ValueError):
        sys.stderr.write("hook-adapter: malformed JSON payload\n")
        return 2
    if not isinstance(payload, dict):
        sys.stderr.write("hook-adapter: payload is not an object\n")
        return 2
    reported_event = payload.get("hook_event_name")
    if reported_event is not None and reported_event != args.event:
        sys.stderr.write("hook-adapter: event does not match configured command\n")
        return 2
    payload["hook_event_name"] = args.event
    payload["_harness_host"] = host
    gate = os.path.join(os.path.dirname(os.path.abspath(__file__)), EVENT_SCRIPTS[args.event])
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-B", gate, "--host", host, "--hook-scope", args.hook_scope],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=environment,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode

