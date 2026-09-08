#!/usr/bin/env python3
"""Offline checks for validation batching, output, and focused case selection."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]


def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


project_gate = load_module("project_validation_test", "tools/project_gate/project_gate.py")
boot_smoke = load_module("boot_output_test", "tools/boot_smoke/boot_smoke.py")
runner = load_module("verification_selection_test", "tools/tests/run_verify.py")
finalize = load_module("completion_validation_test", "shared/gates/finalize.py")


class ProjectValidationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True)
        (self.root / ".gitignore").write_text("/.agents/\n/.codex/\n/.serena/\n/.roblox\n")

    def validate(self):
        errors = []
        with mock.patch.object(project_gate.gatelib, "git", wraps=project_gate.gatelib.git) as git:
            project_gate.validate_local_state(str(self.root), errors)
        self.assertEqual(git.call_count, 2)
        return errors

    def test_ignored_untracked_state_passes_in_two_calls(self):
        self.assertEqual(self.validate(), [])

    def test_missing_rules_and_negation_still_fail_per_path(self):
        (self.root / ".gitignore").write_text(
            "/.agents/\n/.codex/*\n!/.codex/.rblx-harness-probe\n/.roblox\n"
        )
        self.assertEqual(self.validate(), [
            "local state is not ignored: .codex", "local state is not ignored: .serena",
        ])

    def test_tracked_ignored_files_and_unusual_filenames_still_fail(self):
        (self.root / ".codex").mkdir()
        (self.root / ".codex" / "settings café").write_text("tracked")
        (self.root / ".roblox").write_text("tracked")
        subprocess.run(["git", "-C", str(self.root), "add", "--force", "--", ".codex", ".roblox"], check=True)
        self.assertEqual(self.validate(), [
            "local state must not be tracked: .codex", "local state must not be tracked: .roblox",
        ])

    def test_git_failure_does_not_accept_partial_output(self):
        errors = []
        with mock.patch.object(project_gate.gatelib, "git", side_effect=[
            (128, "", "index unavailable"), (128, ".roblox\n", "ignore check failed"),
        ]):
            project_gate.validate_local_state(str(self.root), errors)
        for relative in project_gate.LOCAL_STATE:
            self.assertIn("local state: cannot inspect %s: index unavailable" % relative, errors)
            self.assertIn("local state is not ignored: %s" % relative, errors)


class BootOutputTest(unittest.TestCase):
    def invoke(self, args=None):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = boot_smoke.main(args or [])
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        return status, json.loads(output.getvalue())

    def test_console_log_diagnostics_and_exit_status_are_preserved(self):
        for line, expected_status in (("warn: delayed", 0), ('error: bad "value"', 2)):
            with self.subTest(line=line), tempfile.TemporaryDirectory() as temp:
                log = Path(temp) / "console.log"
                log.write_text(line + "\n")
                with mock.patch.object(boot_smoke, "stage_sourcemap", return_value=({"pass": True}, "map")), \
                        mock.patch.object(boot_smoke, "stage_analyze", return_value={"pass": True, "findings": 0, "lines": []}), \
                        mock.patch.object(boot_smoke, "stage_play", side_effect=AssertionError("must use supplied log")):
                    status, verdict = self.invoke(["--console-log", str(log)])
                self.assertEqual(status, expected_status)
                self.assertEqual(verdict["pass"], expected_status == 0)
                self.assertEqual(verdict["play"], boot_smoke.stage_play_from_log(str(log)))

    def test_sourcemap_failure_retains_detail_and_stops_later_stages(self):
        detail = {"pass": False, "detail": "project build failed\nmissing source"}
        with mock.patch.object(boot_smoke, "stage_sourcemap", return_value=(detail, None)), \
                mock.patch.object(boot_smoke, "stage_analyze") as analyze, \
                mock.patch.object(boot_smoke, "stage_play") as play:
            status, verdict = self.invoke()
        self.assertEqual(status, 2)
        self.assertEqual(verdict, {"sourcemap": detail, "analyze": None, "play": None, "pass": False})
        analyze.assert_not_called()
        play.assert_not_called()

    def test_analyze_failure_retains_findings_and_still_checks_play(self):
        findings = {"pass": False, "findings": 1, "lines": ["source.luau(1,2): TypeError: mismatch"]}
        with mock.patch.object(boot_smoke, "stage_sourcemap", return_value=({"pass": True}, "map")), \
                mock.patch.object(boot_smoke, "stage_analyze", return_value=findings), \
                mock.patch.object(boot_smoke, "stage_play", return_value={"pass": True}) as play:
            status, verdict = self.invoke()
        self.assertEqual(status, 2)
        self.assertEqual(verdict["analyze"], findings)
        self.assertFalse(verdict["pass"])
        play.assert_called_once()

    def test_environment_failure_preserves_partial_verdict_and_remedy(self):
        with mock.patch.object(boot_smoke, "stage_sourcemap", return_value=({"pass": True}, "map")), \
                mock.patch.object(boot_smoke, "stage_analyze", side_effect=boot_smoke.EnvError("missing-tool", "install tool")), \
                mock.patch.object(boot_smoke, "stage_play") as play:
            status, verdict = self.invoke()
        self.assertEqual(status, 3)
        self.assertFalse(verdict["pass"])
        self.assertEqual(verdict["sourcemap"], {"pass": True})
        self.assertIsNone(verdict["analyze"])
        self.assertEqual(verdict["environment"], {"cause": "missing-tool", "remedy": "install tool"})
        play.assert_not_called()


class VerificationSelectionTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        cases = [(name, lambda name=name: self.calls.append(name)) for name in ("API access", "API docs", "Hook rules")]
        patcher = mock.patch.object(runner, "CASES", cases)
        patcher.start()
        self.addCleanup(patcher.stop)

    def invoke(self, args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = runner.main(args)
        return status, output.getvalue()

    def test_default_runs_all_cases_and_retains_full_suite_verdict(self):
        status, output = self.invoke([])
        self.assertEqual(status, 0)
        self.assertEqual(self.calls, ["API access", "API docs", "Hook rules"])
        self.assertIn("VERIFY|READY|3\n", output)

    def test_selection_is_case_insensitive_ordered_and_deduplicated(self):
        status, output = self.invoke(["--case", "docs", "--case", "api"])
        self.assertEqual(status, 0)
        self.assertEqual(self.calls, ["API access", "API docs"])
        self.assertIn("VERIFY|SELECTED|READY|2/3|failures=0\n", output)
        self.assertNotIn("VERIFY|READY|", output)

    def test_listing_runs_no_cases(self):
        status, output = self.invoke(["--list"])
        self.assertEqual(status, 0)
        self.assertEqual(output.splitlines(), ["API access", "API docs", "Hook rules"])
        self.assertEqual(self.calls, [])

    def test_unknown_or_empty_selection_fails_before_running_any_case(self):
        for pattern in ("unknown", "", " "):
            with self.subTest(pattern=pattern), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                self.invoke(["--case", "api", "--case", pattern])
            self.assertEqual(raised.exception.code, 2)
        self.assertEqual(self.calls, [])

    def test_failures_remain_blocking_and_other_selected_cases_still_run(self):
        def fail():
            raise AssertionError("retained failure detail")
        runner.CASES.insert(0, ("API failure", fail))
        for args in ([], ["--case", "api"]):
            with self.subTest(args=args):
                self.calls.clear()
                status, output = self.invoke(args)
                self.assertEqual(status, 2)
                self.assertIn("FAIL|API failure|retained failure detail", output)
                self.assertEqual(len(self.calls), 2 if args else 3)
                self.assertIn("VERIFY|SELECTED|FAILED|3/4|failures=1" if args else "VERIFY|FAILED|1/4", output)

    def test_completion_still_invokes_unfiltered_full_suite(self):
        with mock.patch.object(finalize.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run, \
                contextlib.redirect_stdout(io.StringIO()):
            status = finalize.main(["--root", str(ROOT), "--session", "validation-test"])
        self.assertEqual(status, 0)
        self.assertEqual(run.call_args.args[0], [finalize.sys.executable, str(ROOT / "tools/tests/run_verify.py")])


if __name__ == "__main__":
    unittest.main()
