#!/usr/bin/env python3
"""Offline Claude Code setup, hook migration, and permission profile regressions."""
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
sys.path.insert(0, str(ROOT / "shared/gates"))
import gatelib


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


setup = load("claude_setup", "setup_project.py")
adapter = load("claude_hook_adapter", "anthropic/hooks/adapter.py")
permissions = load("claude_permissions", "anthropic/setup/permissions_harness.py")
AGENT_FILES = ["debugger.md", "optimizer.md", "researcher.md", "reviewer.md"]


class Fixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


class SettingsTest(Fixture):
    canonical = (ROOT / "anthropic/config/settings.json").read_text()

    def test_custom_values_survive_and_merge_is_byte_stable(self):
        existing = json.dumps({
            "model": "opus",
            "env": {"MAX_MCP_OUTPUT_TOKENS": "9000", "CUSTOM": "1"},
            "permissions": {"deny": ["Edit(**/.luaurc)"]},
        })
        merged = gatelib.merge_project_claude_settings(existing, self.canonical)
        document = json.loads(merged)
        self.assertEqual(list(document), ["model", "env", "permissions"])
        self.assertEqual(document["permissions"], {"deny": ["Edit(**/.luaurc)"]})
        self.assertEqual(document["env"], {
            "MAX_MCP_OUTPUT_TOKENS": "9000", "CUSTOM": "1", "BASH_MAX_OUTPUT_LENGTH": "24000",
        })
        self.assertEqual(gatelib.merge_project_claude_settings(merged, self.canonical), merged)

    def test_complete_settings_are_returned_unchanged(self):
        existing = '{"env":{"BASH_MAX_OUTPUT_LENGTH":"1000","MAX_MCP_OUTPUT_TOKENS":"2000"}}'
        self.assertEqual(gatelib.merge_project_claude_settings(existing, self.canonical), existing)

    def test_invalid_settings_are_not_replaced(self):
        for source in ('{"env":', "[]", '{"env": []}'):
            with self.subTest(source=source):
                path = self.write(".claude/settings.json", source)
                with self.assertRaises((RuntimeError, ValueError)):
                    setup.copy_claude_support(str(self.root))
                self.assertEqual(path.read_text(), source)

    def test_custom_agents_skills_and_settings_survive_repeated_setup(self):
        agent = self.write(".claude/agents/custom.md", "---\nname: custom\n---\n")
        skill = self.write(".claude/skills/custom/SKILL.md", "custom instructions\n")
        rule = self.write(".claude/rules/custom.md", "custom rule\n")
        source = '{"env": {"BASH_MAX_OUTPUT_LENGTH": "9000", "MAX_MCP_OUTPUT_TOKENS": "9000"}}\n'
        settings = self.write(".claude/settings.json", source)
        self.write(".claude/skills/rblx-new-game/stale", "stale\n")
        for _ in range(2):
            setup.copy_claude_support(str(self.root))
            self.assertEqual(agent.read_text(), "---\nname: custom\n---\n")
            self.assertEqual(skill.read_text(), "custom instructions\n")
            self.assertEqual(rule.read_text(), "custom rule\n")
            self.assertEqual(
                (self.root / ".claude/rules" / setup.CLAUDE_RULE).read_text(),
                (ROOT / "anthropic/rules/delegation.md").read_text(),
            )
            self.assertEqual(settings.read_text(), source)
            self.assertTrue(gatelib.required_claude_agents_status(str(self.root))[0])
            self.assertTrue((self.root / ".claude/skills/rblx-writer/SKILL.md").is_file())
            self.assertFalse((self.root / ".claude/skills/rblx-new-game").exists())


class AgentTest(Fixture):
    def test_roles_inherit_model_and_cannot_delegate(self):
        self.assertEqual(sorted(path.name for path in (ROOT / "anthropic/agents").iterdir()), AGENT_FILES)
        for name in AGENT_FILES:
            with self.subTest(agent=name):
                fields, body = gatelib.claude_frontmatter((ROOT / "anthropic/agents" / name).read_text())
                denied = {tool.strip() for tool in fields["disallowedTools"].split(",")}
                self.assertEqual(fields["name"], name[:-3])
                self.assertTrue(fields["description"] and body)
                # Claude Code delegates automatically from this description phrase.
                self.assertIn("Use proactively", fields["description"])
                self.assertNotIn("model", fields)
                self.assertNotIn("tools", fields)
                self.assertIn("Agent", denied)
                if name != "debugger.md":
                    self.assertLessEqual({"Edit", "Write", "NotebookEdit"}, denied)

    def test_status_rejects_delegating_or_absent_agent(self):
        setup.copy_claude_support(str(self.root))
        path = self.root / ".claude/agents/reviewer.md"
        path.write_text(path.read_text().replace("disallowedTools: Agent, ", "disallowedTools: "))
        ok, detail = gatelib.required_claude_agents_status(str(self.root))
        self.assertFalse(ok)
        self.assertIn("nested delegation", detail)
        path.unlink()
        self.assertFalse(gatelib.required_claude_agents_status(str(self.root))[0])


class HookMigrationTest(Fixture):
    @staticmethod
    def retired(event, harness_gate=False):
        if harness_gate:
            args = ["-B", "${CLAUDE_PROJECT_DIR}/shared/gates/harness_gate.py", "--host", "claude", "--event", event]
        else:
            args = ["-B", "${CLAUDE_PROJECT_DIR}/.roblox-harness/claude/hooks/adapter.py",
                    "--host", "claude", "--event", event, "--hook-scope", "project"]
        return {"type": "command", "command": "python3", "args": args, "timeout": 60}

    def test_removes_only_retired_handlers_and_preserves_settings(self):
        custom = {"type": "command", "command": "echo claude/hooks/adapter.py"}
        document = {"custom": "retained", "permissions": {"deny": ["Edit(**/.luaurc)"]}, "hooks": {
            "Stop": [{"hooks": [self.retired("Stop"), custom]}],
            "SessionStart": [{"matcher": "startup", "hooks": [self.retired("SessionStart", harness_gate=True)]}],
        }}
        path = self.write(".claude/settings.json", json.dumps(document))
        setup.copy_claude_support(str(self.root))
        migrated = json.loads(path.read_text())
        self.assertEqual(migrated["hooks"], {"Stop": [{"hooks": [custom]}]})
        self.assertEqual(migrated["custom"], "retained")
        self.assertEqual(migrated["permissions"], document["permissions"])
        saved = path.read_bytes()
        setup.copy_claude_support(str(self.root))
        self.assertEqual(path.read_bytes(), saved)

    def test_all_retired_events_remove_the_hooks_key(self):
        events = ("PreToolUse", "Stop", "SessionStart", "PreCompact", "SubagentStart", "SubagentStop", "UserPromptSubmit")
        document = {"hooks": {event: [{"hooks": [self.retired(event)]}] for event in events}}
        path = self.write(".claude/settings.json", json.dumps(document))
        setup.copy_claude_support(str(self.root))
        self.assertNotIn("hooks", json.loads(path.read_text()))

    def test_custom_wrapper_and_other_event_are_untouched(self):
        handler = self.retired("Stop")
        self.assertTrue(adapter.retired_handler(handler, "Stop"))
        self.assertFalse(adapter.retired_handler(handler, "PreToolUse"))
        self.assertFalse(adapter.retired_handler(dict(handler, args=handler["args"] + ["--custom"]), "Stop"))
        self.assertFalse(adapter.retired_handler(dict(handler, command="python3.12"), "Stop"))
        self.assertFalse(adapter.retired_handler(dict(handler, type="prompt"), "Stop"))

    def test_malformed_hooks_are_untouched(self):
        for source in ('{"hooks":{"Stop":{}}}', '{"hooks":{"Stop":[{}]}}', '{"hooks":[]}'):
            with self.subTest(source=source):
                path = self.write(".claude/settings.json", source)
                with self.assertRaises(RuntimeError):
                    setup.copy_claude_support(str(self.root))
                self.assertEqual(path.read_text(), source)

    def test_adapter_exits_without_output(self):
        result = subprocess.run([sys.executable, "-B", str(ROOT / "anthropic/hooks/adapter.py")],
                                input='{"hook_event_name": "Stop"}', capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))


class ImportTest(Fixture):
    def test_import_is_added_once_and_custom_text_survives(self):
        path = self.write("CLAUDE.md", "# Team notes\n")
        setup.render_claude_import(str(self.root))
        text = path.read_text()
        self.assertTrue(text.startswith(setup.CLAUDE_BEGIN + "\n@AGENTS.md\n" + setup.CLAUDE_END + "\n\n"))
        self.assertTrue(text.endswith("# Team notes\n"))
        setup.render_claude_import(str(self.root))
        self.assertEqual(path.read_text(), text)

    def test_existing_import_is_untouched(self):
        path = self.write("CLAUDE.md", "Rules\n@AGENTS.md\n")
        setup.render_claude_import(str(self.root))
        self.assertEqual(path.read_text(), "Rules\n@AGENTS.md\n")

    def test_malformed_markers_fail(self):
        source = setup.CLAUDE_END + "\n" + setup.CLAUDE_BEGIN + "\n"
        path = self.write("CLAUDE.md", source)
        with self.assertRaises(RuntimeError):
            setup.render_claude_import(str(self.root))
        self.assertEqual(path.read_text(), source)


class PermissionsTest(Fixture):
    def install(self, source=None):
        path = self.root / "profile.json"
        if source is not None:
            path.write_text(source)
        output = io.StringIO()
        with mock.patch.object(permissions, "config_path", return_value=str(path)), \
                contextlib.redirect_stdout(output):
            permissions.install_profile()
        return path.read_text(), output.getvalue()

    def test_install_is_byte_stable(self):
        installed, output = self.install()
        self.assertIn("INSTALLED", output)
        profile = json.loads(installed)
        self.assertTrue(profile["sandbox"]["enabled"])
        self.assertIn("~/.cache/harness", profile["sandbox"]["filesystem"]["allowWrite"])
        self.assertIn("localhost", profile["sandbox"]["network"]["allowedDomains"])
        repeated, output = self.install()
        self.assertEqual(repeated, installed)
        self.assertIn("PRESENT", output)

    def test_explicit_choices_and_custom_entries_are_preserved(self):
        source = json.dumps({"model": "opus", "sandbox": {
            "enabled": False, "network": {"allowedDomains": ["example.com", "github.com"]},
        }})
        installed, output = self.install(source)
        self.assertIn("UPDATED", output)
        profile = json.loads(installed)
        self.assertEqual(profile["model"], "opus")
        self.assertFalse(profile["sandbox"]["enabled"])
        domains = profile["sandbox"]["network"]["allowedDomains"]
        self.assertEqual(domains[:2], ["example.com", "github.com"])
        self.assertEqual(domains.count("github.com"), 1)
        self.assertIn("~/.cache/harness", profile["sandbox"]["filesystem"]["allowWrite"])

    def test_invalid_profile_is_not_rewritten(self):
        for source in ('{"sandbox":', "[]", '{"sandbox": {"network": []}}'):
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    self.install(source)
                self.assertEqual((self.root / "profile.json").read_text(), source)


if __name__ == "__main__":
    unittest.main()
