#!/usr/bin/env python3
"""Bounded source excerpts and immutable scoped Git review evidence.

Use read --file path[:first:last] (repeatable), or diff --path path
(repeatable). --since reuses a pack already present in this agent's context.
Full evidence is kept outside the repo; preview omissions are explicit.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

CACHE = Path.home() / ".cache/harness/context"
MAX_FILE_BYTES = 8 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(root, *args, ok=(0,)):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                            env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"), timeout=30)
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


def save_pack(root, mode, items, cache=CACHE):
    root = root.resolve()
    pack = {"schema": "harness-context-v1", "root": str(root), "mode": mode, "items": items}
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
    rows, remaining = [], limit
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
    return {"schema": pack["schema"], "artifact": str(path) if path else None, "root": pack["root"],
            "preview_complete": all(not r.get("omitted_chars") for r in rows), "items": rows}


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
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.max_chars <= 100000:
            raise ValueError("--max-chars must be 1..100000")
        root = args.root.expanduser().resolve()
        items = read_items(root, args.file) if args.mode == "read" else diff_items(root, args.path, args.base)
        if args.no_cache:
            path, pack = None, {"schema": "harness-context-v1", "root": str(root), "mode": args.mode, "items": items}
        else:
            path, pack = save_pack(root, args.mode, items)
        print(json.dumps(preview(path, pack, args.max_chars, args.since), ensure_ascii=False))
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"error": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
