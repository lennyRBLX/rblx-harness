#!/usr/bin/env python3
"""Local scope leases and lifecycle cleanup. GitHub writes are never performed."""
import argparse
import contextlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time

from context_pack import git, inspect_overlap, overlap_preview, process_alive, within

ID = re.compile(r"[A-Za-z0-9_./:-]{1,160}\Z")
SCHEMA = """CREATE TABLE IF NOT EXISTS leases (
    lease INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT UNIQUE NOT NULL,
    parent TEXT, worktree TEXT NOT NULL, paths TEXT NOT NULL,
    pid INTEGER, expires REAL NOT NULL)"""


def identity(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("invalid owner")
    return value


def scopes(root, paths):
    result = set()
    for name in paths:
        if not isinstance(name, str) or not name or len(name) > 4096 or Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("scope must be repo-relative")
        path = within(root, name).relative_to(root).as_posix()
        if path == ".git" or path.startswith(".git/"):
            raise ValueError("Git metadata cannot be leased")
        result.add(path)
    if not result or len(result) > 100:
        raise ValueError("provide 1..100 scopes")
    return sorted(result)


def overlaps(first, second):
    return any(a == "." or b == "." or a == b or a.startswith(b + "/") or b.startswith(a + "/")
               for a in first for b in second)


def database_path(root):
    top = Path(os.fsdecode(git(root, "rev-parse", "--show-toplevel")).rstrip("\n")).resolve()
    if top != root:
        raise ValueError("coord requires worktree root")
    common = Path(os.fsdecode(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")).rstrip("\n"))
    return common / "harness" / "coord.sqlite3"


@contextlib.contextmanager
def store(root, create=False):
    path = database_path(root)
    if not path.exists() and not create:
        yield None
        return
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("coord state cannot be a symlink")
    path.parent.mkdir(mode=0o700, exist_ok=True)
    connection = sqlite3.connect(path, timeout=1, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        if create:
            connection.execute(SCHEMA)
            os.chmod(path, 0o600)
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute("SELECT * FROM leases LIMIT 1001").fetchall()
        if len(rows) > 1000:
            raise ValueError("owner limit")
        for row in rows:
            if (set(row.keys()) != {"lease", "owner", "parent", "worktree", "paths", "pid", "expires"}
                    or type(row["lease"]) is not int or row["lease"] < 1
                    or not isinstance(row["worktree"], str) or not Path(row["worktree"]).is_absolute()
                    or type(row["expires"]) not in (int, float) or not math.isfinite(row["expires"])):
                raise ValueError("invalid stored lease")
            identity(row["owner"])
            if row["parent"] is not None:
                identity(row["parent"])
            paths = json.loads(row["paths"])
            if (not isinstance(paths, list) or not 1 <= len(paths) <= 100
                    or any(not isinstance(p, str) or not p or len(p) > 4096 or Path(p).is_absolute()
                           or ".." in Path(p).parts for p in paths)):
                raise ValueError("invalid stored scopes")
            if row["pid"] is not None:
                if type(row["pid"]) is not int or not 1 <= row["pid"] < 2**31:
                    raise ValueError("invalid stored process")
                if not process_alive(row["pid"]):
                    connection.execute("DELETE FROM leases WHERE lease = ?", (row["lease"],))
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def begin(root, owner, paths, parent=None, pid=None, ttl=300):
    owner = identity(owner)
    parent = identity(parent) if parent is not None else None
    paths = scopes(root, paths)
    if owner == parent or not 30 <= ttl <= 3600:
        raise ValueError("invalid parent or expiry")
    if pid is not None and (type(pid) is not int or not 1 <= pid < 2**31 or not process_alive(pid)):
        raise ValueError("owner process must be alive")
    now = time.time()
    with store(root, create=True) as db:
        rows = db.execute("SELECT * FROM leases").fetchall()
        existing = next((row for row in rows if row["owner"] == owner), None)
        if existing and (existing["worktree"] != str(root) or existing["parent"] != parent):
            return {"state": "stale"}
        busy = [row for row in rows if row["owner"] != owner and row["worktree"] == str(root)
                and overlaps(paths, json.loads(row["paths"]))]
        if busy:
            return {"state": "unknown" if any(row["expires"] <= now for row in busy) else "busy",
                    "owners": [row["owner"] for row in busy[:10]], "omitted": max(0, len(busy) - 10)}
        if existing:
            if json.loads(existing["paths"]) == paths and existing["pid"] == pid:
                db.execute("UPDATE leases SET expires = ? WHERE lease = ?", (now + ttl, existing["lease"]))
                return {"state": "owned", "lease": existing["lease"]}
            db.execute("DELETE FROM leases WHERE lease = ?", (existing["lease"],))
        if len(rows) >= 1000 and not existing:
            raise ValueError("owner limit")
        lease = db.execute("INSERT INTO leases (owner, parent, worktree, paths, pid, expires) VALUES (?, ?, ?, ?, ?, ?)",
                           (owner, parent, str(root), json.dumps(paths), pid, now + ttl)).lastrowid
        return {"state": "owned", "lease": lease}


def check(root, owner=None, lease=None, paths=None):
    selected = scopes(root, paths) if paths else None
    now = time.time()
    with store(root) as db:
        if lease is not None:
            identity(owner)
            row = db.execute("SELECT * FROM leases WHERE owner = ? AND lease = ? AND worktree = ?",
                             (owner, lease, str(root))).fetchone() if db else None
            if not row:
                return {"state": "stale"}
            if selected and any(not any(s == "." or p == s or p.startswith(s + "/") for s in json.loads(row["paths"]))
                                for p in selected):
                return {"state": "outsideScope"}
            db.execute("UPDATE leases SET expires = ? WHERE lease = ?", (now + 300, lease))
            return {"state": "owned", "lease": lease}
        rows = db.execute("SELECT * FROM leases WHERE worktree = ?", (str(root),)).fetchall() if db else []
        rows = [row for row in rows if not selected or overlaps(selected, json.loads(row["paths"]))]
        return {"state": "unknown" if any(row["expires"] <= now for row in rows) else "busy" if rows else "clear",
                "owners": [row["owner"] for row in rows[:10]], "omitted": max(0, len(rows) - 10)}


def end(root, owner, lease=None):
    identity(owner)
    with store(root) as db:
        if db:
            db.execute("DELETE FROM leases WHERE owner = ? AND lease = ? AND worktree = ?", (owner, lease, str(root)))
    return {"state": "ended"}


def cleanup(root, owner):
    identity(owner)
    with store(root) as db:
        if db:
            db.execute("""WITH RECURSIVE ended(owner) AS (
                SELECT ? UNION SELECT leases.owner FROM leases JOIN ended ON leases.parent = ended.owner)
                DELETE FROM leases WHERE owner IN ended""", (owner,))


def hook():
    try:
        raw = sys.stdin.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("hook input limit")
        event = json.loads(raw)
        if not isinstance(event, dict):
            raise ValueError("invalid hook event")
        kind = event.get("hook_event_name")
        if kind == "SubagentStop":
            owner = event.get("agent_id")
        elif kind == "SessionEnd":
            owner = event.get("session_id")
        else:
            print("{}")
            return 0
        cwd = Path(event["cwd"]).resolve()
        root = Path(os.fsdecode(git(cwd, "rev-parse", "--show-toplevel")).rstrip("\n")).resolve()
        cleanup(root, owner)
        print("{}")
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, subprocess.TimeoutExpired):
        print(json.dumps({"systemMessage": "coord cleanup unavailable"}))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("action", choices=("begin", "check", "end", "hook"))
    parser.add_argument("--owner", default=os.environ.get("CODEX_THREAD_ID") or os.environ.get("CLAUDE_CODE_SESSION_ID"))
    parser.add_argument("--parent")
    parser.add_argument("--path", action="append")
    parser.add_argument("--lease", type=int)
    parser.add_argument("--pid", type=int, help="known long-lived owner process; never the short-lived CLI process")
    parser.add_argument("--ttl", type=int, default=300)
    parser.add_argument("--overlap", action="store_true", help="also inspect local worktrees")
    parser.add_argument("--base", default="HEAD")
    args = parser.parse_args(argv)
    if args.action == "hook":
        return hook()
    try:
        root = args.root.expanduser().resolve()
        if args.overlap and args.action != "check":
            raise ValueError("--overlap requires check")
        if args.lease is not None and args.lease < 1:
            raise ValueError("invalid lease")
        if args.action == "begin":
            result = begin(root, args.owner, args.path or [], args.parent, args.pid, args.ttl)
        elif args.action == "end":
            if args.lease is None:
                raise ValueError("end requires --lease")
            result = end(root, args.owner, args.lease)
        else:
            result = check(root, args.owner, args.lease, args.path)
        if args.overlap:
            result["overlap"] = overlap_preview(inspect_overlap(root, args.path or ["."], args.base))
        print(json.dumps(result))
        overlap = result.get("overlap", {})
        return 0 if result["state"] in ("owned", "clear", "ended") and overlap.get("state") not in ("unknown", "conflict") else 2
    except (OSError, ValueError, sqlite3.Error, subprocess.TimeoutExpired):
        print(json.dumps({"state": "unknown", "error": "coord unavailable or invalid request"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
