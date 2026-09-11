#!/usr/bin/env python3
"""Behavior checks for session accounting, evidence packs and tool routing."""
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
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "shared/gates")]
import context_pack
import session_audit
import studio_output
import studio_rpc


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.cache = Path(self.temp.name) / "cache"

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def git(self, *args):
        return context_pack.git(self.root, *args)

    def test_spans_bound_output_and_reuse_only_same_scope(self):
        path = self.write("space file.luau", "one\ntwo\nthree\n")
        items = context_pack.read_items(self.root, ["space file.luau:2:3"])
        self.assertEqual(items[0]["text"], "two\nthree\n")
        artifact, pack = context_pack.save_pack(self.root, "read", items, self.cache)
        preview = context_pack.preview(artifact, pack, 4)
        self.assertFalse(preview["preview_complete"])
        self.assertEqual(preview["items"][0]["omitted_chars"], 6)
        self.assertEqual(json.loads(artifact.read_text())["items"], items)
        repeat = context_pack.preview(artifact, pack, since=artifact)
        self.assertNotIn("text", repeat["items"][0])
        path.write_text("one\nnew\nthree\n")
        new_path, new_pack = context_pack.save_pack(self.root, "read", context_pack.read_items(self.root, ["space file.luau:2:3"]), self.cache)
        self.assertIn("new", context_pack.preview(new_path, new_pack, since=artifact)["items"][0]["text"])
        pack["root"] = "different"
        with self.assertRaisesRegex(ValueError, "root or mode"):
            context_pack.preview(artifact, pack, since=artifact)

    def test_paths_ranges_binary_and_corrupt_receipts_fail(self):
        path = self.write("source.luau", "ok\n")
        for spec in ("source.luau:0:1", "source.luau:1:3", "../outside"):
            with self.assertRaises(ValueError):
                context_pack.read_items(self.root, [spec])
        link = self.root / "outside.luau"
        link.symlink_to(Path(self.temp.name) / "private")
        with self.assertRaises(ValueError):
            context_pack.read_items(self.root, ["outside.luau"])
        items = context_pack.read_items(self.root, ["source.luau"])
        artifact, pack = context_pack.save_pack(self.root, "read", items, self.cache)
        artifact.write_text("{}")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            context_pack.preview(artifact, pack, since=artifact)
        path.write_bytes(b"\x00binary")
        with self.assertRaisesRegex(ValueError, "binary"):
            context_pack.read_items(self.root, ["source.luau"])

    def test_diff_covers_index_worktree_deletions_untracked_and_literal_paths(self):
        self.git("init", "--quiet")
        self.write("scope/a.luau", "before\n")
        self.write("scope/gone.luau", "delete\n")
        self.write("other.luau", "unrelated\n")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "base")
        self.write("scope/a.luau", "staged\n")
        self.git("add", "scope/a.luau")
        self.write("scope/a.luau", "working\n")
        (self.root / "scope/gone.luau").unlink()
        self.write("scope/new.luau", "new content\n")
        self.write("other.luau", "unrelated change\n")
        self.write(".gitignore", "scope/ignored\n")
        self.write("scope/ignored", "private cache\n")
        items = context_pack.diff_items(self.root, ["scope"])
        self.assertIn("+staged", items[0]["text"])
        self.assertIn("+working", items[1]["text"])
        self.assertIn("-delete", items[1]["text"])
        self.assertNotIn("other.luau", str(items))
        self.assertEqual([i["path"] for i in items[2:]], ["scope/new.luau"])
        self.assertEqual(context_pack.diff_items(self.root, ["scope/*"])[0]["text"], "")
        self.assertEqual(context_pack.diff_items(self.root, ["scope"]), items)
        self.write("scope/a.luau", "before\n")
        reverted = context_pack.diff_items(self.root, ["scope/a.luau"])
        self.assertIn("+staged", reverted[0]["text"])
        self.assertIn("-staged", reverted[1]["text"])
        with self.assertRaises(ValueError):
            context_pack.diff_items(self.root, ["scope"], "--bad-ref")

    def test_no_cache_cli_does_not_write(self):
        self.write("x.luau", "return {}\n")
        with mock.patch.object(context_pack, "save_pack", side_effect=AssertionError("cache write")), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(context_pack.main(["--root", str(self.root), "--no-cache", "read", "--file", "x.luau"]), 0)
        self.assertIsNone(json.loads(output.getvalue())["artifact"])


class AuditTests(unittest.TestCase):
    def test_duplicate_history_archives_descendants_and_usage_are_counted_once(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def write(folder, name, meta, records):
                path = root / folder / name
                path.parent.mkdir(parents=True, exist_ok=True)
                rows = [{"type": "session_meta", "payload": meta}] + records
                path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            call = {"type": "response_item", "payload": {"type": "custom_tool_call", "call_id": "call1", "name": "exec", "input": 'text(await tools.exec_command({cmd:"cat x.luau"}))'}}
            out = {"type": "response_item", "payload": {"type": "custom_tool_call_output", "call_id": "call1", "output": [{"type": "input_text", "text": "return {}"}]}}
            usage = {"type": "token_usage_record", "payload": {"thread_id": "a", "response_id": "r1", "usage": {"input_tokens": 100, "cached_input_tokens": 60, "output_tokens": 10, "total_tokens": 110}}}
            write("sessions", "a.jsonl", {"id": "a", "cwd": "/work/arena"}, [call, out, usage])
            write("archived_sessions", "b.jsonl", {"id": "b", "parent_thread_id": "a", "cwd": "/elsewhere"}, [call, out, usage])
            write("sessions", "c.jsonl", {"id": "c", "cwd": "/work/arena-copy"}, [call, out])
            write("sessions", "invalid.jsonl", {"cwd": "/work/arena"}, [])
            report = session_audit.audit(root, "arena")
            self.assertEqual(report["coverage"]["session_files"], 2)
            self.assertEqual(report["coverage"]["unique_calls"], 1)
            self.assertEqual(report["coverage"]["copied_calls_removed"], 1)
            self.assertEqual(len(report["coverage"]["inventory_errors"]), 1)
            self.assertEqual(report["recorded_usage"]["total_tokens"], 110)
            self.assertEqual(sum(r["count"] for r in report["categories"]), 1)
            self.assertIn("Count: highest to lowest", session_audit.markdown(report))

    def test_ciphertext_and_media_are_not_counted_as_visible_tokens(self):
        self.assertEqual(session_audit.visible("before gAAAAA" + "x" * 100 + " after"), "before  after")
        self.assertEqual(session_audit.visible({"type": "image", "data": "a" * 200}), "")
        self.assertEqual(session_audit.visible({"type": "encrypted_content", "encrypted_content": "x" * 200}), "")


class ConsoleTests(unittest.TestCase):
    def test_delta_rotation_scope_and_output_limits(self):
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp)
            first = studio_output.snapshot("studio:a", "old\n", cache=cache)
            new = studio_output.snapshot("studio:a", "old\nRUN|error\nRUN|end\nother\n", first["artifact"], ["RUN"], 1, 5, cache)
            self.assertEqual(new["new_lines"], 3)
            self.assertEqual(new["matched_lines"], 2)
            self.assertEqual(new["omitted_lines"], 1)
            self.assertEqual(new["omitted_chars"], 2)
            repeat = studio_output.snapshot("studio:a", "old\nRUN|error\nRUN|end\nother\n", new["artifact"], cache=cache)
            self.assertEqual(repeat["new_lines"], 0)
            rotated = studio_output.snapshot("studio:a", "other\nfresh\n", new["artifact"], cache=cache)
            self.assertEqual(rotated["continuity"], "reset-or-rotation")
            self.assertEqual(rotated["new_lines"], 2)
            with self.assertRaisesRegex(ValueError, "scope mismatch"):
                studio_output.snapshot("studio:b", "log", first["artifact"], cache=cache)

    def test_live_read_has_explicit_id_and_no_execute_or_play(self):
        rpc = mock.Mock()
        rpc.list_studios.return_value = [{"id": "a"}]
        rpc.call.return_value = "console"
        self.assertEqual(studio_output.live_console(rpc, "a"), "console")
        rpc.call.assert_called_once_with("get_console_output", {"studio_id": "a"})
        rpc.reset_mock()
        with self.assertRaises(ValueError):
            studio_output.live_console(rpc, "b")
        rpc.call.assert_not_called()

    def test_transport_tool_error_is_not_success_and_failed_start_closes(self):
        rpc = studio_rpc.StudioRPC()
        with mock.patch.object(rpc, "_request", return_value={"isError": True, "content": [{"type": "text", "text": "disconnected"}]}):
            with self.assertRaises(studio_rpc.EnvError):
                rpc.call("get_console_output")
        with mock.patch.object(rpc, "start", side_effect=ValueError("bad init")), mock.patch.object(rpc, "close") as close:
            with self.assertRaises(ValueError):
                with rpc:
                    pass
            close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
