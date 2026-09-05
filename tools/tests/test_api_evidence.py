#!/usr/bin/env python3
"""Offline regressions for additive API evidence and retained agent records.

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


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
GATES = os.path.join(ROOT, "shared", "gates")
AGENT_GATE = os.path.join(GATES, "agent_gate.py")
if GATES not in sys.path:
    sys.path.insert(0, GATES)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


api_dump = load_module("api_dump_evidence_test", os.path.join(ROOT, "tools", "api_dump", "api_dump.py"))
token_shrink = load_module("token_shrink_evidence_test", os.path.join(GATES, "token_shrink.py"))


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


class TokenShrinkEvidenceTest(unittest.TestCase):
    def assert_gate_accepts(self, agent, message):
        payload = json.dumps(
            {
                "agent_type": agent,
                "agent_depth": 1,
                "last_assistant_message": message,
            }
        )
        result = subprocess.run(
            [sys.executable, AGENT_GATE, "--event", "SubagentStop"],
            input=payload,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_researcher_record_preserves_decision_evidence_and_negation(self):
        source = (
            "researcher: FOUND\n"
            "fact|api_dump.py access World.Split|context=game-server operation=write "
            "security=PluginSecurity capability=PluginOrOpenCloud api_dump_revision=sha-a "
            "creator_docs_revision=docs-a literal_error=\"The current identity (2) cannot set Split\" "
            "runtime=unknown; next=run Studio; effect is not allowed to be inferred in order to continue\n"
            "fact|api_dump.py behavior UnknownTopic|context=game-client operation=effect security=unknown "
            "capability=unknown creator_docs_revision=unknown; next=research exact context; absence does not prove permission"
        )
        self.assert_gate_accepts("researcher", source)
        actual = token_shrink.shrink_return("researcher", source)
        for literal in (
            "context=game-server",
            "operation=write",
            "security=PluginSecurity",
            "capability=PluginOrOpenCloud",
            "api_dump_revision=sha-a",
            "creator_docs_revision=docs-a",
            '\"The current identity (2) cannot set Split\"',
            "runtime=unknown",
            "next=run Studio",
            "creator_docs_revision=unknown; next=research exact context",
            "does not prove permission",
        ):
            self.assertIn(literal, actual)
        self.assertIn("effect is not allowed to be inferred in order to continue", actual)

    def test_reviewer_record_preserves_exact_error_unknown_and_next_action(self):
        source = (
            "reviewer: ISSUES\n"
            "finding|tools/api_dump/api_dump.py:545|high|context=game-client operation=read security=None capability=PluginOrOpenCloud "
            "api_dump_revision=sha-b creator_docs_revision=unknown literal_error=`CoreScript cannot access Source` "
            "effect=unknown|review is not allowed to infer permission; next=compare each operation in order to continue"
        )
        self.assert_gate_accepts("reviewer", source)
        actual = token_shrink.shrink_return("reviewer", source)
        for literal in (
            "context=game-client",
            "operation=read",
            "security=None",
            "capability=PluginOrOpenCloud",
            "api_dump_revision=sha-b",
            "creator_docs_revision=unknown",
            "`CoreScript cannot access Source`",
            "effect=unknown",
            "next=compare each operation",
        ):
            self.assertIn(literal, actual)
        self.assertIn("review must not infer permission", actual)
        self.assertIn("to continue", actual)


if __name__ == "__main__":
    unittest.main(verbosity=2)
