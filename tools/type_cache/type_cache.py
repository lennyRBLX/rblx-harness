#!/usr/bin/env python3
"""Create, validate, stage, commit, and recover one project type cache."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from contextlib import contextmanager

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
from type_core import atomic_write, build_index, cache_json  # noqa: E402


class CacheError(Exception):
    pass


def cache_path(root: str) -> str:
    key = hashlib.sha256(os.path.realpath(root).encode("utf-8", "surrogateescape")).hexdigest()
    return os.path.join(os.path.expanduser("~/.cache/harness/type_cache"), key + ".json")


def journal_path(root: str) -> str:
    return cache_path(root) + ".journal"


@contextmanager
def project_lock(root: str, timeout: float = 5.0):
    path = cache_path(root) + ".lock"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    deadline = time.monotonic() + timeout
    descriptor = None
    while descriptor is None:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(descriptor, str(os.getpid()).encode("ascii"))
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(path) > 300:
                    os.remove(path)
                    continue
            except OSError:
                continue
            if time.monotonic() >= deadline:
                raise CacheError("type cache transaction lock timed out")
            time.sleep(0.02)
    try:
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.remove(path)
        except OSError:
            pass


def read(root: str) -> dict:
    path = cache_path(root)
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, ValueError) as error:
        raise CacheError("cache read failed: %s" % error)
    required = {"accessors", "definitions", "project_root", "source_map_fingerprint", "sources"}
    if not isinstance(value, dict) or set(value) != required:
        raise CacheError("cache shape is unreadable")
    if os.path.realpath(value.get("project_root", "")) != os.path.realpath(root):
        raise CacheError("cache project root differs")
    if not isinstance(value["definitions"], list) or not isinstance(value["sources"], dict):
        raise CacheError("cache entries are unreadable")
    return value


def verify(root: str) -> tuple[str, dict, dict | None]:
    current = build_index(root)
    try:
        cached = read(root)
    except CacheError as error:
        return "missing" if not os.path.exists(cache_path(root)) else "unreadable", current, {"detail": str(error)}
    if cache_json(cached) != cache_json(current):
        return "stale", current, cached
    return "current", current, cached


def write_index(root: str, index: dict) -> str:
    path = cache_path(root)
    atomic_write(path, cache_json(index))
    return path


def ensure(root: str) -> tuple[str, dict]:
    with project_lock(root):
        recover(root)
        status, current, _ = verify(root)
        if status == "current":
            return "current", current
        write_index(root, current)
        return "rebuilt", current


def stage(root: str, overlay: dict[str, str | None]) -> tuple[str, dict]:
    index = build_index(root, overlay)
    directory = os.path.dirname(cache_path(root))
    os.makedirs(directory, exist_ok=True)
    fd, path = tempfile.mkstemp(prefix=".type_cache_stage_", dir=directory)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(cache_json(index))
        handle.flush()
        os.fsync(handle.fileno())
    return path, index


def commit(root: str, staged: str, locked: bool = False) -> str:
    def install() -> str:
        path = cache_path(root)
        os.replace(staged, path)
        return path

    if locked:
        return install()
    with project_lock(root):
        return install()


def write_journal(root: str, files: dict[str, str | None]) -> str:
    directory = tempfile.mkdtemp(prefix="type_write_recovery_", dir=os.path.dirname(cache_path(root)))
    entries = []
    for index, (path, content) in enumerate(sorted(files.items())):
        backup = None
        if content is not None:
            backup = os.path.join(directory, "%d.source" % index)
            with open(backup, "w", encoding="utf-8") as handle:
                handle.write(content)
        entries.append({"backup": backup, "path": path, "present": content is not None})
    cache_backup = None
    if os.path.exists(cache_path(root)):
        cache_backup = os.path.join(directory, "cache.json")
        shutil.copy2(cache_path(root), cache_backup)
    record = {"cache_backup": cache_backup, "directory": directory, "files": entries}
    atomic_write(journal_path(root), json.dumps(record, sort_keys=True) + "\n")
    return journal_path(root)


def clear_journal(root: str) -> None:
    path = journal_path(root)
    directory = None
    try:
        with open(path, encoding="utf-8") as handle:
            directory = json.load(handle).get("directory")
    except (OSError, ValueError, AttributeError):
        pass
    try:
        os.remove(path)
    except OSError:
        pass
    if directory:
        shutil.rmtree(directory, ignore_errors=True)


def recover(root: str) -> bool:
    path = journal_path(root)
    if not os.path.exists(path):
        return False
    try:
        with open(path, encoding="utf-8") as handle:
            record = json.load(handle)
        for entry in record["files"]:
            target = entry["path"]
            if entry["present"]:
                with open(entry["backup"], encoding="utf-8") as source:
                    atomic_write(target, source.read())
            else:
                try:
                    os.remove(target)
                except OSError:
                    pass
        cache_backup = record.get("cache_backup")
        if cache_backup:
            shutil.copy2(cache_backup, cache_path(root))
        else:
            try:
                os.remove(cache_path(root))
            except OSError:
                pass
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise CacheError("recovery failed: %s" % error)
    clear_journal(root)
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("ensure", "verify", "recover"))
    parser.add_argument("--root", default=os.getcwd())
    args = parser.parse_args(argv)
    try:
        if args.action == "ensure":
            status, _ = ensure(args.root)
            print("OK|%s" % status)
            return 0
        if args.action == "recover":
            print("OK|%s" % ("recovered" if recover(args.root) else "current"))
            return 0
        status, _, _ = verify(args.root)
        print(("OK|current" if status == "current" else "STALE|%s" % status))
        return 0 if status == "current" else 2
    except CacheError as error:
        print("ENV|%s" % error)
        return 3
    except Exception as error:
        print("ENV|%s: %s" % (type(error).__name__, error))
        return 3


if __name__ == "__main__":
    sys.exit(main())
