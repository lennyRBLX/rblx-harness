#!/usr/bin/env python3
"""Synchronize a managed project with its canonical origin branch.

``check`` performs the same live fetch and ancestry check as GATE6. ``repair``
preserves indexed, tracked, and untracked work, rebases local commits onto the
fetched remote tip, and restores the saved work. It never commits or pushes.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(os.path.dirname(HERE))
GATES = os.path.join(HARNESS, "shared", "gates")
sys.path.insert(0, GATES)
import gatelib  # noqa: E402

LOCK_MAX_AGE = 900
REPAIRABLE = {"behind", "diverged"}


class SyncError(Exception):
    pass


def repository_root(root):
    rc, value, error = gatelib.git(root, "rev-parse", "--show-toplevel")
    if rc != 0 or not value:
        raise SyncError((error or "working directory is not a Git repository")[:240])
    return os.path.realpath(value)


def result(status, detail, root="", branch="", remote_tip="", head="", stash=""):
    return {
        "status": status,
        "detail": detail,
        "root": root,
        "branch": branch,
        "remote_tip": remote_tip,
        "head": head,
        "stash": stash,
    }


def context(root):
    branch, branch_error = gatelib.canonical_remote_branch(root)
    if branch is None:
        raise SyncError(branch_error)
    rc, remote_tip, error = gatelib.git(root, "rev-parse", "--verify", "origin/%s^{commit}" % branch)
    if rc != 0:
        raise SyncError((error or "origin/%s is absent" % branch)[:240])
    rc, head, error = gatelib.git(root, "rev-parse", "--verify", "HEAD^{commit}")
    if rc != 0:
        raise SyncError((error or "HEAD is unreadable")[:240])
    return branch, remote_tip, head


def check(root, fetch=True):
    root = repository_root(root)
    state, detail = gatelib.gate6_state(root, fetch=fetch)
    branch = remote_tip = head = ""
    try:
        branch, remote_tip, head = context(root)
    except SyncError:
        pass
    return result(state, detail, root, branch, remote_tip, head)


def lock_path(root):
    key = hashlib.sha256(os.path.realpath(root).encode("utf-8")).hexdigest()[:20]
    return os.path.join(gatelib.CACHE, "git-sync-%s.lock" % key)


def _pid_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acquire_lock(root):
    os.makedirs(gatelib.CACHE, exist_ok=True)
    path = lock_path(root)
    for _ in range(2):
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            try:
                with open(path, encoding="utf-8") as handle:
                    held = json.load(handle)
            except (OSError, ValueError, UnicodeError):
                held = {}
            age = time.time() - float(held.get("timestamp", 0))
            if _pid_alive(held.get("pid")) and age < LOCK_MAX_AGE:
                raise SyncError("another git_sync process holds this clone")
            try:
                os.remove(path)
            except OSError:
                raise SyncError("the stale git_sync lock could not be reclaimed")
            continue
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"pid": os.getpid(), "timestamp": time.time(), "root": root}, handle)
        return path
    raise SyncError("the git_sync lock could not be acquired")


def release_lock(path):
    try:
        os.remove(path)
    except OSError:
        pass


def run_git(root, *args):
    rc, output, error = gatelib.git_mutate(root, *args, timeout=300)
    if rc != 0:
        raise SyncError((error or output or "git command failed")[:400])
    return output


def stash_reference(root, oid):
    rc, output, _ = gatelib.git(root, "stash", "list", "--format=%H%x00%gd")
    if rc != 0:
        return None
    for line in output.splitlines():
        commit, separator, reference = line.partition("\x00")
        if separator and commit == oid:
            return reference
    return None


def drop_stash(root, oid):
    reference = stash_reference(root, oid)
    if reference:
        run_git(root, "stash", "drop", "--quiet", reference)


def restore_stash(root, oid):
    rc, output, error = gatelib.git_mutate(root, "stash", "apply", "--index", oid, timeout=300)
    if rc != 0:
        raise SyncError(
            "saved work could not be restored; stash %s was retained: %s"
            % (oid[:12], (error or output or "stash apply conflicted")[:240])
        )
    drop_stash(root, oid)


def repair(root):
    root = repository_root(root)
    lock = acquire_lock(root)
    stash_oid = ""
    try:
        state, detail = gatelib.gate6_state(root, fetch=True)
        if state == "ok":
            branch, remote_tip, head = context(root)
            return result("ok", "already synchronized", root, branch, remote_tip, head)
        if state not in REPAIRABLE:
            return result(state, detail, root)

        rc, status, error = gatelib.git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
        if rc != 0:
            raise SyncError((error or "working-tree status is unreadable")[:240])
        if status:
            before_rc, before_stash, _ = gatelib.git(root, "rev-parse", "--verify", "refs/stash")
            run_git(
                root,
                "stash",
                "push",
                "--include-untracked",
                "--message",
                "harness-git-sync-%d-%d" % (os.getpid(), int(time.time())),
            )
            rc, stash_oid, error = gatelib.git(root, "rev-parse", "--verify", "refs/stash")
            if rc != 0 or (before_rc == 0 and stash_oid == before_stash):
                raise SyncError((error or "Git did not create the required safety stash")[:240])

        state, detail = gatelib.gate6_state(root, fetch=True)
        if state == "ok":
            if stash_oid:
                restore_stash(root, stash_oid)
            branch, remote_tip, head = context(root)
            return result("ok", "synchronized", root, branch, remote_tip, head)
        if state not in ("behind", "diverged"):
            if stash_oid:
                restore_stash(root, stash_oid)
                stash_oid = ""
            return result(state, detail, root, stash=stash_oid)

        branch, remote_tip, _ = context(root)
        rc, output, error = gatelib.git_mutate(root, "rebase", "origin/%s" % branch, timeout=600)
        if rc != 0:
            gatelib.git_mutate(root, "rebase", "--abort", timeout=120)
            restore_error = ""
            if stash_oid:
                try:
                    restore_stash(root, stash_oid)
                    stash_oid = ""
                except SyncError as restore:
                    restore_error = "; " + str(restore)
            return result(
                "repair-conflict",
                "rebase failed: %s%s" % ((error or output or "conflict")[:240], restore_error),
                root,
                branch,
                remote_tip,
                stash=stash_oid,
            )

        if stash_oid:
            try:
                restore_stash(root, stash_oid)
                stash_oid = ""
            except SyncError as restore:
                return result("repair-conflict", str(restore), root, branch, remote_tip, stash=stash_oid)

        final = check(root, fetch=True)
        if final["status"] != "ok":
            final["detail"] = "remote changed during repair: " + final["detail"]
            return final
        final["detail"] = "rebased onto origin/%s and restored local work" % branch
        return final
    except SyncError as error:
        return result("repair-failed", str(error), root, stash=stash_oid)
    finally:
        release_lock(lock)


def print_result(record):
    print("RESULT|" + json.dumps(record, sort_keys=True))
    if record["status"] == "ok":
        print("OK|" + record["detail"])
        return 0
    print("GATE6|%s|%s" % (record["status"], record["detail"]))
    return 2


def main(argv=None):
    parser = argparse.ArgumentParser(prog="git_sync")
    parser.add_argument("command", choices=("check", "repair"), nargs="?", default="check")
    parser.add_argument("--root", default=".")
    parser.add_argument("--no-fetch", action="store_true")
    args = parser.parse_args(argv)
    try:
        record = repair(args.root) if args.command == "repair" else check(args.root, fetch=not args.no_fetch)
    except SyncError as error:
        record = result("repair-failed" if args.command == "repair" else "check-failed", str(error))
    return print_result(record)


if __name__ == "__main__":
    sys.exit(main())
