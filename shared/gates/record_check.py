#!/usr/bin/env python3
"""record_check — the SubagentStop schema gate [R REV2, REV10]. Runs on every
agent return; the only gate whose subject is an agent rather than a file.

The agent_payload adapter uses only documented SubagentStop fields. The whole
available return must parse: a verdict line, records, and sample| bodies; nothing else
— all ruled agents emit only those shapes, so prose has nowhere to live.

Malformed hook payloads, missing authorization, and gate crashes fail closed.
Non-reviewer output receives one schema-repair attempt, then becomes a typed
ENV mailbox result without a durable project precondition. Reviewer schema,
identity, verdict, live rule ids, target, and receipt failures remain hard.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gatelib  # noqa: E402
import agent_payload  # noqa: E402
import agent_dispatch  # noqa: E402
import token_shrink  # noqa: E402

AGENTS = ("reviewer", "debugger", "optimizer", "researcher", "maintainer")

# leading token -> field arity (token included). Typed records carry no id —
# a fix or an API fact violates no rule.
TOKEN_ARITY = {
    "class": 4,
    "api": 6,
    "enum": 4,
    "doc": 4,
    "house": 3,
    "sample": 3,
    "miss": 3,
    "fix": 4,
    "diag": 4,
    "opt": 4,
    "clear": 3,
    "wait": 3,
    "ENV": 3,
    "rule": 3,
    "repair": 4,
}

VERDICTS = {
    "reviewer": {"CLEAN", "NOTED", "BLOCKED"},
    "debugger": {"FIX", "DIAGNOSING", "WAITING", "ENV"},
    "optimizer": {"CLEAR", "MEASURED", "WAITING", "MISS", "ENV"},
    "researcher": {"FOUND", "MISS", "ENV"},
    "maintainer": {"READY", "ENV"},
}
AGENT_RECORDS = {
    "reviewer": {"rule", "ENV"},
    "debugger": {"fix", "diag", "wait", "ENV"},
    "optimizer": {"opt", "clear", "miss", "wait", "ENV"},
    "researcher": {"class", "api", "enum", "doc", "house", "sample", "miss", "rule", "ENV"},
    "maintainer": {"repair", "ENV"},
}
VERDICT_RE = re.compile(r"^(reviewer|debugger|optimizer|researcher|maintainer): ([A-Z]+)$")
PATH_HEADER_RE = re.compile(r"^\S.*:$")
FINDING_RE = re.compile(r"^-?\d+\|")
MAX_RETURN_BYTES = 8192
MAX_RETURN_LINES = 96
MAX_FIELD_BYTES = 1024
MAX_RECORDS = {
    "reviewer": 24,
    "researcher": 24,
    "optimizer": 16,
    "debugger": 12,
    "maintainer": 2,
}


def complete_mailbox(cwd, session_id, agent_id, agent, message):
    if not session_id or not agent_id:
        return
    prior = next(
        (entry for entry in gatelib.agent_mailbox_entries(cwd, session_id) if entry.get("agent_id") == str(agent_id)),
        {},
    )
    gatelib.agent_mailbox_write(
        cwd,
        session_id,
        agent_id,
        agent_type=agent,
        state="done",
        overlap=bool(prior.get("overlap")),
        result=message,
        last_assistant_message=message,
    )


def mailbox_entry(cwd, session_id, agent_id):
    return next(
        (
            entry
            for entry in gatelib.agent_mailbox_entries(cwd, session_id)
            if entry.get("agent_id") == str(agent_id)
        ),
        {},
    )


def parse_return(agent, text):
    """Returns (findings, rule_records). Findings are the shape violations."""
    problems = []
    rules = []
    byte_count = len(text.encode("utf-8"))
    if byte_count > MAX_RETURN_BYTES:
        return [
            (
                1,
                "return exceeds %d UTF-8 bytes" % MAX_RETURN_BYTES,
                "rank evidence and return only records needed for the verdict",
            )
        ], rules
    lines = text.split("\n")
    if len(lines) > MAX_RETURN_LINES:
        return [
            (
                1,
                "return exceeds %d lines" % MAX_RETURN_LINES,
                "drop logs, excerpts, and redundant records",
            )
        ], rules
    verdict_match = VERDICT_RE.fullmatch(lines[0]) if lines else None
    if not verdict_match:
        problems.append((1, "no verdict line", "first line is '<agent>: <VERDICT>'"))
        return problems, rules
    verdict_agent, verdict = verdict_match.groups()
    if verdict_agent != agent:
        problems.append((1, "verdict agent does not match dispatch", "first line names the dispatched agent"))
        return problems, rules
    if verdict not in VERDICTS[agent]:
        problems.append((1, "invalid %s verdict" % agent, "%s verdict is one of %s" % (agent, ", ".join(sorted(VERDICTS[agent])))))
        return problems, rules

    in_sample_body = False
    seen_tokens = []
    reviewer_records = 0
    reviewer_blocking_finding = False
    reviewer_env = False
    record_count = 0
    for n, line in enumerate(lines[1:], start=2):
        if line.strip() == "":
            in_sample_body = False
            continue
        head = line.split("|", 1)[0]
        looks_record = "|" in line and (head in TOKEN_ARITY or FINDING_RE.match(line))
        if in_sample_body and not looks_record:
            continue  # lines after a sample| header are body until the next line that parses
        in_sample_body = False
        if PATH_HEADER_RE.match(line) and "|" not in line:
            if agent == "researcher":
                problems.append((n, "researcher path header", "research records are API facts, not file groups"))
            continue  # OUT2 path header
        if "|" not in line:
            problems.append((n, "prose line", "records only - prose has nowhere to live"))
            continue

        if line.endswith("|"):
            problems.append((n, "record ends with '|'", "trailing field dropped by split - void fills"))
            continue
        # paren-aware split: a | inside parentheses is a union type in a sig,
        # not a delimiter
        fields = []
        depth = 0
        cur = ""
        for ch in line:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            if ch == "|" and depth == 0:
                fields.append(cur)
                cur = ""
            else:
                cur += ch
        fields.append(cur)

        if any(len(field.encode("utf-8")) > MAX_FIELD_BYTES for field in fields):
            problems.append((n, "field exceeds %d UTF-8 bytes" % MAX_FIELD_BYTES, "return a compact fact or reference"))
            continue
        if any(f == "" for f in fields):
            problems.append((n, "empty field", "'void' fills, never ''"))
            continue
        if any(f != f.strip() and f.strip() != "" for f in fields):
            problems.append((n, "whitespace padding around '|'", "OUT1: no pad"))
            continue

        token = fields[0]
        if token in TOKEN_ARITY:
            record_count += 1
            if token not in AGENT_RECORDS[agent]:
                problems.append((n, "%s record is not valid for %s" % (token, agent), "use only the agent's declared record types"))
                continue
            if len(fields) != TOKEN_ARITY[token]:
                problems.append(
                    (n, "%s %d fields, %d expected" % (token, len(fields), TOKEN_ARITY[token]), "%s arity is fixed" % token)
                )
                continue
            if token == "repair" and fields[1] not in gatelib.RECOVERY_KINDS:
                problems.append(
                    (
                        n,
                        "unknown recovery kind '%s'" % fields[1],
                        "repair kind is one of %s" % ", ".join(sorted(gatelib.RECOVERY_KINDS)),
                    )
                )
                continue
            if token == "sample":
                in_sample_body = True
            if token == "rule":
                rules.append(line)
            if agent == "reviewer":
                reviewer_records += 1
                reviewer_env = reviewer_env or token == "ENV"
            seen_tokens.append(token)
            continue

        if FINDING_RE.match(line):
            record_count += 1
            if agent != "reviewer":
                problems.append((n, "finding record is not valid for %s" % agent, "use the agent's typed records"))
                continue
            if len(fields) != 5:
                problems.append((n, "finding %d fields, 5 expected" % len(fields), "findings are line, col, id, subject, remedy"))
                continue
            line_f, col_f, id_f = fields[0], fields[1], fields[2]
            if not re.match(r"^-?\d+$", line_f) or not re.match(r"^-?\d+$", col_f):
                problems.append((n, "finding line or col not an integer", "line and col are integers"))
                continue
            if "!" in id_f and not id_f.endswith("!"):
                problems.append((n, "'!' inside the id", "'!' suffixes the id for BLOCK"))
                continue
            bare = id_f.rstrip("!")
            if "!" in fields[3] + fields[4] and False:
                pass
            if bare in gatelib.REMOVED_IDS:
                problems.append((n, "%s is removed" % bare, "cite a live id or drop the finding"))
                continue
            if bare not in gatelib.ACCEPTED_IDS:
                problems.append((n, "%s not a live id" % bare, "cite a live id or drop the finding"))
                continue
            reviewer_records += 1
            reviewer_blocking_finding = reviewer_blocking_finding or id_f.endswith("!")
            continue

        problems.append((n, "leading token '%s' not valid for %s" % (token, agent), "use the agent's declared record types"))

    record_limit = MAX_RECORDS[agent]
    if record_count > record_limit:
        problems.append(
            (
                1,
                "%s return exceeds %d records" % (agent, record_limit),
                "rank evidence and return only records needed for the verdict",
            )
        )

    required_record = {
        ("debugger", "FIX"): "fix",
        ("debugger", "DIAGNOSING"): "diag",
        ("debugger", "WAITING"): "wait",
        ("debugger", "ENV"): "ENV",
        ("optimizer", "CLEAR"): "clear",
        ("optimizer", "MEASURED"): "opt",
        ("optimizer", "WAITING"): "wait",
        ("optimizer", "MISS"): "miss",
        ("optimizer", "ENV"): "ENV",
        ("researcher", "MISS"): "miss",
        ("researcher", "ENV"): "ENV",
        ("maintainer", "READY"): "repair",
        ("maintainer", "ENV"): "ENV",
    }.get((agent, verdict))
    if required_record and required_record not in seen_tokens:
        problems.append((1, "%s verdict has no %s record" % (verdict, required_record), "the verdict's typed record is required"))
    if agent == "researcher" and verdict == "FOUND" and not seen_tokens:
        problems.append((1, "FOUND verdict has no evidence record", "return at least one researched fact"))
    if agent == "reviewer":
        if verdict == "CLEAN" and reviewer_records:
            problems.append((1, "CLEAN verdict has records", "use CLEAN only when there are no records"))
        elif verdict == "NOTED":
            if not reviewer_records:
                problems.append((1, "NOTED verdict has no record", "use CLEAN when there are no concerns"))
            if reviewer_blocking_finding:
                problems.append((1, "NOTED verdict has a blocking finding", "use BLOCKED when an id ends in '!'"))
            if reviewer_env:
                problems.append((1, "NOTED verdict has an ENV record", "use BLOCKED when environment evidence prevents review"))
        elif verdict == "BLOCKED" and not (reviewer_blocking_finding or reviewer_env):
            problems.append((1, "BLOCKED verdict has no blocking finding or ENV", "suffix a live finding id with '!' or return ENV"))
    return problems, rules


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    payload = gatelib.read_payload()
    candidate = payload.get("cwd") if isinstance(payload, dict) else os.getcwd()
    if not gatelib.is_roblox_project(candidate):
        return 0
    if payload is None:
        sys.stderr.write("record_check: BLOCKED malformed SubagentStop payload\n")
        return 2
    payload = agent_payload.normalize(payload, "stop")
    message = payload.get("last_assistant_message")
    cwd = payload.get("cwd") or os.getcwd()
    if not gatelib.is_roblox_project(cwd):
        return 0
    session_id = payload.get("session_id") or ""
    agent_id = payload.get("agent_id") or ""
    agent = gatelib.effective_agent_type(payload, cwd)
    scope = gatelib.hook_scope(argv)
    host = gatelib.hook_host(argv, payload)
    authorized, detail = gatelib.session_authorization_status(payload, cwd, scope, "SubagentStop", host)
    if not authorized:
        degraded, degraded_detail, _, _ = gatelib.session_recovery_status(
            payload,
            cwd,
            scope,
            "SubagentStop",
            host,
        )
        verdict = VERDICT_RE.fullmatch(message.split("\n", 1)[0]) if isinstance(message, str) else None
        if agent not in AGENTS and verdict:
            agent = verdict.group(1)
        if not degraded or agent != "maintainer":
            sys.stderr.write(gatelib.session_block(host, degraded_detail or detail, cwd) + "\n")
            return 2
    gatelib.cleanup_review_receipts(cwd)

    if agent not in AGENTS:
        # A default-profile task receives a ruled role only from the dispatch
        # registry consumed by SubagentStart. Its own verdict cannot grant it
        # reviewer or writer authority.
        m = VERDICT_RE.fullmatch(message.split("\n", 1)[0]) if isinstance(message, str) else None
        gatelib.fail_review_receipt(cwd, session_id, agent_id)
        gatelib.agent_mailbox_delete(cwd, session_id, agent_id)
        if m:
            sys.stderr.write(
                "record_check: BLOCKED unbound agent role\n\n"
                "0|0|REV4|agent verdict was not bound to its dispatch role|dispatch the named harness role again\n"
            )
            return 2
        return 0

    prior = mailbox_entry(cwd, session_id, agent_id)
    if agent != "reviewer" and (
        not prior
        or prior.get("agent_type") != agent
        or prior.get("state") not in ("pending", "overlap", "recovering")
    ):
        gatelib.fail_review_receipt(cwd, session_id, agent_id)
        gatelib.agent_mailbox_delete(cwd, session_id, agent_id)
        sys.stderr.write(
            "record_check: BLOCKED unbound or expired agent role\n\n"
            "0|0|REV4|agent return is not bound to a live mailbox in the current turn|dispatch the named harness role again\n"
        )
        return 2

    if agent != "reviewer":
        gatelib.fail_review_receipt(cwd, session_id, agent_id)

    if message is None or message == "":
        problems = [(1, "no output", "return the agent's verdict and fixed records")]
        rules = []
    elif not isinstance(message, str):
        problems = [(1, "return is not text", "return the agent's verdict and fixed records")]
        rules = []
    else:
        message = token_shrink.normalize_schema(message)
        problems, rules = parse_return(agent, message)

    if agent == "maintainer" and not problems and isinstance(message, str):
        verdict = VERDICT_RE.fullmatch(message.split("\n", 1)[0])
        if verdict and verdict.group(2) == "READY":
            repair_line = next(
                (line for line in message.splitlines() if line.startswith("repair|")),
                "",
            )
            repair_kind = repair_line.split("|", 2)[1] if repair_line.count("|") >= 2 else ""
            assigned_kind = prior.get("recovery_kind")
            if assigned_kind not in gatelib.RECOVERY_KINDS or repair_kind != assigned_kind:
                problems.append(
                    (
                        1,
                        "repair kind is not bound to this maintainer assignment",
                        "return READY only for the exact parent-selected recovery",
                    )
                )

    if rules:
        # a rule| proposal never enters the writer's stream — it reaches the
        # human by systemMessage, so it cannot be mistaken for a finding
        gatelib.emit_json({"systemMessage": "record_check: %s proposes:\n%s" % (agent, "\n".join(rules))})

    if not problems:
        if agent == "reviewer":
            verdict = VERDICT_RE.fullmatch(message.split("\n", 1)[0]).group(2)
            receipt = gatelib.finish_review_receipt(cwd, session_id, agent_id, verdict)
            if not receipt:
                gatelib.agent_mailbox_write(
                    cwd,
                    session_id,
                    agent_id,
                    agent_type="reviewer",
                    state="failed",
                    repair_attempted=True,
                    result="",
                )
                sys.stderr.write(
                    "record_check: BLOCKED reviewer\n\n"
                    "0|0|REV4|review receipt is absent, stale, expired, or for a changed target|dispatch one reviewer on the current immutable target\n"
                )
                return 2
            gatelib.agent_mailbox_delete(cwd, session_id, agent_id)
            agent_dispatch.finish(cwd, session_id, agent_id, "accepted", message)
        else:
            normalized = token_shrink.shrink_return(agent, message)
            complete_mailbox(
                cwd,
                session_id,
                agent_id,
                agent,
                normalized,
            )
            agent_dispatch.finish(cwd, session_id, agent_id, "accepted", normalized)
        return 0

    # ownership, no duplicate id: shape problems cite OUT1; only a well-formed
    # record's id was checked, citing REV10
    records = []
    for n, subject, remedy in problems:
        rid = "REV10" if ("live id" in subject or "removed" in subject) else "OUT1"
        records.append("%d|0|%s|%s|%s" % (n, rid, subject, remedy))

    retry_used = bool(prior.get("repair_attempted"))
    if retry_used:
        if agent == "reviewer":
            gatelib.fail_review_receipt(cwd, session_id, agent_id)
            gatelib.agent_mailbox_write(
                cwd,
                session_id,
                agent_id,
                agent_type="reviewer",
                state="failed",
                repair_attempted=True,
                result="",
            )
            sys.stderr.write("record_check: BLOCKED reviewer\n\n%s\n" % "\n".join(records))
            agent_dispatch.release(cwd, session_id, agent_id)
            return 2
        fallback = "%s: ENV\n\nENV|agent-return|unparseable or absent after retry" % agent
        complete_mailbox(
            cwd,
            session_id,
            agent_id,
            agent,
            fallback,
        )
        agent_dispatch.finish(cwd, session_id, agent_id, "accepted", fallback)
        gatelib.emit_json(
            {
                "systemMessage": "record_check: %s return still malformed after retry - typed ENV:\n%s"
                % (agent, "\n".join(records))
            }
        )
        return 0

    # Keep a review receipt pending across the single repair attempt. A
    # corrected second return can then prove the same immutable target.
    if session_id and agent_id:
        agent_dispatch.finish(cwd, session_id, agent_id, "repairable")
        gatelib.agent_mailbox_write(
            cwd,
            session_id,
            agent_id,
            agent_type=agent,
            state=prior.get("state") or ("reviewing" if agent == "reviewer" else "pending"),
            overlap=bool(prior.get("overlap")),
            result=prior.get("result", ""),
            repair_attempted=True,
        )
    sys.stderr.write("record_check: BLOCKED %s\n\n%s\n" % (agent, "\n".join(records)))
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as error:
        sys.stderr.write("record_check: BLOCKED gate crashed: %s: %s\n" % (type(error).__name__, str(error)[:160]))
        sys.exit(2)
