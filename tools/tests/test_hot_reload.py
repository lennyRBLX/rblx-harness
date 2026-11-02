"""HR1: Can staged changes preserve callers and refuse conflicting writes?

Stop at decisive offline contract results. Doubles do not establish Studio access,
engine scheduling/replication or live-consumer behavior. No gameplay tests added.
"""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/hot_reload")]
import hot_reload
import studio_source


class ReloadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.old = self.root / "original.luau"
        self.old.write_bytes(b'return {Value = "old"}\r\n')
        self.new = self.root / "changed.luau"
        self.new.write_bytes('return {Value = "炎"}\r\n'.encode())
        self.path = '["ReplicatedStorage", "Quoted\\\".炎"]'
        self.args = argparse.Namespace(
            action="patch", side="Server", session="HR1", path=self.path,
            source=self.new, expected=self.old, expected_editor=self.old,
            revision=0, audited=True,
        )

    def run_luau(self, source):
        path = self.root / "check.luau"
        path.write_text(source, encoding="utf-8")
        result = subprocess.run([str(ROOT / "tools/bin/lute"), "run", str(path)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_runtime_lifecycle_and_generated_commands(self):
        commands = []
        for name, action, revision in (
                ("bootstrap", "bootstrap", 0), ("poll", "poll", 0),
                ("status", "status", 0), ("patch", "patch", 0),
                ("undo", "undo", 1), ("patch2", "patch", 2)):
            self.args.action, self.args.revision = action, revision
            commands.append(f'commands.{name} = function(game, Instance)\n{hot_reload.build(self.args)}\nend\n')
        self.args.action, self.args.side = "bootstrap", "Client"
        commands.append(f'commands.client = function(game, Instance)\n{hot_reload.build(self.args)}\nend\n')
        assets = ROOT / "tools/hot_reload"
        core = studio_source.read_exact(assets / "PatchCore.luau")
        bridge = studio_source.read_exact(assets / "Bridge.server.luau")
        fixture = (ROOT / "tests/fixtures/hot_reload.luau").read_text()
        self.run_luau(
            'local Core = (function()\n' + core + '\nend)()\n'
            'local function Bridge(game, script, require, typeof, task)\n' + bridge + '\nend\n'
            'local commands = {}\n' + ''.join(commands) +
            '(function()\n' + fixture + '\nend)()(Core, Bridge, commands, ' +
            ', '.join(studio_source.literal(value) for value in (
                core, bridge, studio_source.read_exact(self.old), studio_source.read_exact(self.new))) + ')\n'
        )

    def test_exact_source_and_persistence_conflicts(self):
        self.args.action, self.args.side = "snapshot", "Edit"
        snapshot = studio_source.build(self.args)
        self.args.action = "persist"
        persist = studio_source.build(self.args)
        old, new = (studio_source.literal(studio_source.read_exact(p)) for p in (self.old, self.new))
        self.run_luau(f'''local Old, New = {old}, {new}
local Target = {{Name = "Quoted\\034.\\231\\130\\142", Source = Old, draft = Old}}
function Target:IsA(class) return class == "LuaSourceContainer" end
function Target:GetFullName() return self.Name end
local Folder = {{Name = "ReplicatedStorage"}}
function Folder:GetChildren() return {{Target}} end
local RunService = {{}}
local running = false
function RunService:IsStudio() return true end
function RunService:IsRunning() return running end
local Editor = {{}}
local conflict
function Editor:GetEditorSource(target) return target.draft end
function Editor:UpdateSourceAsync(target, callback)
    if conflict then conflict(target) end
    local nextSource = callback(target.draft)
    if nextSource then target.draft = nextSource end
end
local game = {{}}
function game:GetChildren() return {{Folder}} end
function game:GetService(name) return name == "RunService" and RunService or Editor end
local function Snapshot() {snapshot} end
local function Persist() {persist} end
assert(Snapshot().Stored == Old and Snapshot().Editor == Old)
for _, kind in {{"stored", "editor", "retry-editor", "retry-stored", "running"}} do
    Target.Source, Target.draft = Old, Old
    conflict = nil
    running = kind == "running"
    if kind == "stored" then Target.Source = "external" end
    if kind == "editor" then Target.draft = "external" end
    if kind == "retry-editor" then conflict = function(t) t.draft = "external" end end
    if kind == "retry-stored" then conflict = function(t) t.Source = "external" end end
    assert(not pcall(Persist), kind)
    assert(Target.Source ~= New and Target.draft ~= New, kind)
end
running, conflict = false, nil
Target.Source, Target.draft = Old, Old
assert(Persist().StoredMatches)
assert(Snapshot().Stored == New and Snapshot().Editor == New)
-- Duplicate instance names must fail before a write.
function Folder:GetChildren() return {{Target, Target}} end
assert(not pcall(Persist))
assert(Target.Source == New)
''')

    def test_cli_validation_and_path_file_dispatch(self):
        path = self.root / "target.json"
        path.write_text(self.path)
        output = self.root / "command.luau"
        base = [sys.executable, str(ROOT / "tools/harness.py"), "studio", "reload", "patch",
                "--side", "Server", "--session", "HR1", "--path-file", str(path),
                "--source", str(self.new), "--expected", str(self.old), "--revision", "0",
                "--audited", "--output", str(output)]
        result = subprocess.run(base, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output.is_file())
        original = output.read_bytes()
        for flag, value in (("--session", "bad/ID"), ("--revision", "-1"), ("--side", "Edit"),
                            ("--path-file", str(self.old)), ("--output", str(self.old)), ("--audited", None)):
            command = list(base)
            index = command.index(flag)
            if value is None:
                command.pop(index)
            else:
                command[index + 1] = value
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertEqual(output.read_bytes(), original)
            self.assertEqual(self.old.read_bytes(), b'return {Value = "old"}\r\n')


if __name__ == "__main__":
    unittest.main()
