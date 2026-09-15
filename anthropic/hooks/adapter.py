#!/usr/bin/env python3
"""Claude Code compatibility for retired rblx-harness hook handlers.

Earlier releases wrote python3 handlers into .claude/settings.json that ran
claude/hooks/adapter.py or shared/gates/harness_gate.py. Those scripts are gone;
python3 exits 2 for a missing script, which Claude Code treats as a blocking
error. Setup removes exactly those handlers with retired_handler(). Running this
file exits 0 without output, which Claude Code treats as success. Claude Code's
native permissions and user-owned hooks continue to apply.
"""

import sys


RETIRED_SCRIPTS = (
    ("${CLAUDE_PROJECT_DIR}/.roblox-harness/claude/hooks/adapter.py", ["--hook-scope", "project"]),
    ("${CLAUDE_PROJECT_DIR}/shared/gates/harness_gate.py", []),
)


def retired_handler(handler, event):
    """Match installed handler fields, not arbitrary commands mentioning a path."""
    if not isinstance(handler, dict) or handler.get("type") != "command" or handler.get("command") != "python3":
        return False
    args = handler.get("args")
    return any(
        args == ["-B", script, "--host", "claude", "--event", event] + suffix
        for script, suffix in RETIRED_SCRIPTS
    )


if __name__ == "__main__":
    sys.exit(0)
