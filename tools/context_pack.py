#!/usr/bin/env python3
"""Bounded source excerpts and immutable scoped Git review evidence.

Use read --file path[:first:last] (repeatable), or diff --path path
(repeatable). --since reuses a pack already present in this agent's context.
Full evidence is kept outside the repo; preview omissions are explicit.
"""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

CACHE = Path.home() / ".cache/harness/context"
MAX_FILE_BYTES = 8 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(root, *args, ok=(0,), env=None, input=None, timeout=30):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                            input=input, env=dict(os.environ, GIT_OPTIONAL_LOCKS="0", **(env or {})), timeout=timeout)
    if result.returncode not in ok:
        raise ValueError(result.stderr.decode(errors="replace").strip() or "Git command failed")
    return result.stdout


def within(root, name):
    root = root.resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root):
        raise ValueError("path is outside --root: " + name)
    return path


def read_items(root, specs):
    root = root.resolve()
    items = []
    for spec in specs:
        match = re.fullmatch(r"(.+):(\d+):(\d+)", spec)
        name, first, last = (match[1], int(match[2]), int(match[3])) if match else (spec, 1, None)
        path = within(root, name)
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("source exceeds 8 MiB: " + name)
        raw = path.read_bytes()
        if b"\0" in raw:
            raise ValueError("binary source: " + name)
        lines = raw.decode("utf-8").splitlines(keepends=True)
        last = len(lines) if last is None else last
        if first < 1 or last < first or first > len(lines) or last > len(lines):
            if lines or match:
                raise ValueError("invalid source span: " + spec)
        text = "".join(lines[first - 1:last])
        items.append({"path": str(path.relative_to(root)), "first": first, "last": last,
                      "file_sha256": digest(raw), "sha256": digest(text.encode()),
                      "text": text})
    return items


def diff_items(root, paths, base="HEAD"):
    root = root.resolve()
    # Literal pathspecs prevent glob and pathspec magic from broadening scope.
    for path in paths:
        within(root, path)
        if Path(path).is_absolute() or ".." in Path(path).parts:
            raise ValueError("diff paths must be repo-relative")
    specs = [":(literal)" + path for path in paths]
    git(root, "rev-parse", "--show-toplevel")
    revision = git(root, "rev-parse", "--verify", "--end-of-options", base + "^{commit}").decode().strip()
    items = []
    # Separate layers: a staged edit reverted only in the worktree must
    # remain visible because committing the index would still publish it.
    for label, arguments in (("staged.diff", ["--cached", revision]), ("unstaged.diff", [])):
        patch = git(root, "diff", "--no-ext-diff", "--no-textconv", "--binary", "--no-renames",
                    "--unified=3", *arguments, "--", *specs)
        items.append({"path": label, "base": revision if arguments else "index",
                      "sha256": digest(patch), "text": patch.decode("utf-8", errors="replace")})
    untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z", "--", *specs)
    for raw_name in untracked.split(b"\0"):
        if not raw_name:
            continue
        name = os.fsdecode(raw_name)
        path = root / name
        if path.is_symlink():
            data = os.fsencode(os.readlink(path))
            text = "symlink -> " + os.fsdecode(data)
        else:
            if path.stat().st_size > MAX_FILE_BYTES:
                raise ValueError("untracked file exceeds 8 MiB: " + name)
            data = path.read_bytes()
            text = data.decode("utf-8") if b"\0" not in data else "[binary; inspect separately]"
        items.append({"path": name, "status": "untracked", "sha256": digest(data), "text": text})
    return items


def process_alive(pid):
    """Only a confirmed dead process permits automatic reclamation."""
    if type(pid) is not int or not 1 <= pid < 2**31:
        return True
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() != 87
        try:
            code = wintypes.DWORD()
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return True


@contextlib.contextmanager
def overlap_scratch():
    """Recover only marked scratch directories whose owning process died."""
    temporary = Path(tempfile.gettempdir())
    for path in temporary.glob("harness-overlap-*"):
        match = re.fullmatch(r"harness-overlap-([1-9][0-9]*)-[a-z0-9_]+", path.name)
        try:
            if (match and not path.is_symlink() and path.is_dir()
                    and (path / ".owner").read_text() == "harness-overlap-v1"
                    and not process_alive(int(match[1]))):
                shutil.rmtree(path)
        except OSError:
            pass
    with tempfile.TemporaryDirectory(prefix="harness-overlap-%d-" % os.getpid()) as folder:
        path = Path(folder)
        (path / ".owner").write_text("harness-overlap-v1")
        yield path


def worktree_snapshot(root, paths, folder, objects, run=git):
    """Snapshot both index and worktree without writing their index or objects."""
    folder.mkdir()
    index = folder / "index"
    env = {"GIT_INDEX_FILE": str(index), "GIT_OBJECT_DIRECTORY": str(folder.parent / "objects"),
           "GIT_ALTERNATE_OBJECT_DIRECTORIES": objects,
           "GIT_AUTHOR_NAME": "harness", "GIT_AUTHOR_EMAIL": "harness@invalid",
           "GIT_COMMITTER_NAME": "harness", "GIT_COMMITTER_EMAIL": "harness@invalid",
           "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z"}
    head = run(root, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    source = Path(os.fsdecode(run(root, "rev-parse", "--path-format=absolute", "--git-path", "index")).rstrip("\n"))
    before = source.read_bytes() if source.exists() else None
    if before is None:
        run(root, "read-tree", head, env=env)
    else:
        index.write_bytes(before)

    commits = {}

    def commit():
        tree = run(root, "write-tree", env=env).decode().strip()
        if tree not in commits:
            commits[tree] = run(root, "commit-tree", tree, "-p", head, "-m", "harness snapshot", env=env).decode().strip()
        return commits[tree]

    staged = commit()
    specs = [":(literal)" + path for path in paths]
    names = run(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", *specs)
    files = sorted(set(names.split(b"\0")) - {b""})
    if len(files) > 10000:
        raise ValueError("snapshot file limit")
    if files:
        run(root, "add", "-A", "--pathspec-from-file=-", "--pathspec-file-nul", env=env,
            input=b"".join(b":(literal)" + name + b"\0" for name in files))
    working = commit() if files else staged
    after = source.read_bytes() if source.exists() else None
    if before != after or head != run(root, "rev-parse", "--verify", "HEAD^{commit}").decode().strip():
        raise ValueError("snapshot changed")
    return {"head": head, "commits": sorted({staged, working}), "env": env}


def inspect_overlap(root, paths, base="HEAD"):
    """ATC-style local overlap and test merges; missing coverage stays unknown."""
    root = root.resolve()
    result = {"complete": True, "state": "clear", "peers": [], "limitations": []}
    deadline = time.monotonic() + 20

    def run(*args, **kwargs):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired("git", 20)
        return git(*args, timeout=remaining, **kwargs)

    try:
        for name in paths:
            within(root, name)
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise ValueError("invalid scope")
        top = Path(os.fsdecode(run(root, "rev-parse", "--show-toplevel")).rstrip("\n")).resolve()
        if root != top:
            raise ValueError("overlap requires worktree root")
        revision = run(root, "rev-parse", "--verify", "--end-of-options", base + "^{commit}").decode().strip()
        result["base"] = revision
        records = run(root, "worktree", "list", "--porcelain", "-z").split(b"\0\0")
        peers = []
        for record in records:
            fields = record.split(b"\0")
            if not fields or not fields[0].startswith(b"worktree ") or b"bare" in fields:
                continue
            path = Path(os.fsdecode(fields[0][9:]))
            if path.resolve() != root:
                peers.append(path)
        if not peers:
            return result
        if len(peers) > 20:
            result["limitations"].append("peerLimit")
        objects = os.fsdecode(run(root, "rev-parse", "--path-format=absolute", "--git-path", "objects")).rstrip("\n")
        if os.environ.get("GIT_ALTERNATE_OBJECT_DIRECTORIES"):
            objects += os.pathsep + os.environ["GIT_ALTERNATE_OBJECT_DIRECTORIES"]
        with overlap_scratch() as folder:
            (folder / "objects").mkdir()
            mine = worktree_snapshot(root, paths, folder / "mine", objects, run)
            result["snapshot"] = digest("".join(mine["commits"]).encode())
            merges, changes = {}, {}
            specs = [":(literal)" + path for path in paths]
            for number, peer in enumerate(peers[:20]):
                row = {"worktree": str(peer), "state": "unknown", "files": []}
                result["peers"].append(row)
                try:
                    theirs = worktree_snapshot(peer, paths, folder / str(number), objects, run)
                    row["snapshot"] = digest("".join(theirs["commits"]).encode())
                    common = run(root, "merge-base", "--octopus", revision, mine["head"], theirs["head"]).decode().strip()

                    def changed(snapshot):
                        key = (common, tuple(snapshot["commits"]))
                        if key in changes:
                            return changes[key]
                        names = set()
                        for commit in snapshot["commits"]:
                            names.update(run(root, "diff", "--no-ext-diff", "--no-textconv", "--no-renames",
                                             "--name-only", "-z", common, commit, "--", *specs,
                                             env=mine["env"]).split(b"\0"))
                        changes[key] = names - {b""}
                        return changes[key]

                    shared = changed(mine) & changed(theirs)
                    row["files"] = sorted(os.fsdecode(name) for name in shared)
                    row["state"] = "overlap" if shared else "clear"
                    if shared:
                        for first in mine["commits"]:
                            for second in theirs["commits"]:
                                key = (first, second)
                                if key not in merges:
                                    raw = run(root, "merge-tree", "--write-tree", "--name-only", "--no-messages", "-z",
                                              first, second, ok=(0, 1), env=mine["env"])
                                    parts = raw.split(b"\0")
                                    if not re.fullmatch(rb"[0-9a-f]{40}|[0-9a-f]{64}", parts[0]):
                                        raise ValueError("invalid merge output")
                                    merges[key] = set(parts[1:]) - {b""}
                                if merges[key] & shared:
                                    row["state"] = "conflict"
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    row["state"] = "unknown"
                    result["limitations"].append("peerUnavailable")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        result["limitations"].append("snapshotUnavailable")
    result["limitations"] = sorted(set(result["limitations"]))
    result["complete"] = not result["limitations"]
    states = {row["state"] for row in result["peers"]}
    result["state"] = ("unknown" if not result["complete"] else "conflict" if "conflict" in states
                       else "overlap" if "overlap" in states else "clear")
    return result


def overlap_preview(report, limit=6000):
    result = dict(report, peers=[], limitations=list(report["limitations"]))
    result["omitted_peers"] = 0
    remaining = max(512, limit) - len(json.dumps(result, ensure_ascii=False)) - 96
    for number, peer in enumerate(report["peers"]):
        row = dict(peer, files=[], omitted_files=len(peer["files"]))
        remaining -= len(json.dumps(row, ensure_ascii=False)) + 2
        if remaining < 0:
            result["omitted_peers"] = len(report["peers"]) - number
            result["complete"] = False
            result["state"] = "unknown"
            result["limitations"].append("previewLimit")
            break
        for name in peer["files"]:
            size = len(json.dumps(name, ensure_ascii=False)) + 2
            if size > remaining:
                break
            row["files"].append(name)
            row["omitted_files"] -= 1
            remaining -= size
        result["peers"].append(row)
    return result


def save_pack(root, mode, items, cache=CACHE, overlap=None):
    root = root.resolve()
    pack = {"schema": "harness-context-v1", "root": str(root), "mode": mode, "items": items}
    if overlap is not None:
        pack["overlap"] = overlap
    raw = (json.dumps(pack, ensure_ascii=False, sort_keys=True) + "\n").encode()
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (digest(raw) + ".json")
    if not path.exists() or path.read_bytes() != raw:
        fd, temporary = tempfile.mkstemp(dir=cache, prefix=".pack-")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return path, pack


def preview(path, pack, limit=12000, since=None):
    previous = set()
    if since:
        old_raw = Path(since).read_bytes()
        if Path(since).stem != digest(old_raw):
            raise ValueError("--since pack hash mismatch")
        old = json.loads(old_raw)
        if old.get("root") != pack["root"] or old.get("mode") != pack["mode"]:
            raise ValueError("--since root or mode mismatch")
        previous = {(i["path"], i.get("first"), i.get("last"), i["sha256"]) for i in old["items"]}
    overlap = overlap_preview(pack["overlap"], limit // 2) if "overlap" in pack else None
    rows, remaining = [], max(0, limit - len(json.dumps(overlap))) if overlap is not None else limit
    for item in pack["items"]:
        row = {k: v for k, v in item.items() if k != "text"}
        key = (item["path"], item.get("first"), item.get("last"), item["sha256"])
        if key in previous:
            row["unchanged_from"] = str(since)
        else:
            row["text"] = item["text"][:remaining]
            row["omitted_chars"] = len(item["text"]) - len(row["text"])
            remaining -= len(row["text"])
        rows.append(row)
    result = {"schema": pack["schema"], "artifact": str(path) if path else None, "root": pack["root"],
              "preview_complete": all(not r.get("omitted_chars") for r in rows), "items": rows}
    if overlap is not None:
        result["overlap"] = overlap
        result["preview_complete"] &= not overlap["omitted_peers"] and not any(peer["omitted_files"] for peer in overlap["peers"])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--max-chars", type=int, default=12000)
    parser.add_argument("--since", type=Path)
    parser.add_argument("--no-cache", action="store_true", help="read-only agents: print excerpts without saving a pack")
    commands = parser.add_subparsers(dest="mode", required=True)
    reads = commands.add_parser("read")
    reads.add_argument("--file", action="append", required=True)
    diffs = commands.add_parser("diff")
    diffs.add_argument("--path", action="append", required=True)
    diffs.add_argument("--base", default="HEAD")
    diffs.add_argument("--overlap", action="store_true", help="test local peer snapshots; no network or index writes")
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.max_chars <= 100000:
            raise ValueError("--max-chars must be 1..100000")
        root = args.root.expanduser().resolve()
        items = read_items(root, args.file) if args.mode == "read" else diff_items(root, args.path, args.base)
        overlap = inspect_overlap(root, args.path, args.base) if args.mode == "diff" and args.overlap else None
        if args.no_cache:
            path, pack = None, {"schema": "harness-context-v1", "root": str(root), "mode": args.mode, "items": items}
            if overlap is not None:
                pack["overlap"] = overlap
        else:
            path, pack = save_pack(root, args.mode, items, overlap=overlap)
        output = preview(path, pack, args.max_chars, args.since)
        print(json.dumps(output, ensure_ascii=False))
        return 2 if output.get("overlap", {}).get("state") in ("conflict", "unknown") else 0
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"error": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
