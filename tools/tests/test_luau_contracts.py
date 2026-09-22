"""Native parser regressions for distilled Luau contracts; no Studio required."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import lint_driver


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


deny = load("contracts_deny", "tools/deny_scan/deny_scan.py")
style = load("contracts_style", "tools/style_assess/style_assess.py")
boilerplate = load("contracts_frames", "tools/create_boilerplate/create_boilerplate.py")


class LuauContracts(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "src" / "Example.luau"
        self.source.parent.mkdir()
        globals_file = self.root / "api_globals.luau"
        globals_file.write_text("return {}\n")
        for module in (deny, style, lint_driver):
            for key, value in (("CACHE", str(self.root)), ("GLOBALS_PATH", str(globals_file))):
                patch = mock.patch.object(module, key, value)
                patch.start()
                self.addCleanup(patch.stop)

    def scan(self, source, checker=deny, fix=False):
        self.source.write_text(source)
        stdout, stderr = io.StringIO(), io.StringIO()
        args = ["--root", str(self.root), str(self.source)]
        if fix:
            args.insert(0, "--fix")
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = checker.main(args)
        return status, stdout.getvalue() + stderr.getvalue()

    def test_balanced_profiles_across_branches_and_nested_scopes(self):
        cases = [
            'debug.profilebegin("a")\ndebug.profilebegin("b")\ndebug.profileend()\ndebug.profileend()',
            'debug.profilebegin("a")\nif x then debug.profileend() return end\ndebug.profileend()',
            'debug.profilebegin("a")\nif x then debug.profileend() else debug.profileend() end',
            'debug.profilebegin("a")\ndo debug.profileend() end',
            'debug.profilebegin("a")\nlocal function f() return end\ndebug.profileend()',
            'debug.profilebegin("a")\nwhile x do if y then break end end\ndebug.profileend()',
            'while x do debug.profilebegin("a")\nif y then debug.profileend() continue end\ndebug.profileend() end',
            'repeat debug.profilebegin("a") debug.profileend() until x',
            'for i = 1, 3 do debug.profilebegin("a") debug.profileend() end',
            'for _, v in values do debug.profilebegin("a") debug.profileend() end',
            'while true do debug.profilebegin("a") break end debug.profileend()',
            'repeat debug.profilebegin("a") until true debug.profileend()',
            'while false do debug.profileend() end',
            'if false then debug.profileend() elseif true then debug.profilebegin("a") end debug.profileend()',
            'debug.profilebegin("a")\nlocal ok, err = pcall(work)\ndebug.profileend()\nif not ok then error(err) end',
        ]
        for source in cases:
            with self.subTest(source=source):
                status, output = self.scan(source)
                self.assertEqual(status, 0, output)

    def test_unbalanced_profiles_fail_on_each_exit_kind(self):
        cases = [
            'debug.profileend()',
            'debug.profilebegin("a")',
            'debug.profilebegin("a")\nif x then return end\ndebug.profileend()',
            'debug.profilebegin("a")\nif x then debug.profileend() end',
            'while x do debug.profilebegin("a") break end',
            'while x do debug.profilebegin("a") continue end',
            'repeat debug.profilebegin("a") until x',
            'debug.profilebegin("a")\nlocal function f() debug.profileend() end',
            'debug.profilebegin("a") error("bad")',
            'debug.profilebegin("a")\nif x then debug.profileend() elseif y then return else debug.profileend() end',
        ]
        for source in cases:
            with self.subTest(source=source):
                status, output = self.scan(source)
                self.assertEqual(status, 2, output)
                self.assertIn("OPT20", output)

    def test_parallel_pairing_and_implicit_callback_entry(self):
        cases = [
            'task.desynchronize()\ntask.synchronize()',
            'task.synchronize()',  # idempotent, including helpers called in parallel
            'task.desynchronize()\nif x then task.synchronize() return end\ntask.synchronize()',
            'actor:BindToMessageParallel("Work", function() task.synchronize() end)',
            'event:ConnectParallel(function() task.synchronize() end)',
            'event:ConnectParallel(function() compute() end)',
            'while x do task.desynchronize() task.synchronize() continue end',
            'task.desynchronize()\ndo task.synchronize() end',
        ]
        for source in cases:
            with self.subTest(source=source):
                status, output = self.scan(source)
                self.assertEqual(status, 0, output)

    def test_parallel_missing_pair_and_require_fail(self):
        cases = [
            'task.desynchronize()',
            'task.desynchronize() if x then return end task.synchronize()',
            'task.desynchronize() if x then task.synchronize() end',
            'task.desynchronize() local function f() task.synchronize() end',
            'while x do task.desynchronize() continue end',
            'while x do task.desynchronize() break end',
            'task.desynchronize() local m = require("./m") task.synchronize()',
            'event:ConnectParallel(function() require("./m") end)',
        ]
        for source in cases:
            with self.subTest(source=source):
                status, output = self.scan(source)
                self.assertEqual(status, 2, output)
                self.assertIn("OPT15", output)

    def test_shadowed_libraries_comments_strings_and_independent_functions(self):
        source = '''-- debug.profileend(); task.desynchronize()
const TEXT = "debug.profilebegin('x'); task.desynchronize()"
local function f(debug, task)
    debug.profileend()
    task.desynchronize()
end
local function g() debug.profilebegin("a") debug.profileend() end
'''
        status, output = self.scan(source)
        self.assertEqual(status, 0, output)

    def test_const_formatter_keeps_bindings_and_is_idempotent(self):
        source = '''const Players = game:GetService("Players")
const X ,Y = 1,2
const function greet()
    local const = 2
    print('hello', X,Y, const)
end
const m = {Players = Players,greet = greet,}
return m
'''
        status, output = self.scan(source, style, fix=True)
        self.assertEqual(status, 0, output)
        self.assertNotIn("NOTED", output)
        fixed = self.source.read_text()
        for text in ("const Players", "const X, Y", "const function greet", "local const", "const m"):
            self.assertIn(text, fixed)
        status, output = self.scan(fixed, style, fix=True)
        self.assertEqual(status, 0, output)
        self.assertEqual(self.source.read_text(), fixed)

    def test_const_binding_mutation_is_still_rejected(self):
        for assignment in ("X = 2", "X += 1", "local function f() X = 2 end"):
            with self.subTest(assignment=assignment):
                status, output = self.scan("const X = 1\n" + assignment)
                self.assertEqual(status, 2, output)
                self.assertIn("GATE4", output)
        status, output = self.scan('const T = {}\nT.x = 1')
        self.assertEqual(status, 0, output)

    def test_style_and_advisory_performance_fail_on_parser_failure(self):
        status, output = self.scan("const X = 1\nX = 2", style)
        self.assertEqual(status, 2, output)
        with contextlib.redirect_stderr(io.StringIO()) as err:
            status = lint_driver.scan("performance", str(ROOT / "tools/perf_audit/rules"),
                                      [str(self.source)], fails_open=True)
        self.assertEqual(status, 2, err.getvalue())

    def test_structured_parser_diagnostic_is_not_a_performance_advisory(self):
        self.source.write_text("return {}")
        report = json.dumps({"items": [{"uri": str(self.source), "items": [{
            "range": {"start": {"line": 0, "character": 0}},
            "code": "SyntaxError", "message": "invalid source",
        }]}]})
        result = subprocess.CompletedProcess([], 0, report, "")
        with mock.patch.object(lint_driver.subprocess, "run", return_value=result), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            status = lint_driver.scan("performance", str(ROOT / "tools/perf_audit/rules"),
                                      [str(self.source)], fails_open=True)
        self.assertEqual(status, 2, err.getvalue())
        self.assertIn("GATE4", err.getvalue())

    def test_const_frames_pass_and_format_without_changes(self):
        for frame in (boilerplate.FRAME, boilerplate.CONTROLLER_FRAME, boilerplate.TOOL_FRAME):
            with self.subTest(frame=frame):
                status, output = self.scan(frame, style, fix=True)
                self.assertEqual(status, 0, output)
                self.assertEqual(self.source.read_text(), frame)

    def test_literal_codec_advisories_and_valid_widths(self):
        for source in ('buffer.writeu32(b, 0, player.UserId)', 'buffer.writef32(b, 0, player.UserId)',
                       'buffer.writeu8(b, 0, 256)', 'buffer.writei8(b, 0, 128)', 'buffer.writeu8(b, 0, 1.5)',
                       'buffer.writeu8(b, 0, -1)', 'buffer.writei8(b, 0, -129)', 'buffer.writeu16(b, 0, 65_536)'):
            status, output = self.scan(source)
            self.assertEqual(status, 0, output)
            self.assertIn("DATA38", output)
        for source in ('buffer.writef64(b, 0, player.UserId)', 'buffer.writeu8(b, 0, 255)',
                       'local function f(buffer) buffer.writeu8(b, 0, 999) end'):
            status, output = self.scan(source)
            self.assertEqual(status, 0, output)
            self.assertNotIn("DATA38", output)

    def test_owned_global_state_rejected_but_local_names_pass(self):
        for source in ('_G.State = 1', 'shared.State = 1'):
            status, output = self.scan(source)
            self.assertEqual(status, 2, output)
            self.assertIn("WRIT18", output)
        status, output = self.scan('local shared = {}\nshared.State = 1')
        self.assertEqual(status, 0, output)

    def test_performance_tracks_nested_writes_and_retains_advisory_labels(self):
        cases = [
            ('event:ConnectParallel(function() if x then part.Position = value end end)', True),
            ('task.desynchronize() if x then part:Destroy() end task.synchronize()', True),
            ('task.desynchronize() do task.synchronize() end part.Position = value', False),
            ('event:ConnectParallel(function() task.synchronize() part.Position = value end)', False),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                self.source.write_text(source)
                with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
                    status = lint_driver.scan("performance", str(ROOT / "tools/perf_audit/rules"),
                                              [str(self.source)], fails_open=True)
                self.assertEqual(status, 0, err.getvalue())
                self.assertEqual("OPT15" in out.getvalue(), expected, out.getvalue())
        self.source.write_text('RunService.Heartbeat:Connect(function() work() end)')
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            status = lint_driver.scan("performance", str(ROOT / "tools/perf_audit/rules"),
                                      [str(self.source)], fails_open=True)
        self.assertEqual(status, 0, err.getvalue())
        self.assertIn("OPT20", out.getvalue())

    def test_unreliable_remote_uses_existing_event_ownership_rule(self):
        self.source.write_text('const Remote = Instance.new("UnreliableRemoteEvent")')
        args = ["--root", str(self.root), str(self.source)]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
            status = lint_driver.scan("replication_audit", str(ROOT / "tools/replication_audit/rules"), args)
        self.assertEqual(status, 2, err.getvalue())
        self.assertIn("WRIT8", err.getvalue())
        event = self.root / "Packages/Event.luau"
        event.parent.mkdir()
        event.write_text(self.source.read_text())
        with contextlib.redirect_stderr(io.StringIO()) as err:
            status = lint_driver.scan("replication_audit", str(ROOT / "tools/replication_audit/rules"), [str(event)])
        self.assertEqual(status, 0, err.getvalue())

    def test_rule_crash_cannot_report_clean(self):
        report = 'Error applying lint rule broken\n' + json.dumps({"items": []})
        result = subprocess.CompletedProcess([], 0, report, "")
        with mock.patch.object(style.subprocess, "run", return_value=result):
            findings, error = style.run_lint(style.RULES, "unused", [str(self.source)])
        self.assertIsNone(findings)
        self.assertIn("broken", error)
        self.source.write_text("return {}")
        with mock.patch.object(lint_driver.subprocess, "run", return_value=result), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            status = lint_driver.scan("performance", str(ROOT / "tools/perf_audit/rules"), [str(self.source)], fails_open=True)
        self.assertEqual(status, 2, err.getvalue())


if __name__ == "__main__":
    unittest.main()
