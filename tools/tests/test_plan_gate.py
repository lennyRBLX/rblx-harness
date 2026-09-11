#!/usr/bin/env python3
"""Offline behavioral checks for plan validation and hook scope."""

import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared/gates"))
import adapterlib
import plan_gate


PLAN = '''<!-- rblx-plan -->
# Motion controller

Deliver movement with verified teardown.
Store evidence at `evidence/motion`.

## Architecture

Assign client state and connection cleanup to `src/Motion.luau`.

## APIs

- Use `Motion.Stop()` from teardown to release connections; review `src/Motion.luau:1-4`.

## Luau Types

```luau
export type Motion = { Stop: () -> () }
```

## Milestones

### M01 — Motion lifecycle

Requires: —
Context: Review `src/Motion.luau:1-4`.
Write: `src/Motion.luau`.

1. Implement the motion lifecycle.
2. Verify cleanup after teardown; human reports the Studio result.

Complete: Record the teardown result; receipt `evidence/motion/M01.md`.
'''
COMPLETE = PLAN[:PLAN.index("### M01")] + "Complete.\n"


class FormatTest(unittest.TestCase):
    def test_plan_response_and_inapplicable_types(self):
        self.assertEqual(plan_gate.validate(PLAN), [])
        self.assertEqual(plan_gate.validate("<proposed_plan>\n" + PLAN + "</proposed_plan>"), [])
        self.assertEqual(plan_gate.validate(PLAN.replace(
            "```luau\nexport type Motion = { Stop: () -> () }\n```", "—")), [])
        self.assertEqual(plan_gate.validate(COMPLETE), [])

    def test_missing_sections_reordered_fields_and_invalid_actions(self):
        changes = [
            ("## APIs", "## API"),
            ("Context: Review `src/Motion.luau:1-4`.\nWrite: `src/Motion.luau`.",
             "Write: `src/Motion.luau`.\nContext: Review `src/Motion.luau:1-4`."),
            ("2. Verify", "3. Verify"),
            ("2. Verify", "2. Consider"),
            ("### M01 —", "### Step 1 —"),
            ("```luau", "```lua"),
            ("1. Implement", "1. Do not implement"),
        ]
        for before, after in changes:
            with self.subTest(after=after):
                self.assertTrue(plan_gate.validate(PLAN.replace(before, after)))

    def test_literals_do_not_trigger_prose_checks(self):
        text = PLAN.replace("export type Motion = { Stop: () -> () }",
                            'export type Motion = { reason: "Never stop" }')
        self.assertEqual(plan_gate.validate(text), [])
        self.assertFalse(plan_gate.is_plan("# Notes\n```markdown\n" + PLAN + "\n```"))

    def test_duplicate_ids_and_completed_checkboxes_fail(self):
        duplicate = PLAN + PLAN[PLAN.index("### M01"):]
        self.assertTrue(plan_gate.validate(duplicate))
        self.assertTrue(plan_gate.validate(PLAN.replace("1. Implement", "- [x] Implement")))

    def test_standalone_cli_matches_validation(self):
        for text, expected in ((PLAN, 0), ("# Incomplete plan", 2)):
            result = subprocess.run([sys.executable, str(ROOT / "shared/gates/plan_gate.py"), "--stdin"],
                                    input=text, text=True, capture_output=True)
            self.assertEqual(result.returncode, expected, result.stderr)


class HookTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "project"
        self.root.mkdir()
        self.git("init", "--quiet")
        self.git("config", "user.name", "plan-test")
        self.git("config", "user.email", "plan-test@example.invalid")
        self.write(".gitignore", "/.codex/\n/.agents/\n/ignored/\n")
        patcher = mock.patch.object(plan_gate, "CACHE", Path(self.temporary.name) / "cache")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.payload = {"cwd": str(self.root), "session_id": "session-a", "turn_id": "turn-a",
                        "tool_name": "Bash", "tool_input": {"command": "python3 write_plan.py"}}

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)

    def write(self, name, text):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        return target

    def dispatch(self, event, **extra):
        output, errors = io.StringIO(), io.StringIO()
        payload = dict(self.payload, hook_event_name=event, **extra)
        with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            result = adapterlib.main("codex", ["--event", event])
        self.assertEqual(result, 0, errors.getvalue())
        return json.loads(output.getvalue() or "{}")

    def test_untouched_legacy_plan_and_ordinary_reply_pass(self):
        self.write("legacy.plan.md", "# Legacy\n### M01 — Existing milestone\nExisting plan format")
        self.write("existing.plan.md", PLAN)
        self.dispatch("PreToolUse")
        self.assertEqual(self.dispatch("Stop", last_assistant_message="Updated the controller."), {})

    def test_new_arbitrary_filename_plan_is_checked_and_corrected(self):
        self.dispatch("PreToolUse")
        path = self.write("design café.md", "<!-- rblx-plan -->\n# Work\n")
        result = self.dispatch("Stop", last_assistant_message="Saved the plan.")
        self.assertEqual(result["decision"], "block")
        self.assertIn("design café.md", result["reason"])
        path.write_text(PLAN)
        self.assertEqual(self.dispatch("Stop", stop_hook_active=True), {})

    def test_existing_file_becoming_plan_and_committed_edits_are_checked(self):
        self.write("notes.md", "# Notes\nDraft")
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "initial")
        self.dispatch("PreToolUse")
        self.write("notes.md", "# Implementation Plan\n1. Implement motion.")
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "plan")
        self.assertEqual(self.dispatch("Stop")["decision"], "block")

    def test_first_snapshot_survives_later_tools(self):
        self.dispatch("PreToolUse")
        self.write("motion.plan.md", "# Motion")
        with mock.patch.object(plan_gate, "snapshot", side_effect=AssertionError("snapshot repeated")):
            self.dispatch("PreToolUse")
        self.assertEqual(self.dispatch("Stop")["decision"], "block")

    def test_snapshot_isolated_by_session_and_refreshed_per_turn(self):
        self.dispatch("PreToolUse")
        self.write("motion.plan.md", "# Motion")
        self.dispatch("PreToolUse", session_id="session-b")
        self.assertEqual(self.dispatch("Stop", session_id="session-b"), {})
        self.assertEqual(self.dispatch("Stop")["decision"], "block")

    def test_receipts_required_for_removed_milestone(self):
        self.write("motion.plan.md", PLAN)
        self.dispatch("PreToolUse")
        self.write("motion.plan.md", COMPLETE)
        result = self.dispatch("Stop")
        self.assertEqual(result["decision"], "block")
        self.assertIn("completion receipt", result["reason"])
        # Stop continuations have a new turn ID; retain the original removed IDs.
        self.payload["turn_id"] = "turn-b"
        self.dispatch("PreToolUse")
        self.assertEqual(self.dispatch("Stop")["decision"], "block")
        self.write("evidence/motion/M01.md", "Revision: abc123\nEvidence: Human reported cleanup passed.\n\n"
                   + PLAN[PLAN.index("### M01"):])
        self.assertEqual(self.dispatch("Stop", stop_hook_active=True), {})

    def test_renaming_plan_does_not_bypass_validation(self):
        path = self.write("motion.plan.md", PLAN)
        self.dispatch("PreToolUse")
        path.rename(self.root / "notes.md")
        self.assertEqual(self.dispatch("Stop")["decision"], "block")

    def test_dependency_ignored_and_external_link_documents_are_excluded(self):
        self.dispatch("PreToolUse")
        self.write("rblx-harness/shared/PLAN.md", "# Plan")
        self.write("ignored/invalid.plan.md", "# Plan")
        outside = Path(self.temporary.name) / "outside.plan.md"
        outside.write_text("# Plan")
        (self.root / "link.plan.md").symlink_to(outside)
        self.assertEqual(self.dispatch("Stop"), {})

    def test_response_without_tools_retries_once_then_reports_unresolved(self):
        result = self.dispatch("Stop", last_assistant_message="<proposed_plan>bad</proposed_plan>")
        self.assertEqual(result["decision"], "block")
        result = self.dispatch("Stop", last_assistant_message="Saved.", stop_hook_active=True)
        self.assertFalse(result["continue"])
        self.assertIn("unresolved", result["systemMessage"])
        self.assertEqual(self.dispatch("Stop", last_assistant_message=PLAN, stop_hook_active=True), {})

    def test_plan_mode_questions_pass_and_unformatted_steps_fail(self):
        self.assertEqual(self.dispatch("Stop", permission_mode="plan", last_assistant_message="Which place owns motion?"), {})
        self.assertEqual(self.dispatch("Stop", permission_mode="plan", last_assistant_message="1. Implement motion.")["decision"], "block")

    def test_real_hook_adapter_and_gate_agree(self):
        raw = json.dumps(dict(self.payload, last_assistant_message=PLAN))
        commands = [
            [str(ROOT / "openai/hooks/adapter.py"), "--host", "codex", "--event", "Stop"],
            [str(ROOT / "shared/gates/plan_gate.py"), "--event", "Stop"],
        ]
        results = [subprocess.run([sys.executable, *command], input=raw, capture_output=True, text=True)
                   for command in commands]
        self.assertEqual([(r.returncode, r.stdout, r.stderr) for r in results], [(0, "{}\n", "")] * 2)


if __name__ == "__main__":
    unittest.main()
