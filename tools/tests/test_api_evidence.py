#!/usr/bin/env python3
"""Offline regressions for API evidence and restrictions.

Run with: python3 tools/tests/test_api_evidence.py
This fixture uses only temporary files and remains as a regression test; it
does not create a Studio diagnostic and has no human-run cleanup step.
"""

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
GATES = os.path.join(ROOT, "shared", "gates")
if GATES not in sys.path:
    sys.path.insert(0, GATES)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


api_dump = load_module("api_dump_evidence_test", os.path.join(ROOT, "tools", "api_dump", "api_dump.py"))


def prop(name, security="absent", capabilities="absent", tags=None, thread_safety="ReadSafe"):
    member = {
        "MemberType": "Property",
        "Name": name,
        "ThreadSafety": thread_safety,
        "ValueType": {"Category": "Primitive", "Name": "string"},
    }
    if security != "absent":
        member["Security"] = security
    if capabilities != "absent":
        member["Capabilities"] = capabilities
    if tags is not None:
        member["Tags"] = tags
    return member


def function(name, security="absent", capabilities="absent", tags=None, thread_safety="Unsafe"):
    member = {
        "MemberType": "Function",
        "Name": name,
        "ThreadSafety": thread_safety,
        "Parameters": [],
        "ReturnType": {"Category": "Primitive", "Name": "void"},
    }
    if security != "absent":
        member["Security"] = security
    if capabilities != "absent":
        member["Capabilities"] = capabilities
    if tags is not None:
        member["Tags"] = tags
    return member


class ApiEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = self.temporary.name
        self.cache = os.path.join(self.root, "cache")
        self.docs = os.path.join(self.cache, "creator-docs")
        self.content = os.path.join(self.docs, "content", "en-us")
        self.engine = os.path.join(self.content, "reference", "engine")
        self.classes = os.path.join(self.engine, "classes")
        os.makedirs(self.classes)

        self.dump_path = os.path.join(self.cache, "API-Dump.json")
        self.refresh_path = os.path.join(self.cache, "corpus-refresh.json")
        self.find_index_path = os.path.join(self.cache, "find_index.json")
        self.behavior_path = os.path.join(self.root, "behavior.json")
        self.overlay_path = os.path.join(self.root, "house_overlay.txt")
        self.docs_revision = "docs-current"

        self.dump = {
            "Version": 1,
            "Classes": [
                {
                    "Name": "Instance",
                    "Superclass": "<<<ROOT>>>",
                    "Tags": ["NotCreatable"],
                    "Capabilities": ["BaseClassCapability"],
                    "Members": [
                        prop(
                            "InheritedRestricted",
                            {"Read": "LocalUserSecurity", "Write": "RobloxScriptSecurity"},
                            {"Read": ["BaseRead"], "Write": ["BaseWrite"]},
                            ["Hidden"],
                        ),
                        prop("InheritedOpen", {"Read": "None", "Write": "None"}),
                    ],
                },
                {
                    "Name": "World",
                    "Superclass": "Instance",
                    "Tags": ["Service", "NotReplicated"],
                    "Capabilities": ["WorldClassCapability"],
                    "Members": [
                        prop("Split", {"Read": "None", "Write": "PluginSecurity"}),
                        prop(
                            "CapabilityOnly",
                            {"Read": "None", "Write": "None"},
                            {"Read": ["Basic"], "Write": ["PluginOrOpenCloud"]},
                        ),
                        prop(
                            "Tagged",
                            {"Read": "None", "Write": "None"},
                            {"Read": ["Basic"], "Write": ["Basic", "Input"]},
                            ["NotReplicated", "CustomLuaState", "Hidden"],
                        ),
                        prop(
                            "NotScriptableThing",
                            {"Read": "None", "Write": "None"},
                            tags=["NotScriptable"],
                        ),
                        prop("MissingMeta"),
                        prop("Conflict", {"Read": "None", "Write": "PluginSecurity"}),
                    ],
                },
                {
                    "Name": "ScriptEditorService",
                    "Superclass": "Instance",
                    "Tags": ["Service", "NotCreatable"],
                    "Capabilities": ["StudioPlugin"],
                    "Members": [
                        function("UpdateSourceAsync", "PluginSecurity", ["StudioPlugin"]),
                    ],
                },
            ],
            "Enums": [],
        }
        self.write_json(self.dump_path, self.dump)
        with open(self.dump_path, "rb") as handle:
            self.dump_sha = hashlib.sha256(handle.read()).hexdigest()
        self.write_json(
            self.refresh_path,
            {
                "refreshed_at": 123,
                "api_dump_sha256": "stale-dump-sha",
                "creator_docs_revision": "stale-docs-revision",
            },
        )
        self.write_json(
            self.behavior_path,
            {
                "records": [
                    {
                        "id": "stale-split-behavior",
                        "topics": ["workspace-timing"],
                        "apis": ["World.Split"],
                        "creator_docs_revision": "docs-reviewed-earlier",
                        "finding": "A successful write does not establish an effect.",
                        "sources": [
                            {
                                "kind": "creator-docs",
                                "path": "reference/engine/classes/World.yaml",
                                "sha256": "reviewed-source-sha",
                                "decisive": "Configure Split in Studio.",
                            }
                        ],
                        "runtime": {
                            "World.Split": {
                                "runtime_assignment": "supported",
                                "effective_when": "immediate",
                            }
                        },
                    },
                    {
                        "id": "changed-reviewed-source",
                        "topics": ["source-freshness"],
                        "apis": [],
                        "creator_docs_revision": "docs-current",
                        "finding": "The reviewed source content changed.",
                        "sources": [
                            {
                                "kind": "creator-docs",
                                "path": "reference/engine/classes/World.yaml",
                                "sha256": "reviewed-before-change",
                                "decisive": "Previously reviewed text.",
                            }
                        ],
                    },
                    {
                        "id": "missing-reviewed-source",
                        "topics": ["source-freshness"],
                        "apis": [],
                        "creator_docs_revision": "docs-current",
                        "finding": "The reviewed source content is absent.",
                        "sources": [
                            {
                                "kind": "creator-docs",
                                "path": "reference/engine/classes/Removed.yaml",
                                "sha256": "reviewed-before-removal",
                                "decisive": "Previously reviewed text.",
                            }
                        ],
                    }
                ]
            },
        )
        self.write_text(self.overlay_path, "")
        self.write_text(
            os.path.join(self.classes, "World.yaml"),
            """name: World
summary: World summary
description: World is restricted to callers with WorldClassCapability.
capabilities:
  - WorldClassCapability
tags:
  - Service
  - NotReplicated
properties:
  - name: World.Split
    summary: Split summary
    description: Configure Split in Studio.
    security:
      read: None
      write: PluginSecurity
    thread_safety: ReadSafe
  - name: World.Conflict
    summary: Conflict summary
    description: Conflicting source metadata is deliberate in this fixture.
    security:
      read: None
      write: RobloxScriptSecurity
    thread_safety: ReadSafe
""",
        )
        self.write_text(
            os.path.join(self.classes, "Instance.yaml"),
            """name: Instance
summary: Instance summary
description: Instance is restricted to callers with BaseClassCapability.
capabilities:
  - BaseClassCapability
tags:
  - NotCreatable
properties:
  - name: Instance.InheritedRestricted
    summary: Inherited restricted summary
    description: This property has separate read and write restrictions.
    security:
      read: LocalUserSecurity
      write: RobloxScriptSecurity
    capabilities:
      read:
        - BaseRead
      write:
        - BaseWrite
    tags:
      - Hidden
    thread_safety: ReadSafe
""",
        )

        self.originals = {}
        replacements = {
            "DUMP_PATH": self.dump_path,
            "DOCS_ROOT": self.docs,
            "CONTENT": self.content,
            "ENGINE": self.engine,
            "REFRESH_PATH": self.refresh_path,
            "CACHE": self.cache,
            "DOCS_INDEX": os.path.join(self.cache, "docs_index.json"),
            "FIND_INDEX": self.find_index_path,
            "BEHAVIOR_PATH": self.behavior_path,
            "OVERLAY_PATH": self.overlay_path,
            "docs_revision": lambda: self.docs_revision,
        }
        for name, value in replacements.items():
            self.originals[name] = getattr(api_dump, name)
            setattr(api_dump, name, value)
        api_dump._dump = None
        api_dump._yaml_cache.clear()

    def tearDown(self):
        for name, value in self.originals.items():
            setattr(api_dump, name, value)
        api_dump._dump = None
        api_dump._yaml_cache.clear()
        self.temporary.cleanup()

    @staticmethod
    def write_json(path, value):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(value, handle)

    @staticmethod
    def write_text(path, value):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(value)

    def records(self, *args):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            result = api_dump.main(list(args))
        self.assertIn(result, (None, 0))
        return [json.loads(line) for line in stream.getvalue().splitlines() if line]

    def access(self, member):
        return self.access_spec("World." + member)

    def access_spec(self, spec):
        records = self.records("access", spec)
        self.assertEqual(records[0]["record"], "class-context")
        self.assertEqual(records[1]["record"], "access")
        return records[0], records[1]

    @staticmethod
    def expand_batch(batch):
        def expand(value):
            if isinstance(value, list):
                return [expand(item) for item in value]
            if isinstance(value, dict):
                if "$ref" in value:
                    value = {**batch["shared"][value["$ref"]],
                             **{key: item for key, item in value.items() if key != "$ref"}}
                return {key: expand(item) for key, item in value.items()}
            return value
        return expand(batch["results"])

    def test_batch_preserves_complete_single_query_evidence(self):
        queries = [("access", "World.Split"), ("access", "World.InheritedRestricted"),
                   ("access", "Instance.InheritedRestricted"), ("inventory", "World"),
                   ("behavior", "stale-split-behavior"), ("behavior", "source-freshness"),
                   ("access", "World.Unknown"), ("behavior", "unknown-behavior")]
        expected = [self.records(*query) for query in queries]
        with mock.patch.object(api_dump, "corpus_provenance", wraps=api_dump.corpus_provenance) as provenance:
            batch = self.records("batch", *(part for query in queries for part in query))[0]
        self.assertEqual(provenance.call_count, 1)
        self.assertEqual(batch["schema"], "roblox-evidence-batch-v1")
        self.assertEqual([row["records"] for row in self.expand_batch(batch)], expected)
        self.assertEqual([(row["verb"], row["query"]) for row in batch["results"]], queries)
        self.assertEqual(sum(key.startswith("provenance-") for key in batch["shared"]), 1)
        self.assertEqual(sum(key.startswith("class-") for key in batch["shared"]), 2)
        shared_behaviors = [row for key, row in batch["shared"].items() if key.startswith("behavior-")]
        self.assertEqual(sum(row["id"] == "stale-split-behavior" for row in shared_behaviors), 1)

    def test_batch_rechecks_source_revisions_on_next_invocation(self):
        first = self.records("batch", "access", "World.Split")[0]
        self.docs_revision = "docs-updated"
        second = self.records("batch", "access", "World.Split")[0]
        first_source = self.expand_batch(first)[0]["records"][0]["sources"]
        second_source = self.expand_batch(second)[0]["records"][0]["sources"]
        self.assertEqual(first_source["creator_docs_revision"], "docs-current")
        self.assertEqual(second_source["creator_docs_revision"], "docs-updated")

    def test_batch_invalid_requests_fail_before_corpus_lookup(self):
        for args in ([], ["access"], ["--sync", "World"], ["access", "World", "bad"]):
            with self.subTest(args=args), mock.patch.object(api_dump, "corpus_provenance") as provenance:
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    result = api_dump.main(["batch", *args])
                self.assertEqual(result, 2)
                self.assertEqual(json.loads(stream.getvalue())["record"], "miss")
                provenance.assert_not_called()

    def test_restricted_member_preserves_operations_inheritance_and_class_context(self):
        context, record = self.access("InheritedRestricted")
        self.assertEqual(record["requested_class"], "World")
        self.assertEqual(record["declaring_class"], "Instance")
        self.assertEqual(record["operations"]["read"]["security"], "LocalUserSecurity")
        self.assertEqual(record["operations"]["write"]["security"], "RobloxScriptSecurity")
        self.assertEqual(record["operations"]["read"]["capabilities"], ["BaseRead"])
        self.assertEqual(record["operations"]["write"]["capabilities"], ["BaseWrite"])
        self.assertIn("requires LocalUserSecurity", record["operations"]["read"]["ordinary_game_denial_basis"])
        self.assertIn("requires RobloxScriptSecurity", record["operations"]["write"]["ordinary_game_denial_basis"])

        classes = {item["name"]: item for item in context["classes"]}
        self.assertEqual(set(classes), {"World", "Instance"})
        self.assertEqual(classes["World"]["capabilities"], ["WorldClassCapability"])
        self.assertIn("WorldClassCapability", classes["World"]["documentation"]["description"])
        self.assertEqual(classes["Instance"]["capabilities"], ["BaseClassCapability"])
        self.assertIn("BaseClassCapability", classes["Instance"]["documentation"]["description"])

    def test_operation_specific_restrictions_and_not_scriptable_are_visible(self):
        _, split = self.access("Split")
        self.assertEqual(split["operations"]["read"]["security"], "None")
        self.assertEqual(split["operations"]["write"]["security"], "PluginSecurity")
        self.assertEqual(split["operations"]["read"]["contexts"]["game-server"], "unknown")
        self.assertEqual(split["operations"]["write"]["contexts"]["game-server"], "denied")

        _, capability = self.access("CapabilityOnly")
        self.assertEqual(capability["operations"]["read"]["capabilities"], ["Basic"])
        self.assertEqual(capability["operations"]["write"]["capabilities"], ["PluginOrOpenCloud"])
        self.assertEqual(capability["operations"]["read"]["security"], "None")
        self.assertEqual(capability["operations"]["write"]["security"], "None")

        _, blocked = self.access("NotScriptableThing")
        self.assertEqual(blocked["tags"], ["NotScriptable"])
        self.assertEqual(blocked["operations"]["read"]["security"], "None")
        self.assertEqual(blocked["operations"]["write"]["security"], "None")
        self.assertEqual(blocked["operations"]["read"]["contexts"]["game-client"], "denied")
        self.assertIn("NotScriptable", blocked["operations"]["write"]["ordinary_game_denial_basis"])

    def test_restricted_function_call_is_returned_with_class_restrictions(self):
        context, record = self.access_spec("ScriptEditorService.UpdateSourceAsync")
        self.assertEqual(record["kind"], "Function")
        self.assertEqual(set(record["operations"]), {"call"})
        self.assertEqual(record["operations"]["call"]["security"], "PluginSecurity")
        self.assertEqual(record["operations"]["call"]["capabilities"], ["StudioPlugin"])
        self.assertEqual(record["operations"]["call"]["contexts"]["game-server"], "denied")
        requested = context["classes"][0]
        self.assertEqual(requested["name"], "ScriptEditorService")
        self.assertEqual(requested["capabilities"], ["StudioPlugin"])
        self.assertEqual(requested["documentation"]["status"], "missing")

    def test_all_dump_tags_and_missing_metadata_stay_explicit(self):
        _, tagged = self.access("Tagged")
        self.assertEqual(tagged["tags"], ["NotReplicated", "CustomLuaState", "Hidden"])
        self.assertEqual(tagged["api_dump_member"]["Tags"], tagged["tags"])

        _, missing = self.access("MissingMeta")
        self.assertEqual(missing["documentation"]["status"], "missing")
        self.assertEqual(missing["documentation"]["description"], "unknown")
        self.assertNotEqual(missing["documentation"]["sha256"], "unknown")
        for operation in ("read", "write"):
            self.assertEqual(missing["operations"][operation]["security"], "unknown")
            self.assertEqual(missing["operations"][operation]["capabilities"], "unknown")
            self.assertTrue(all(value == "unknown" for value in missing["operations"][operation]["contexts"].values()))

    def test_provenance_and_behavior_revision_mismatches_are_flagged(self):
        _, split = self.access("Split")
        self.assertEqual(split["behavior"][0]["revision_status"], "recheck-required")
        self.assertEqual(split["behavior"][0]["sources"][0]["sha256"], "reviewed-source-sha")
        self.assertEqual(split["behavior"][0]["sources"][0]["decisive"], "Configure Split in Studio.")
        self.assertEqual(split["runtime"]["runtime_assignment"], "unknown")
        self.assertEqual(split["runtime"]["effective_when"], "unknown")
        self.assertEqual(split["runtime"]["replication"], "unknown")

        behavior = self.records("behavior", "stale-split-behavior")[0]
        self.assertEqual(behavior["record"], "behavior")
        self.assertEqual(behavior["revision_status"], "recheck-required")
        self.assertEqual(behavior["sources"][0]["sha256"], "reviewed-source-sha")
        self.assertEqual(behavior["sources"][0]["decisive"], "Configure Split in Studio.")
        self.assertEqual(behavior["provenance"]["cache_manifest_match"], "mismatch")
        self.assertEqual(behavior["provenance"]["api_dump_sha256"], self.dump_sha)
        self.assertEqual(behavior["provenance"]["creator_docs_revision"], self.docs_revision)
        self.assertEqual(behavior["provenance"]["engine_docs_alignment"], "unknown")

    def test_missing_entire_docs_tree_remains_unknown(self):
        original_content = api_dump.CONTENT
        original_engine = api_dump.ENGINE
        original_docs_revision = api_dump.docs_revision
        api_dump.CONTENT = os.path.join(self.root, "missing-docs", "content", "en-us")
        api_dump.ENGINE = os.path.join(api_dump.CONTENT, "reference", "engine")
        api_dump.docs_revision = lambda: "unknown"
        api_dump._yaml_cache.clear()
        try:
            context, record = self.access("Split")
        finally:
            api_dump.CONTENT = original_content
            api_dump.ENGINE = original_engine
            api_dump.docs_revision = original_docs_revision
            api_dump._yaml_cache.clear()

        self.assertEqual(context["sources"]["creator_docs_revision"], "unknown")
        for class_record in context["classes"]:
            self.assertEqual(class_record["documentation"]["status"], "missing")
            self.assertEqual(class_record["documentation"]["description"], "unknown")
            self.assertEqual(class_record["documentation"]["sha256"], "unknown")
        self.assertEqual(record["documentation"]["status"], "missing")
        self.assertEqual(record["documentation"]["description"], "unknown")
        self.assertEqual(record["documentation"]["sha256"], "unknown")

    def test_changed_and_missing_reviewed_sources_require_recheck(self):
        changed = self.records("behavior", "changed-reviewed-source")[0]
        self.assertEqual(changed["source_checks"], [
            {"path": "reference/engine/classes/World.yaml", "status": "mismatch"}
        ])
        self.assertEqual(changed["revision_status"], "recheck-required")
        self.assertEqual(changed["evidence_status"], "recheck-required")
        self.assertEqual(changed["sources"][0]["sha256"], "reviewed-before-change")

        missing = self.records("behavior", "missing-reviewed-source")[0]
        self.assertEqual(missing["source_checks"], [
            {"path": "reference/engine/classes/Removed.yaml", "status": "missing"}
        ])
        self.assertEqual(missing["revision_status"], "recheck-required")
        self.assertEqual(missing["evidence_status"], "recheck-required")
        self.assertEqual(missing["sources"][0]["sha256"], "reviewed-before-removal")

    def test_docs_key_casing_is_normalized_and_real_conflict_is_preserved(self):
        _, split = self.access("Split")
        security_differences = [row for row in split["metadata_differences"] if row["field"] == "security"]
        self.assertEqual(security_differences, [])

        _, conflict = self.access("Conflict")
        security_differences = [row for row in conflict["metadata_differences"] if row["field"] == "security"]
        self.assertEqual(len(security_differences), 1)
        difference = security_differences[0]
        self.assertEqual(difference["status"], "conflict")
        self.assertEqual(difference["api_dump"]["Write"], "PluginSecurity")
        self.assertEqual(difference["creator_docs"]["write"], "RobloxScriptSecurity")
        self.assertIn("do not choose permissive evidence", difference["next"])

    def test_inventory_returns_all_direct_and_inherited_properties(self):
        records = self.records("inventory", "World")
        self.assertEqual(records[0]["record"], "class-context")
        members = {record["member"]: record for record in records[1:]}
        self.assertEqual(
            set(members),
            {
                "Split",
                "CapabilityOnly",
                "Tagged",
                "NotScriptableThing",
                "MissingMeta",
                "Conflict",
                "InheritedRestricted",
                "InheritedOpen",
            },
        )
        self.assertEqual(members["InheritedRestricted"]["declaring_class"], "Instance")
        self.assertEqual(members["InheritedRestricted"]["requested_class"], "World")
        self.assertEqual(members["InheritedRestricted"]["operations"]["read"]["security"], "LocalUserSecurity")

    def test_behavior_miss_is_scoped_and_does_not_claim_access(self):
        records = self.records("behavior", "unknown-behavior")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["record"], "miss")
        self.assertEqual(records[0]["query"], "unknown-behavior")
        self.assertIn("research the exact context", records[0]["next"])
        self.assertNotIn("operations", records[0])

    def test_legacy_member_fields_remain_in_the_same_positions(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            api_dump.main(["props", "World", "--all"])
        lines = stream.getvalue().splitlines()
        self.assertEqual(len(lines[0].split("|")), 5)
        records = {line.split("|", 1)[0]: line.split("|") for line in lines[1:]}
        self.assertTrue(records)
        for fields in records.values():
            self.assertEqual(len(fields), 6)
        split = records[".Split"]
        self.assertEqual(split[0], ".Split")
        self.assertEqual(split[1], "string")
        self.assertEqual(split[2], "ReadSafe")
        self.assertEqual(split[3], "void")
        self.assertEqual(split[4], "void")
        self.assertEqual(split[5], "Split summary")

    def output(self, *args):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            result = api_dump.main(list(args))
        return result, stream.getvalue()

    def current_stamp(self):
        return {"api_dump_sha256": self.dump_sha, "creator_docs_revision": self.docs_revision}

    def write_current_manifest(self):
        self.write_json(self.refresh_path, {"refreshed_at": 123, **self.current_stamp()})

    def test_find_uses_matching_index_and_parses_only_printed_hits(self):
        self.write_current_manifest()
        _, live = self.output("find", "split", "--all")
        self.assertIn("World.Split|", live)
        api_dump._yaml_cache.clear()
        api_dump.install_find_index(api_dump.build_find_index(self.current_stamp()))
        api_dump._yaml_cache.clear()
        self.assertIsNotNone(api_dump.installed_find_index())
        _, indexed = self.output("find", "split", "--all")
        self.assertEqual(indexed, live)
        self.assertEqual(list(api_dump._yaml_cache), [os.path.join(self.classes, "World.yaml")])

    def test_find_parses_live_when_index_does_not_match_manifest(self):
        self.write_current_manifest()
        _, live = self.output("find", "split", "--all")
        bogus = api_dump.build_find_index(dict(self.current_stamp(), creator_docs_revision="older-docs"))
        bogus["classes"]["World"]["members"]["Split"] = "unrelated"
        api_dump.install_find_index(bogus)
        self.assertIsNone(api_dump.installed_find_index())
        _, result = self.output("find", "split", "--all")
        self.assertEqual(result, live)

    def test_find_installs_an_absent_index(self):
        self.write_current_manifest()
        self.assertFalse(os.path.exists(self.find_index_path))
        _, first = self.output("find", "split", "--all")
        index = api_dump.installed_find_index()
        self.assertIsNotNone(index)
        self.assertEqual(index["api_dump_sha256"], self.dump_sha)
        api_dump._yaml_cache.clear()
        _, second = self.output("find", "split", "--all")
        self.assertEqual(second, first)
        self.assertEqual(list(api_dump._yaml_cache), [os.path.join(self.classes, "World.yaml")])

    def test_find_leaves_a_mismatched_index_for_sync(self):
        self.write_current_manifest()
        stale = api_dump.build_find_index(dict(self.current_stamp(), creator_docs_revision="older-docs"))
        api_dump.install_find_index(stale)
        with open(self.find_index_path, "rb") as handle:
            before = handle.read()
        self.output("find", "split", "--all")
        with open(self.find_index_path, "rb") as handle:
            self.assertEqual(handle.read(), before)

    def test_find_succeeds_when_the_index_cannot_be_written(self):
        self.write_current_manifest()
        _, live = self.output("find", "split", "--all")
        os.remove(self.find_index_path)
        with mock.patch.object(api_dump.os, "replace", side_effect=PermissionError("read-only")):
            result, out = self.output("find", "split", "--all")
        self.assertIn(result, (None, 0))
        self.assertEqual(out, live)
        self.assertEqual(os.listdir(self.cache).count("find_index.json"), 0)
        self.assertFalse([name for name in os.listdir(self.cache) if name.endswith(".tmp")])

    def sync_output(self, urlopen):
        os.makedirs(os.path.join(self.docs, ".git"), exist_ok=True)
        completed = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(api_dump.gatelib, "corpus_status", return_value=("stale", "old")), \
                mock.patch.object(api_dump.gatelib, "corpus_assets_error", return_value=""), \
                mock.patch.object(api_dump.urllib.request, "urlopen", urlopen), \
                mock.patch.object(api_dump.subprocess, "run", return_value=completed):
            return self.output("--sync")

    def test_stale_sync_deletes_find_index_then_rebuilds_it(self):
        bogus = {"schema": api_dump.FIND_INDEX_SCHEMA, "api_dump_sha256": "old", "creator_docs_revision": "old",
                 "classes": {"World": {"summary": "stale", "members": {}}}, "enums": {}}
        self.write_json(self.find_index_path, bogus)
        with open(self.dump_path, "rb") as handle:
            data = handle.read()
        result, out = self.sync_output(mock.Mock(return_value=io.BytesIO(data)))
        self.assertEqual(result, 0)
        lines = [line.split("|", 2)[0] + "|" + line.split("|", 2)[1] for line in out.splitlines()]
        self.assertLess(lines.index("find-index|deleted"), lines.index("dump|synced"))
        self.assertLess(lines.index("find-index|rebuilt"), lines.index("refresh|successful"))
        index = api_dump.installed_find_index()
        self.assertIsNotNone(index)
        self.assertEqual(index["api_dump_sha256"], self.dump_sha)
        self.assertEqual(index["classes"]["World"]["summary"], "World summary")
        self.assertEqual(index["classes"]["World"]["members"]["Split"], "Split summary")

    def test_failed_sync_leaves_no_find_index(self):
        self.write_current_manifest()
        api_dump.install_find_index(api_dump.build_find_index(self.current_stamp()))
        with self.assertRaises(SystemExit) as raised:
            self.sync_output(mock.Mock(side_effect=OSError("offline")))
        self.assertEqual(raised.exception.code, 3)
        self.assertFalse(os.path.exists(self.find_index_path))

    def test_fresh_sync_builds_only_a_missing_or_mismatched_find_index(self):
        self.write_current_manifest()
        with mock.patch.object(api_dump.gatelib, "corpus_status", return_value=("fresh", "")):
            _, first = self.output("--sync")
            self.assertIn("find-index|rebuilt|", first)
            self.assertIsNotNone(api_dump.installed_find_index())
            _, second = self.output("--sync")
        self.assertNotIn("find-index", second)





if __name__ == "__main__":
    unittest.main(verbosity=2)
