#!/usr/bin/env python3
"""Write one authorized session-scoped baseline at UserPromptSubmit."""

import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gatelib  # noqa: E402
import agent_dispatch  # noqa: E402


NEGATED_STUDIO = re.compile(
    r"(?:\b(?:do\s+not|don['’]?t|does\s+not|doesn['’]?t|did\s+not|didn['’]?t|"
    r"is\s+not|isn['’]?t|are\s+not|aren['’]?t|will\s+not|won['’]?t|"
    r"not|never|without|avoid|exclude|excluding|omit|omitting|skip|"
    r"no(?:\s+need\s+to)?)\b|\bnon[-\s]*)[^.;,\n]{0,64}$",
    re.IGNORECASE,
)
POST_NEGATED_STUDIO = re.compile(
    r"^(?:\s+(?:is|are|was|were|will|would|should|must|does|do|needs?|needed)){0,3}"
    r"\s+(?:not|never|unnecessary|optional)\b"
    r"|^\s+(?:isn['’]?t|aren['’]?t|wasn['’]?t|weren['’]?t|won['’]?t|"
    r"wouldn['’]?t|shouldn['’]?t|doesn['’]?t|don['’]?t)\b"
    r"|^\s+(?:(?:is|are|was|were|will|would|should|must)\s+)?(?:be\s+)?"
    r"(?:avoided|excluded|omitted|skipped|unused|unneeded)\b"
    r"|^\s*-(?:free|less|independent)\b",
    re.IGNORECASE,
)
STUDIO_OPERATION = re.compile(
    r"\b(?:roblox\s+studio|studio|play[- ]?tests?|play[- ]?testing|"
    r"boot[_ -]?smoke|run[- ]?time\s+tests?|in[- ]?game\s+tests?)\b",
    re.IGNORECASE,
)


def studio_requested(prompt):
    if not isinstance(prompt, str):
        return False
    for match in STUDIO_OPERATION.finditer(prompt):
        clause_start = max(
            prompt.rfind("\n", 0, match.start()),
            prompt.rfind(".", 0, match.start()),
            prompt.rfind(";", 0, match.start()),
            prompt.rfind(",", 0, match.start()),
        )
        if (
            not NEGATED_STUDIO.search(prompt[clause_start + 1:match.start()])
            and not POST_NEGATED_STUDIO.search(prompt[match.end():])
        ):
            return True
    return False


def current_head(cwd):
    r = subprocess.run(
        ["git", "-C", cwd, "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"),
    )
    return r.stdout.strip() if r.returncode == 0 else "no-head"


def current_baseline(cwd):
    """Return a commit whose tree is the current tracked working tree.

    ``git stash create`` writes an unreachable snapshot object without
    changing the index, worktree, or stash refs.  A clean worktree produces
    no object, so HEAD is already the correct baseline.
    """
    return gatelib.current_turn_baseline(cwd)


def remove_legacy_state(cwd):
    for name in (".reviewed", ".turn", ".veto"):
        try:
            os.remove(os.path.join(cwd, "gates", name))
        except OSError:
            pass


def target(argv):
    cwd = os.getcwd()
    session_id = os.environ.get("CODEX_THREAD_ID", "")
    i = 0
    while i < len(argv):
        if argv[i] == "--root" and i + 1 < len(argv):
            cwd = argv[i + 1]
            i += 2
        elif argv[i] == "--session" and i + 1 < len(argv):
            session_id = argv[i + 1]
            i += 2
        else:
            i += 1
    turn = gatelib.read_turn_record(cwd, session_id)
    digest, paths = gatelib.review_target(cwd, turn)
    if not turn or not digest:
        sys.stderr.write("review-target: unavailable\n")
        return 2
    print("review-target|%s|%s|%d" % (turn["head"], digest, len(paths)))
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        payload = json.load(sys.stdin)
    except Exception:
        if not gatelib.is_roblox_project(os.getcwd()):
            return 0
        sys.stderr.write(gatelib.blocker_instruction("new-task", os.getcwd()) + "\n")
        return 2
    cwd = payload.get("cwd") or os.getcwd()
    if not gatelib.is_roblox_project(cwd):
        return 0
    session_id = payload.get("session_id") or os.environ.get("CODEX_THREAD_ID", "")
    if not session_id:
        sys.stderr.write(gatelib.blocker_instruction("new-task", cwd) + "\n")
        return 2
    scope = gatelib.hook_scope(argv)
    host = gatelib.hook_host(argv, payload)
    authorized, detail = gatelib.session_authorization_status(payload, cwd, scope, "UserPromptSubmit", host)
    if not authorized:
        degraded, _, repairs, _ = gatelib.session_recovery_status(
            payload,
            cwd,
            scope,
            "UserPromptSubmit",
            host,
        )
        if degraded:
            gatelib.emit_json(
                {
                    "continue": True,
                    "systemMessage": "session-gate: DEGRADED|RECOVERABLE",
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": gatelib.recovery_prompt_context(cwd, repairs),
                    },
                }
            )
            return 0
        profile_ok, profile_detail = (gatelib.permissions_harness() if host == "codex" else (True, ""))
        diagnostic = detail if profile_ok else profile_detail
        visible = (
            gatelib.permissions_harness_stop_reason(diagnostic, cwd)
            if host == "codex"
            else "Roblox harness did not authorize this Claude Code session: %s" % diagnostic[:200]
        )
        if host == "codex" and not profile_ok and gatelib.permissions_harness_install_accepted(payload.get("prompt")):
            installed, install_detail, _ = gatelib.install_permissions_harness()
            if installed:
                visible = gatelib.PERMISSIONS_HARNESS_INSTALLED_PROMPT
            else:
                diagnostic = "profile installation failed: %s" % install_detail
                visible = "Could not add the 'Roblox' permission mode: %s" % install_detail[:200]
        gatelib.emit_json(
            {
                "continue": True,
                "systemMessage": gatelib.session_block(host, diagnostic, cwd),
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": gatelib.permissions_harness_prompt_context(visible),
                },
            }
        )
        return 0
    gatelib.cleanup_review_receipts(cwd)
    gatelib.clear_session_review_receipts(cwd, session_id)
    gatelib.clear_session_type_records(cwd, session_id)
    gatelib.clear_session_agent_mailboxes(cwd, session_id)
    gatelib.clear_mutation_check(cwd, session_id)
    agent_dispatch.clear(cwd, session_id)
    for path in (
        gatelib.turn_record_path(cwd, session_id),
        gatelib.veto_path(cwd, session_id),
        gatelib.untracked_baseline_path(cwd, session_id),
        gatelib.studio_requirement_path(cwd, session_id),
        gatelib.stop_cache_path(cwd, session_id),
    ):
        try:
            os.remove(path)
        except OSError:
            pass
    remove_legacy_state(cwd)
    turn_id = payload.get("turn_id") or str(time.time_ns())
    prompt = payload.get("prompt")
    try:
        gatelib.write_untracked_baseline(cwd, session_id)
        gatelib.write_turn_record(cwd, session_id, turn_id, current_baseline(cwd))
        if studio_requested(prompt):
            try:
                gatelib.mark_studio_required(cwd, session_id)
            except OSError:
                pass
    except OSError as error:
        gatelib.emit_json(
            {
                "systemMessage": (
                    "turn-stamp: baseline deferred; the first source mutation will retry: %s"
                    % str(error)[:160]
                )
            }
        )
        return 0
    gatelib.emit_json(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": (
                    "After the workspace is settled and all required review receipts exist, "
                    "run this validation command as the last tool before the final response: %s"
                    % gatelib.finalization_command(cwd, session_id)
                ),
            }
        }
    )
    return 0


if __name__ == "__main__":
    if "--target" in sys.argv[1:]:
        sys.exit(target([arg for arg in sys.argv[1:] if arg != "--target"]))
    sys.exit(main())
