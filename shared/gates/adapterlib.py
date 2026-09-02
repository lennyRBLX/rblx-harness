"""Run the three supported Codex project gates."""

import argparse
import json
import os
import subprocess
import sys


EVENT_SCRIPTS = {
    "PreToolUse": "tool_gate.py",
    "SubagentStart": "agent_gate.py",
    "SubagentStop": "agent_gate.py",
}


def main(host, argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", choices=sorted(EVENT_SCRIPTS), required=True)
    parser.add_argument("--hook-scope", choices=("project",), default="project")
    args = parser.parse_args(argv)
    if host != "codex":
        sys.stderr.write("hook-adapter: only Codex is supported\n")
        return 2
    try:
        payload = json.load(sys.stdin)
    except (TypeError, ValueError):
        sys.stderr.write("hook-adapter: malformed JSON payload\n")
        return 2
    if not isinstance(payload, dict):
        sys.stderr.write("hook-adapter: payload is not an object\n")
        return 2
    reported = payload.get("hook_event_name")
    if reported is not None and reported != args.event:
        sys.stderr.write("hook-adapter: event does not match configured command\n")
        return 2
    payload["hook_event_name"] = args.event
    gate = os.path.join(os.path.dirname(os.path.abspath(__file__)), EVENT_SCRIPTS[args.event])
    result = subprocess.run(
        [sys.executable, "-B", gate, "--event", args.event],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode

