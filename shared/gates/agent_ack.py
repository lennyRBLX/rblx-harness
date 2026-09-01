#!/usr/bin/env python3
"""Ack one joined agent return: agent_ack.py <agent_id>."""

import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gatelib  # noqa: E402

INCOMPLETE_VERDICTS = frozenset(("MISS", "WAITING", "ENV"))
VERDICT_RE = re.compile(r"^(reviewer|debugger|optimizer|researcher|maintainer): ([A-Z]+)$")


def mailbox_verdict(entry):
    result = entry.get("result")
    first_line = result.split("\n", 1)[0] if isinstance(result, str) else ""
    match = VERDICT_RE.fullmatch(first_line)
    if not match or match.group(1) != entry.get("agent_type"):
        return None
    return match.group(2)


def main(argv):
    if len(argv) != 1:
        sys.stderr.write("usage: agent_ack.py <agent_id>\n")
        return 2
    cwd = os.getcwd()
    agent_id = argv[0]
    matches = []
    for path in glob.glob(os.path.join(cwd, "gates", ".agents", "*", "*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                entry = json.load(f)
        except (OSError, ValueError):
            continue
        session_id = entry.get("session_id")
        if not isinstance(session_id, str):
            continue
        live = next(
            (
                candidate
                for candidate in gatelib.agent_mailbox_entries(cwd, session_id)
                if candidate.get("agent_id") == agent_id and candidate.get("state") == "done"
            ),
            None,
        )
        if live is not None and live not in matches:
            matches.append(live)
    if len(matches) != 1:
        sys.stderr.write("agent-ack: expected 1 done return for %s, found %d\n" % (agent_id, len(matches)))
        return 2
    entry = matches[0]
    if entry.get("overlap"):
        sys.stderr.write("agent-ack: concurrent writer return for %s cannot be acknowledged\n" % agent_id)
        return 2
    verdict = mailbox_verdict(entry)
    if verdict is None:
        sys.stderr.write("agent-ack: unverified return for %s cannot be acknowledged\n" % agent_id)
        return 2
    if verdict in INCOMPLETE_VERDICTS:
        gatelib.agent_mailbox_write(cwd, entry["session_id"], agent_id, state="acked")
        sys.stdout.write("agent-ack: RETIRED %s %s\n" % (agent_id, verdict))
        return 0
    gatelib.agent_mailbox_write(cwd, entry["session_id"], agent_id, state="acked")
    sys.stdout.write("agent-ack: ACKED %s\n" % agent_id)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as e:
        sys.stderr.write("agent-ack: %s\n" % e)
        sys.exit(2)
