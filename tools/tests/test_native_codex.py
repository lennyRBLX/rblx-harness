#!/usr/bin/env python3
"""Offline migration, dispatch, and rollback regressions."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared/gates"))
sys.path.insert(0, str(ROOT / "tools"))
import gatelib
from type_write import type_write
from data_write import data_write
from type_cache import type_cache


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


setup = load("native_setup", "setup_project.py")
harness = load("native_commands", "tools/harness.py")
permissions = load("native_permissions", "openai/setup/permissions_harness.py")
place_map = load("native_place_map", "tools/place_map/place_map.py")


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

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(ROOT / "tools/harness.py"),
                               "--root", str(self.root), *args], cwd=self.root,
                              capture_output=True, text=True)


class ConfigurationTest(Fixture):
    canonical = (ROOT / "openai/config/project.toml").read_text()

    def test_custom_values_comments_and_multiline_strings_survive(self):
        existing = '''# User settings
model = "chosen-model"
developer_instructions = """+[features]
tool_output_token_limit = 42
"""
[mcp_servers.custom]
command = "custom"
'''
        merged = gatelib.merge_project_codex_config(existing, self.canonical)
        self.assertTrue(merged.endswith(existing))
        actual = tomllib.loads(merged)
        self.assertEqual(actual.pop("tool_output_token_limit"), 6000)
        self.assertEqual(actual, tomllib.loads(existing))
        self.assertEqual(gatelib.merge_project_codex_config(merged, self.canonical), merged)

    def test_explicit_output_budget_and_model_preferences_survive(self):
        existing = 'tool_output_token_limit = 12000\nservice_tier = "fast"\n'
        self.assertEqual(gatelib.merge_project_codex_config(existing, self.canonical), existing)

    def test_invalid_toml_is_not_replaced(self):
        path = self.write(".codex/config.toml", '[broken\n')
        with self.assertRaises(ValueError):
            setup.copy_codex_support(str(self.root))
        self.assertEqual(path.read_text(), '[broken\n')

    def test_custom_agents_skills_and_config_survive_repeated_setup(self):
        agent = self.write(".codex/agents/custom.toml", 'name = "custom"\n')
        skill = self.write(".agents/skills/custom/SKILL.md", "custom instructions\n")
        config = self.write(".codex/config.toml", 'tool_output_token_limit = 9000\n')
        for _ in range(2):
            setup.copy_codex_support(str(self.root))
            self.assertEqual(agent.read_text(), 'name = "custom"\n')
            self.assertEqual(skill.read_text(), "custom instructions\n")
            self.assertEqual(config.read_text(), 'tool_output_token_limit = 9000\n')
            self.assertTrue(gatelib.required_codex_agents_status(str(self.root))[0])
            self.assertFalse((self.root / ".codex/hooks.json").exists())


class HookMigrationTest(Fixture):
    @staticmethod
    def legacy(event, prefix="", windows=False):
        path = prefix + "openai/hooks/adapter.py"
        suffix = "--host codex --event %s --hook-scope project" % event
        if windows:
            return 'powershell.exe -NoProfile -Command "$root = git rev-parse --show-toplevel; & py -3 -B (Join-Path $root \'%s\') %s"' % (path.replace("/", "\\"), suffix)
        return 'PYTHONDONTWRITEBYTECODE=1 python3 "$(git rev-parse --show-toplevel)/%s" %s' % (path, suffix)

    def test_removes_only_known_handlers_and_preserves_metadata(self):
        custom = {"type": "command", "command": "echo openai/hooks/adapter.py"}
        document = {"custom": "retained", "hooks": {"Stop": [{"matcher": "*", "hooks": [
            {"type": "command", "command": self.legacy("Stop"),
             "commandWindows": self.legacy("Stop", windows=True)}, custom,
        ]}], "SessionStart": [{"hooks": [custom]}]}}
        path = self.write(".codex/hooks.json", json.dumps(document))
        setup.remove_legacy_hooks(str(self.root))
        document["hooks"]["Stop"][0]["hooks"] = [custom]
        self.assertEqual(json.loads(path.read_text()), document)
        saved = path.read_bytes()
        setup.remove_legacy_hooks(str(self.root))
        self.assertEqual(path.read_bytes(), saved)

    def test_removes_empty_owned_file_for_checkout_and_project(self):
        for prefix in ("", "rblx-harness/"):
            with self.subTest(prefix=prefix):
                document = {"hooks": {event: [{"hooks": [{"type": "command",
                    "command": self.legacy(event, prefix),
                    "command_windows": self.legacy(event, prefix, windows=True)}]}]
                    for event in ("PreToolUse", "SubagentStart", "SubagentStop", "Stop")}}
                path = self.write(".codex/hooks.json", json.dumps(document))
                setup.remove_legacy_hooks(str(self.root))
                self.assertFalse(path.exists())

    def test_custom_wrapper_and_other_event_are_untouched(self):
        command = self.legacy("Stop")
        for handler in ({"type": "command", "command": command + " && custom"},
                        {"type": "command", "command": command, "commandWindows": "custom"}):
            self.assertFalse(setup.legacy_hook_handler(handler, "Stop"))
        self.assertFalse(setup.legacy_hook_handler({"type": "command", "command": command}, "PreToolUse"))

    def test_malformed_hook_file_is_untouched(self):
        for source in ('{"hooks":', '{"hooks":{"Stop":{}}}', '{"hooks":{"Stop":[{}]}}'):
            path = self.write(".codex/hooks.json", source)
            with self.assertRaises(RuntimeError):
                setup.remove_legacy_hooks(str(self.root))
            self.assertEqual(path.read_text(), source)

    def test_stale_adapter_commands_exit_without_retry_output(self):
        for event in ("PreToolUse", "Stop"):
            result = subprocess.run([sys.executable, "-B", str(ROOT / "openai/hooks/adapter.py"),
                                     "--host", "codex", "--event", event, "--hook-scope", "project"],
                                    input="old payload", capture_output=True, text=True)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))


class PermissionsTest(Fixture):
    def install(self, source):
        path = self.write("config.toml", source)
        with mock.patch.object(permissions, "config_path", return_value=str(path)), \
                contextlib.redirect_stdout(io.StringIO()):
            permissions.install_profile()
        return path.read_text()

    def test_profile_heading_inside_instructions_is_not_configuration(self):
        source = 'developer_instructions = """\n[permissions.Roblox]\nText\n"""\n'
        installed = self.install(source)
        self.assertTrue(installed.startswith(source))
        self.assertTrue(permissions.profile_present(installed))
        self.assertEqual(self.install(installed), installed)

    def test_explicit_grants_and_custom_settings_are_preserved(self):
        source = '''[permissions.Roblox]
extends = ":workspace"
[permissions.Roblox.filesystem.":workspace_roots"]
".agents" = "read"
"custom" = "write"
[permissions.Roblox.network]
enabled = false
'''
        installed = self.install(source)
        expected = tomllib.loads(source)
        expected["permissions"]["Roblox"]["filesystem"][":workspace_roots"][".codex"] = "write"
        self.assertEqual(tomllib.loads(installed), expected)
        self.assertEqual(self.install(installed), installed)

    def test_multiline_pseudo_section_survives_runtime_grant_upgrade(self):
        source = '''developer_instructions = """
[permissions.Roblox.filesystem.":workspace_roots"]
".agents" = "read"
"""
[permissions.Roblox]
extends = ":workspace"
[permissions."Roblox".filesystem.":workspace_roots"]
".git" = "write"
'''
        installed = self.install(source)
        before = tomllib.loads(source)
        after = tomllib.loads(installed)
        self.assertEqual(after["developer_instructions"], before["developer_instructions"])
        self.assertEqual(after["permissions"]["Roblox"]["filesystem"][":workspace_roots"][".agents"], "write")

    def test_invalid_permission_config_is_not_rewritten(self):
        with self.assertRaises(tomllib.TOMLDecodeError):
            self.install('[malformed\n')
        self.assertEqual((self.root / "config.toml").read_text(), '[malformed\n')


class GuidanceMigrationTest(Fixture):
    manifest = {"places": ["Lobby", "Match"], "gameplay": "Win matches", "assets": []}

    def render(self, **changes):
        setup.render_templates(str(self.root), dict(self.manifest, **changes))
        return (self.root / "AGENTS.md").read_text()

    def test_custom_guidance_and_readme_survive_managed_updates(self):
        self.write("AGENTS.md", "# Team rules\nKeep fixtures.\n")
        readme = self.write("README.md", "# Custom README\n")
        initial = self.render()
        self.assertIn("# Team rules\nKeep fixtures.", initial)
        self.assertEqual(initial.count(setup.GUIDANCE_BEGIN), 1)
        self.assertEqual(self.render(), initial)
        updated = self.render(gameplay="New loop")
        self.assertIn("Gameplay loop: New loop", updated)
        self.assertIn("# Team rules\nKeep fixtures.", updated)
        self.assertNotIn("Gameplay loop: Win matches", updated)
        self.assertEqual(readme.read_text(), "# Custom README\n")

    def test_exact_legacy_guidance_migrates_preserving_ids_and_suffix(self):
        legacy = (ROOT / "templates/AGENTS.legacy").read_text().replace(
            "{{SUMMARY}}", "Gameplay loop: Win matches\n\nServices: none\n\nControllers: none"
        ).replace("{{PLACES}}", "Lobby|1234\n- Match").replace("{{ASSETS}}", "none")
        self.write("AGENTS.md", legacy + "\n# User rules\nRetain this.\n")
        migrated = self.render()
        self.assertNotIn("Hooks enforce", migrated)
        self.assertIn("Lobby|1234", migrated)
        self.assertIn("# User rules\nRetain this.", migrated)
        self.assertEqual(self.render(), migrated)
        updated = self.render(places=["Lobby", "Arena"])
        self.assertIn("Lobby|1234\n- Arena", updated)
        self.assertNotIn("- Match", updated)

    def test_customized_legacy_guidance_is_preserved(self):
        custom = "## places\n\nLobby|2345\n\n# Team\nCustom rules.\n"
        self.write("AGENTS.md", custom)
        self.assertIn(custom.strip(), self.render())

    def test_place_mapping_changes_only_the_managed_section(self):
        custom = "## places\n\nArchive|9999\n\n# User notes\nKeep this.\n"
        path = self.write("AGENTS.md", custom)
        self.render()
        place_map.write_places_block(str(path), {"Lobby": 1234, "Match": 5678})
        self.assertTrue(path.read_text().endswith(custom))
        self.assertEqual(place_map.read_places_block(str(path)), {"Lobby": 1234, "Match": 5678})
        updated = self.render()
        self.assertIn("Lobby|1234\nMatch|5678", updated)
        self.assertTrue(updated.endswith(custom))

    def test_malformed_markers_do_not_overwrite_instructions(self):
        for source in (setup.GUIDANCE_BEGIN, setup.GUIDANCE_END,
                       setup.GUIDANCE_END + setup.GUIDANCE_BEGIN,
                       setup.GUIDANCE_BEGIN * 2 + setup.GUIDANCE_END):
            path = self.write("AGENTS.md", source)
            with self.assertRaises(RuntimeError):
                self.render()
            self.assertEqual(path.read_text(), source)


class DispatchTest(Fixture):
    def test_help_has_no_project_side_effects(self):
        for args in (("--help",), *((family, "--help") for family in harness.HELP)):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_literal_source_read_matches_backend_and_respects_limit(self):
        name = "literal $(never) [a]*.luau"
        self.write(name, "first line\nsecond line\n")
        args = ["--file", name, "--max-chars", "8", "--no-cache"]
        actual = self.run_cli("inspect", "read", *args)
        expected = subprocess.run([sys.executable, "-B", str(ROOT / "tools/context_pack.py"),
                                   "--root", str(self.root), "--max-chars", "8", "--no-cache",
                                   "read", "--file", name], capture_output=True, text=True)
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(actual.stdout, expected.stdout)
        self.assertFalse(json.loads(actual.stdout)["preview_complete"])
        self.assertEqual([p.name for p in self.root.iterdir()], [name])

    def test_unknown_action_and_duplicate_root_fail(self):
        for args in (("types", "unknown"), ("types", "read", "--root", str(self.root), "--project")):
            result = self.run_cli(*args)
            self.assertEqual(result.returncode, 2)
            self.assertIn("harness:", result.stderr)

    def test_project_scaffold_and_cache_action_arguments_reach_backend(self):
        result = self.run_cli("scaffold", "project", "inspect")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("places", json.loads(result.stdout))
        result = self.run_cli("types", "cache", "unknown")
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)

    def test_selected_checks_run_once_with_deduplicated_owned_files(self):
        first = self.write("src/a.luau", "return {}\n")
        second = self.write("src/b.lua", "return {}\n")
        self.write("src/readme.txt", "ignore")
        (self.root / "src/link.luau").symlink_to(first)
        with mock.patch.object(harness.subprocess, "run", side_effect=[
            subprocess.CompletedProcess([], 2), subprocess.CompletedProcess([], 3),
        ]) as run, contextlib.redirect_stdout(io.StringIO()):
            status = harness.check_source(["--only", "style,style,correctness", "src", "src/a.luau"], self.root)
        self.assertEqual(status, 3)
        self.assertEqual(run.call_count, 2)
        for call in run.call_args_list:
            args = call.args[0]
            self.assertEqual(args[-2:], [str(first), str(second)])
            self.assertNotIn("--fix", args)

    def test_source_selection_does_not_follow_dependency_links_or_escape(self):
        self.write("owned/a.luau", "return {}\n")
        (self.root / "linked").symlink_to(self.root / "owned", target_is_directory=True)
        for paths in (["linked"], ["linked/a.luau"], [str(self.root.parent)]):
            with self.assertRaises(ValueError):
                harness.source_files(self.root, paths)


class WriterInputTest(Fixture):
    def test_stdin_file_and_inline_requests_dispatch_same_operations(self):
        operations = [{"scope": "public", "action": "create", "owner": "Inventory", "type_name": "Item",
                       "declaration": "export type Item = { count: number }"}]
        request = json.dumps({"operations": operations})
        path = self.write("request file.json", request)
        variants = (["--request", request], ["--request", "-"], ["--request-file", str(path)],
                    ["--operation", json.dumps(operations[0])])
        for args in variants:
            with self.subTest(args=args), mock.patch.object(sys, "stdin", io.StringIO(request)), \
                    mock.patch.object(type_write, "execute", return_value=[]) as execute, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(type_write.main(["--root", str(self.root), "--session", "", *args]), 0)
                execute.assert_called_once_with(str(self.root), operations, "", None)

    def test_invalid_requests_fail_before_execution(self):
        for request in ('{"operations":', '[]', 'null', '{}'):
            with self.subTest(request=request), mock.patch.object(type_write, "execute") as execute, \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(type_write.main(["--request", request]), 2)
                execute.assert_not_called()
                self.assertIn("BLOCKED|TYPE8", output.getvalue())


class DataRollbackTest(Fixture):
    def replacements(self, existing=True):
        pairs = []
        for name in ("Default", "Typed", "Development"):
            source = self.write("staged/%s.luau" % name, "new " + name)
            target = self.root / (name + ".luau")
            if existing:
                target.write_text("old " + name)
            pairs.append((str(source), str(target)))
        return pairs

    def test_all_outputs_are_replaced_and_old_orig_is_preserved(self):
        pairs = self.replacements()
        old_backup = self.write("Default.luau.orig", "user backup")
        data_write.replace_files(pairs)
        for source, target in pairs:
            self.assertEqual(Path(target).read_text(), Path(source).read_text())
        self.assertEqual(old_backup.read_text(), "user backup")
        self.assertFalse(list(self.root.glob(".data_write_*")))

    def test_each_replacement_failure_restores_existing_or_new_files(self):
        replace = os.replace
        for existing in (False, True):
            for position in range(3):
                with self.subTest(existing=existing, position=position):
                    pairs = self.replacements(existing)
                    def fail(source, target):
                        if str(source).endswith("%d.new" % position):
                            raise OSError("injected replacement failure")
                        return replace(source, target)
                    with mock.patch.object(data_write.os, "replace", side_effect=fail), \
                            self.assertRaisesRegex(data_write.ReplacementError, "original files restored"):
                        data_write.replace_files(pairs)
                    for _, target in pairs:
                        if existing:
                            self.assertEqual(Path(target).read_text(), "old " + Path(target).stem)
                            Path(target).unlink()
                        else:
                            self.assertFalse(Path(target).exists())
                    self.assertFalse(list(self.root.glob(".data_write_*")))

    def test_recovery_failure_retains_original_backup(self):
        pairs = self.replacements()
        replace = os.replace
        def fail(source, target):
            if str(source).endswith(("2.new", "0.original")):
                raise OSError("injected failure")
            return replace(source, target)
        with mock.patch.object(data_write.os, "replace", side_effect=fail), \
                self.assertRaisesRegex(data_write.ReplacementError, "retained backups"):
            data_write.replace_files(pairs)
        backups = list(self.root.glob(".data_write_*/0.original"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "old Default")
        self.assertEqual(Path(pairs[1][1]).read_text(), "old Typed")
        self.assertEqual(Path(pairs[2][1]).read_text(), "old Development")


class TypeTransactionTest(Fixture):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(type_cache, "cache_path", return_value=str(self.root / "cache/index.json"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.first = self.write("shared/src/ReplicatedStorage/Types/Inventory.luau",
                                "export type Item = { count: number }\nreturn {}\n")
        self.operations = [
            {"scope": "public", "action": "update", "owner": "Inventory", "type_name": "Item",
             "declaration": "export type Item = { count: number, name: string }"},
            {"scope": "public", "action": "create", "owner": "Camera", "type_name": "State",
             "declaration": "export type State = { active: boolean }"},
        ]
        self.created = self.first.with_name("Camera.luau")

    @unittest.skipUnless(Path(type_write.LUAU_LSP).exists() and (ROOT / "tools/globalTypes.d.luau").exists(),
                         "bundled Luau analyzer or Roblox definitions unavailable")
    def test_batch_roundtrip_uses_real_type_analyzer_and_leaves_no_receipts(self):
        outcomes = type_write.execute(str(self.root), self.operations)
        self.assertEqual([item["outcome"] for item in outcomes], ["updated", "created"])
        self.assertIn("name: string", self.first.read_text())
        self.assertIn("active: boolean", self.created.read_text())
        self.assertEqual(type_cache.verify(str(self.root))[0], "current")
        self.assertFalse(Path(type_cache.journal_path(str(self.root))).exists())
        self.assertFalse((self.root / "gates").exists())

    def test_analysis_failure_rolls_back_modified_new_and_cached_files(self):
        type_cache.ensure(str(self.root))
        original = self.first.read_bytes()
        original_cache = Path(type_cache.cache_path(str(self.root))).read_bytes()
        with mock.patch.object(type_write, "_analyze_result", side_effect=type_write.WriteError("TYPE1", "injected")), \
                self.assertRaises(type_write.WriteError):
            type_write.execute(str(self.root), self.operations)
        self.assertEqual(self.first.read_bytes(), original)
        self.assertFalse(self.created.exists())
        self.assertEqual(Path(type_cache.cache_path(str(self.root))).read_bytes(), original_cache)
        self.assertFalse(Path(type_cache.journal_path(str(self.root))).exists())

    def test_failed_new_file_removal_retains_recoverable_journal(self):
        type_cache.ensure(str(self.root))
        type_cache.write_journal(str(self.root), {str(self.created): None})
        self.created.write_text("new source")
        remove = os.remove
        def fail(path):
            if path == str(self.created):
                raise PermissionError("injected")
            return remove(path)
        with mock.patch.object(type_cache.os, "remove", side_effect=fail), \
                self.assertRaises(type_cache.CacheError):
            type_cache.recover(str(self.root))
        self.assertTrue(Path(type_cache.journal_path(str(self.root))).exists())
        self.assertTrue(type_cache.recover(str(self.root)))
        self.assertFalse(self.created.exists())


if __name__ == "__main__":
    unittest.main()
