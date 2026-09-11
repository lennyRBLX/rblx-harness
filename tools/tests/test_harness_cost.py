#!/usr/bin/env python3
"""Offline equivalence and invalidation checks for harness cost reductions."""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared/gates"))
sys.path.insert(0, str(ROOT / "tools"))

from type_cache import type_cache
from type_core import core


class ParsedTypeCacheTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "project"
        self.root.mkdir()
        self.cache = Path(self.temporary.name) / "cache/index.json"
        patcher = mock.patch.object(type_cache, "cache_path", return_value=str(self.cache))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.first = self.write("shared/src/ServerScriptService/Services/Inventory.luau",
                                "export type Item = { count: number }\nreturn {}\n")
        self.second = self.write("shared/src/ReplicatedStorage/Types/Camera.luau",
                                 "export type State = { active: boolean }\n")

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def ensure(self):
        return type_cache.ensure(str(self.root))

    def assert_canonical(self, index):
        self.assertEqual(index, core.build_index(str(self.root)))

    def test_warm_cache_skips_parsing_and_preserves_current_index(self):
        status, original = self.ensure()
        self.assertEqual(status, "rebuilt")
        with mock.patch.object(core, "parse_declarations", side_effect=AssertionError("reparsed unchanged source")):
            status, current = self.ensure()
            self.assertEqual(type_cache.verify(str(self.root))[0], "current")
        self.assertEqual(status, "current")
        self.assertEqual(current, original)
        self.assert_canonical(current)

    def test_same_mtime_edit_reparses_only_changed_content(self):
        self.ensure()
        stat = self.first.stat()
        self.first.write_text(self.first.read_text().replace("number", "string"))
        os.utime(self.first, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        with mock.patch.object(core, "parse_declarations", wraps=core.parse_declarations) as parse:
            status, current = self.ensure()
        self.assertEqual(status, "rebuilt")
        self.assertEqual(parse.call_count, 1)
        self.assert_canonical(current)

    def test_discovery_deletion_and_owner_qualification_remain_current(self):
        self.ensure()
        duplicate = self.write("places/Lobby/src/ServerScriptService/Services/Inventory.luau", self.first.read_text())
        _, current = self.ensure()
        self.assert_canonical(current)
        _, warmed = self.ensure()
        self.assertEqual(current, warmed)
        duplicate.unlink()
        self.second.unlink()
        _, current = self.ensure()
        self.assert_canonical(current)
        self.assertEqual(current["definitions"][0]["qualified"], "Inventory.Item")
        parsed = type_cache.read_parsed_sources(str(self.root), type_cache.parser_revision())
        self.assertEqual(len(parsed), 1)

    def test_project_map_changes_are_checked_without_reparsing(self):
        self.write("default.project.json", '{"tree":{}}')
        _, original = self.ensure()
        self.write("default.project.json", '{"tree":{"name":"Changed"}}')
        with mock.patch.object(core, "parse_declarations", side_effect=AssertionError("reparsed unchanged source")):
            status, current = self.ensure()
        self.assertEqual(status, "rebuilt")
        self.assertNotEqual(current["source_map_fingerprint"], original["source_map_fingerprint"])
        self.assert_canonical(current)

    def test_parser_change_and_damaged_memo_rebuild(self):
        self.ensure()
        with mock.patch.object(type_cache, "parser_revision", return_value="updated-parser"), \
                mock.patch.object(core, "parse_declarations", wraps=core.parse_declarations) as parse:
            _, current = self.ensure()
        self.assertEqual(parse.call_count, 2)
        self.assert_canonical(current)
        self.ensure()
        sidecar = Path(str(self.cache) + ".parsed")
        saved = json.loads(sidecar.read_text())
        saved["entries"][str(self.first.relative_to(self.root))]["definitions"][0]["declaration"] = "wrong"
        sidecar.write_text(json.dumps(saved))
        with mock.patch.object(core, "parse_declarations", wraps=core.parse_declarations) as parse:
            _, current = self.ensure()
        self.assertEqual(parse.call_count, 2)
        self.assert_canonical(current)

    def test_corrupt_public_cache_is_still_detected_and_repaired(self):
        _, original = self.ensure()
        damaged = json.loads(self.cache.read_text())
        damaged["definitions"][0]["declaration"] = "wrong"
        self.cache.write_text(json.dumps(damaged))
        self.assertEqual(type_cache.verify(str(self.root))[0], "stale")
        status, current = self.ensure()
        self.assertEqual(status, "rebuilt")
        self.assertEqual(current, original)

    def test_overlay_staging_and_recovery_do_not_publish_stale_types(self):
        _, original = self.ensure()
        before = self.first.read_text()
        changed = before.replace("number", "string")
        overlay = {str(self.first): changed, str(self.second): None}
        staged, current = type_cache.stage(str(self.root), overlay)
        self.assertEqual(current, core.build_index(str(self.root), overlay))
        self.assertEqual(self.first.read_text(), before)
        self.assertEqual(type_cache.read(str(self.root)), original)
        os.unlink(staged)
        type_cache.write_journal(str(self.root), {str(self.first): before})
        self.first.write_text(changed)
        # Populate a memo for the changed source, then restore the journal.
        parsed = type_cache.read_parsed_sources(str(self.root), type_cache.parser_revision())
        core.build_index(str(self.root), parsed_sources=parsed)
        type_cache.write_parsed_sources(str(self.root), type_cache.parser_revision(), parsed)
        _, recovered = self.ensure()
        self.assertEqual(recovered, original)
        self.assertEqual(self.first.read_text(), before)
        self.assertFalse(Path(type_cache.journal_path(str(self.root))).exists())

    def test_data_accessors_and_external_symlink_targets_are_rechecked(self):
        folder = "shared/src/ServerScriptService/Services/PlayerData/"
        self.write(folder + "Default.luau", "return {}")
        self.write(folder + "Development.luau", "return {}")
        typed = self.write(folder + "Typed.luau", "function m.read(key: string): number\nend\n")
        self.ensure()
        typed.write_text("function m.read(key: string): string\nend\n")
        _, current = self.ensure()
        self.assert_canonical(current)
        self.assertEqual(current["accessors"][0]["signature"], "read(key: string): string")
        target = Path(self.temporary.name) / "External.luau"
        target.write_text("export type Remote = number\n")
        self.second.unlink()
        self.second.symlink_to(target)
        self.ensure()
        target.write_text("export type Remote = string\n")
        _, current = self.ensure()
        self.assert_canonical(current)
        self.assertTrue(any(row["declaration"] == "export type Remote = string" for row in current["definitions"]))


if __name__ == "__main__":
    unittest.main()
