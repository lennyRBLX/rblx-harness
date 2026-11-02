#!/usr/bin/env python3
"""Local ATC port: real Git merges, concurrent leases, fencing and cleanup."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))
import context_pack
import coord
import setup_project


class Fixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name).resolve()
        self.root = self.folder / "repo"
        self.root.mkdir()
        self.git(self.root, "init", "-q")
        self.git(self.root, "config", "user.name", "Test")
        self.git(self.root, "config", "user.email", "test@invalid")
        self.base = "".join("line %d\n" % n for n in range(12))
        (self.root / "a.txt").write_text(self.base)
        self.git(self.root, "add", ".")
        self.git(self.root, "-c", "commit.gpgsign=false", "commit", "-qm", "base")

    def git(self, root, *args):
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        return result.stdout

    def peer(self):
        path = self.folder / "peer"
        self.git(self.root, "worktree", "add", "--detach", str(path), "HEAD")
        return path

    def invoke(self, *args, input=None):
        return subprocess.run([sys.executable, "-B", str(ROOT / "tools/harness.py"), "--root", str(self.root), *args],
                              input=input, capture_output=True, text=True)


class OverlapTest(Fixture):
    def test_staged_conflict_survives_worktree_revert_and_preserves_indexes_and_objects(self):
        peer = self.peer()
        (self.root / "a.txt").write_text("mine\n")
        self.git(self.root, "add", "a.txt")
        (self.root / "a.txt").write_text(self.base)
        (peer / "a.txt").write_text("theirs\n")
        indexes = [Path(os.fsdecode(self.git(path, "rev-parse", "--path-format=absolute", "--git-path", "index")).strip())
                   for path in (self.root, peer)]
        before = [p.read_bytes() for p in indexes]
        objects = self.root / ".git/objects"
        saved_objects = sorted(str(p.relative_to(objects)) for p in objects.rglob("*") if p.is_file())
        report = context_pack.inspect_overlap(self.root, ["a.txt"])
        self.assertEqual(report["state"], "conflict", report)
        self.assertTrue(report["complete"])
        self.assertEqual(report["peers"][0]["files"], ["a.txt"])
        self.assertEqual(before, [p.read_bytes() for p in indexes])
        self.assertEqual(saved_objects, sorted(str(p.relative_to(objects)) for p in objects.rglob("*") if p.is_file()))
        result = self.invoke("inspect", "diff", "--path", "a.txt", "--overlap", "--no-cache")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["overlap"]["state"], "conflict")

    def test_clean_merge_is_still_reported_as_shared_work(self):
        peer = self.peer()
        (self.root / "a.txt").write_text(self.base.replace("line 1\n", "mine\n"))
        (peer / "a.txt").write_text(self.base.replace("line 10\n", "theirs\n"))
        report = context_pack.inspect_overlap(self.root, ["a.txt"])
        self.assertEqual(report["state"], "overlap", report)

    def test_untracked_additions_and_committed_peer_changes_are_compared(self):
        peer = self.peer()
        (self.root / "new file.txt").write_text("mine\n")
        (peer / "new file.txt").write_text("theirs\n")
        self.git(peer, "add", ".")
        self.git(peer, "-c", "commit.gpgsign=false", "commit", "-qm", "peer")
        report = context_pack.inspect_overlap(self.root, ["new file.txt"])
        self.assertEqual(report["state"], "conflict", report)

    def test_missing_peer_and_timed_out_peer_never_report_clear(self):
        peer = self.peer()
        original = context_pack.worktree_snapshot

        def snapshot(path, *args):
            if path == peer:
                raise subprocess.TimeoutExpired("git", 30)
            return original(path, *args)

        with mock.patch.object(context_pack, "worktree_snapshot", side_effect=snapshot):
            report = context_pack.inspect_overlap(self.root, ["a.txt"])
        self.assertEqual(report["state"], "unknown", report)
        self.assertFalse(report["complete"])
        shutil.rmtree(peer)
        report = context_pack.inspect_overlap(self.root, ["a.txt"])
        self.assertEqual(report["state"], "unknown", report)
        self.assertIn("peerUnavailable", report["limitations"])

    def test_literal_scopes_do_not_expand_globs(self):
        peer = self.peer()
        (self.root / "a.txt").write_text("mine\n")
        (peer / "a.txt").write_text("theirs\n")
        report = context_pack.inspect_overlap(self.root, ["*.txt"])
        self.assertEqual(report["state"], "clear", report)
        self.assertEqual(context_pack.inspect_overlap(self.root, ["../peer"])["state"], "unknown")

    def test_scratch_recovers_dead_owners_and_preserves_live_or_unmarked_folders(self):
        process = subprocess.Popen([sys.executable, "-c", "pass"])
        process.wait(timeout=10)
        dead = self.folder / ("harness-overlap-%d-dead" % process.pid)
        live = self.folder / ("harness-overlap-%d-live" % os.getpid())
        unmarked = self.folder / ("harness-overlap-%d-user" % process.pid)
        for path in (dead, live, unmarked):
            path.mkdir()
        for path in (dead, live):
            (path / ".owner").write_text("harness-overlap-v1")
        with mock.patch.object(context_pack.tempfile, "gettempdir", return_value=str(self.folder)):
            with self.assertRaises(RuntimeError):
                with context_pack.overlap_scratch() as scratch:
                    self.assertTrue(scratch.exists())
                    raise RuntimeError("interrupted")
        self.assertFalse(dead.exists())
        self.assertFalse(scratch.exists())
        self.assertTrue(live.exists())
        self.assertTrue(unmarked.exists())

    def test_preview_omissions_are_explicit_and_full_report_is_unchanged(self):
        report = {"state": "conflict", "complete": True, "limitations": [],
                  "peers": [{"worktree": "peer", "state": "conflict", "files": ["x" * 100 for _ in range(100)]}]}
        preview = context_pack.overlap_preview(report, 600)
        self.assertLessEqual(len(json.dumps(preview)), 600)
        self.assertGreater(preview["peers"][0]["omitted_files"], 0)
        self.assertEqual(len(report["peers"][0]["files"]), 100)


class LeaseTest(Fixture):
    def test_concurrent_owners_get_one_reservation(self):
        processes = [subprocess.Popen([sys.executable, "-B", str(ROOT / "tools/coord.py"), "--root", str(self.root),
                                      "begin", "--owner", owner, "--path", "src"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                     for owner in ("first", "second")]
        results = [p.communicate(timeout=15) for p in processes]
        states = [json.loads(out)["state"] for out, _ in results]
        self.assertCountEqual(states, ["owned", "busy"], results)

    def test_directories_cover_children_but_not_prefix_neighbors(self):
        first = coord.begin(self.root, "first", ["src"])
        self.assertEqual(coord.begin(self.root, "second", ["src/file"])["state"], "busy")
        self.assertEqual(coord.begin(self.root, "second", ["src2"])["state"], "owned")
        self.assertEqual(coord.check(self.root, "first", first["lease"], ["src/file"])["state"], "owned")
        self.assertEqual(coord.check(self.root, "first", first["lease"], ["."])["state"], "outsideScope")

    def test_expiry_cannot_steal_work_and_reacquisition_fences_old_tokens(self):
        first = coord.begin(self.root, "first", ["src"])
        with mock.patch.object(coord.time, "time", return_value=time.time() + 400):
            self.assertEqual(coord.begin(self.root, "second", ["src"])["state"], "unknown")
            self.assertEqual(coord.check(self.root, "first", first["lease"])["state"], "owned")
        coord.end(self.root, "first", first["lease"])
        second = coord.begin(self.root, "first", ["src"])
        self.assertGreater(second["lease"], first["lease"])
        coord.end(self.root, "first", first["lease"])
        self.assertEqual(coord.check(self.root, "first", first["lease"])["state"], "stale")
        self.assertEqual(coord.check(self.root, "first", second["lease"])["state"], "owned")

    def test_scope_updates_are_atomic_idempotent_and_fenced(self):
        first = coord.begin(self.root, "first", ["a"])
        self.assertEqual(coord.begin(self.root, "first", ["a"]), first)
        coord.begin(self.root, "second", ["b"])
        self.assertEqual(coord.begin(self.root, "first", ["a", "b"])["state"], "busy")
        self.assertEqual(coord.check(self.root, "first", first["lease"], ["a"])["state"], "owned")
        changed = coord.begin(self.root, "first", ["c"])
        self.assertNotEqual(changed["lease"], first["lease"])
        self.assertEqual(coord.check(self.root, "first", first["lease"])["state"], "stale")

    def test_worktrees_share_state_and_keep_separate_write_scopes(self):
        peer = self.peer()
        coord.begin(self.root, "first", ["a.txt"])
        coord.begin(peer, "second", ["a.txt"], parent="first")
        self.assertEqual(coord.database_path(self.root), coord.database_path(peer))
        self.assertEqual(coord.check(peer)["owners"], ["second"])
        coord.cleanup(self.root, "first")
        self.assertEqual(coord.check(peer)["state"], "clear")

    def test_confirmed_process_death_reclaims_without_expiry_or_manual_cleanup(self):
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            first = coord.begin(self.root, "first", ["a.txt"], pid=process.pid)
        finally:
            process.terminate()
            process.wait(timeout=10)
        self.assertEqual(coord.begin(self.root, "second", ["a.txt"])["state"], "owned")
        self.assertEqual(coord.check(self.root, "first", first["lease"])["state"], "stale")

    def test_lifecycle_hooks_release_only_the_stopped_scope(self):
        parent = coord.begin(self.root, "parent", ["a"])
        coord.begin(self.root, "other", ["c"])
        for active in (True, False):
            child = coord.begin(self.root, "child", ["b"], parent="parent")
            event = {"hook_event_name": "SubagentStop", "agent_id": "child", "session_id": "parent",
                     "cwd": str(self.root), "stop_hook_active": active}
            with mock.patch("sys.stdin", io.StringIO(json.dumps(event))), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(coord.hook(), 0)
            self.assertEqual(json.loads(output.getvalue()), {})
            self.assertEqual(coord.check(self.root, "child", child["lease"])["state"], "stale")
        self.assertEqual(coord.check(self.root, "parent", parent["lease"])["state"], "owned")
        event = {"hook_event_name": "SessionEnd", "session_id": "parent", "cwd": str(self.root)}
        with mock.patch("sys.stdin", io.StringIO(json.dumps(event))), contextlib.redirect_stdout(io.StringIO()):
            coord.hook()
        self.assertEqual(coord.check(self.root)["owners"], ["other"])

    def test_unregistered_session_cleanup_creates_no_state_and_invalid_input_has_fixed_output(self):
        coord.cleanup(self.root, "unknown")
        self.assertFalse((self.root / ".git/harness").exists())
        result = self.invoke("coord", "begin", "--owner", "bad\nowner", "--path", ".")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("bad", result.stdout)
        with self.assertRaises(ValueError):
            coord.begin(self.root, "first", ["../outside"])
        result = self.invoke("coord", "begin", "--owner", "first", "--path", ".", "--overlap")
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.root / ".git/harness").exists())

    def test_corrupt_state_and_symlink_escapes_remain_unknown(self):
        coord.begin(self.root, "first", ["a"])
        with coord.store(self.root) as db:
            db.execute("UPDATE leases SET expires = 'untrusted'")
        result = self.invoke("coord", "check")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["state"], "unknown")
        if os.name != "nt":
            (self.root / "escape").symlink_to(self.folder, target_is_directory=True)
            with self.assertRaises(ValueError):
                coord.scopes(self.root, ["escape/file"])

    def test_installed_hook_command_cleans_a_registered_owner(self):
        held = coord.begin(self.root, "child", ["a"], parent="parent")
        setup_project.install_coord_hooks(str(self.root), "codex")
        document = json.loads((self.root / ".codex/hooks.json").read_text())
        command = document["hooks"]["SubagentStop"][0]["hooks"][0]["command"]
        event = {"hook_event_name": "SubagentStop", "agent_id": "child", "cwd": str(self.root)}
        result = subprocess.run(shlex.split(command), input=json.dumps(event), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {})
        self.assertEqual(coord.check(self.root, "child", held["lease"])["state"], "stale")


class HookSetupTest(unittest.TestCase):
    def test_cleanup_merge_preserves_custom_hooks_metadata_and_repeat_bytes(self):
        for host, relative in (("codex", ".codex/hooks.json"), ("claude", ".claude/settings.json")):
            with self.subTest(host=host), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / relative
                path.parent.mkdir()
                custom = {"matcher": "custom", "hooks": [{"type": "command", "command": "echo custom"}]}
                document = {"custom": 42, "hooks": {"SubagentStop": [custom], "PreToolUse": [custom]}}
                path.write_text(json.dumps(document))
                setup_project.install_coord_hooks(directory, host)
                actual = json.loads(path.read_text())
                self.assertEqual(actual["custom"], 42)
                self.assertEqual(actual["hooks"]["PreToolUse"], [custom])
                self.assertEqual(actual["hooks"]["SubagentStop"][0], custom)
                self.assertEqual(len(actual["hooks"]["SubagentStop"]), 2)
                saved = path.read_bytes()
                setup_project.install_coord_hooks(directory, host)
                self.assertEqual(saved, path.read_bytes())

    def test_moved_checkout_replaces_only_exact_cleanup_handlers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".codex/hooks.json"
            path.parent.mkdir()
            previous = setup_project.coord_hook_entry("/old folder/tools/coord.py")
            custom = setup_project.coord_hook_entry("/custom/tools/coord.py")
            custom["hooks"][0]["timeout"] = 17
            path.write_text(json.dumps({"hooks": {"SessionEnd": [previous, custom]}}))
            setup_project.install_coord_hooks(directory, "codex")
            entries = json.loads(path.read_text())["hooks"]["SessionEnd"]
            self.assertEqual(entries[0], custom)
            self.assertEqual(len(entries), 2)
            self.assertNotIn(previous, entries)

    def test_windows_hook_arguments_are_literal_and_migration_matches_them(self):
        import base64
        script = "C:/task $(literal)/it's/tools/coord.py"
        with mock.patch.object(setup_project.os, "name", "nt"):
            entry = setup_project.coord_hook_entry(script, "C:/Python/python.exe")
            self.assertTrue(setup_project.installed_coord_hook(entry))
        encoded = shlex.split(entry["hooks"][0]["command"])[3]
        expression = base64.b64decode(encoded).decode("utf-16le")
        self.assertEqual(expression, "& 'C:/Python/python.exe' '-B' 'C:/task $(literal)/it''s/tools/coord.py' 'hook'")


if __name__ == "__main__":
    unittest.main()
