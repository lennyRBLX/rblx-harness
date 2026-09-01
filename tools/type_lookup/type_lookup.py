#!/usr/bin/env python3
"""Batched lookup of project-owned Luau type definitions."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
from type_cache.type_cache import CacheError, ensure  # noqa: E402
from type_core import append_tool_record, sha256_text  # noqa: E402


class QueryError(Exception):
    pass


def _definition_record(item: dict, member: str | None = None) -> dict:
    members = item.get("members", {})
    selected = members if member is None else ({member: members[member]} if member in members else {})
    return {
        "definition": item["fingerprint"],
        "members": {name: sha256_text(text) for name, text in selected.items()},
        "path": item["path"],
        "qualified": item["qualified"],
    }


def _matches(index: dict, query: dict) -> tuple[list[dict], str | None]:
    scope = query.get("scope")
    definitions = index["definitions"]
    if scope == "type":
        name = query.get("type_name")
        if not name:
            raise QueryError("type_name is required")
        return [item for item in definitions if item["name"] == name], None
    if scope in ("service", "controller"):
        owner = query.get(scope)
        if not owner:
            raise QueryError("%s is required" % scope)
        return [
            item for item in definitions
            if item["owner"] == owner and item["kind"] in (scope, "feature", "data")
        ], None
    if scope in ("service_type", "controller_type"):
        kind = scope.split("_", 1)[0]
        owner = query.get(kind)
        name = query.get("type_name")
        if not owner or not name:
            raise QueryError("%s and type_name are required" % kind)
        return [
            item for item in definitions
            if item["owner"] == owner and item["name"] == name and item["kind"] in (kind, "feature", "data")
        ], None
    if scope == "member":
        owner = query.get("provider")
        type_name = query.get("owner_type")
        member = query.get("member")
        kind = query.get("provider_kind")
        if not owner or not type_name or not member:
            raise QueryError("provider, owner_type, and member are required")
        allowed = (kind, "feature") if kind in ("service", "controller") else ("feature", "service", "controller", "data")
        return [
            item for item in definitions
            if item["owner"] == owner and item["name"] == type_name and item["kind"] in allowed and member in item.get("members", {})
        ], member
    if scope == "place":
        place = query.get("place")
        if not place:
            raise QueryError("place is required")
        return [item for item in definitions if item["place"] in ("shared", place)], None
    if scope == "project":
        return list(definitions), None
    raise QueryError("unknown scope %s" % (scope or "nil"))


def _format(matches: list[dict], member: str | None, grouped: bool) -> str:
    if not matches:
        return "nil"
    if member is not None:
        values = []
        for item in matches:
            declaration = item["members"][member]
            values.append((item["qualified"], declaration))
        if len(values) == 1:
            return values[0][1]
        return "\n\n".join("%s\n%s" % pair for pair in values)
    if len(matches) == 1 and not grouped:
        return matches[0]["declaration"]
    if grouped:
        paths = {}
        for item in matches:
            paths.setdefault(item["path"], []).append(item["declaration"])
        return "\n\n".join("@%s\n%s" % (path, "\n\n".join(paths[path])) for path in sorted(paths))
    return "\n\n".join("%s\n%s" % (item["qualified"], item["declaration"]) for item in matches)


def _source_files(root: str) -> list[str]:
    files = []
    for base in (os.path.join(root, "shared", "src"), os.path.join(root, "places"), os.path.join(root, "plugins")):
        if not os.path.isdir(base):
            continue
        for directory, dirs, names in os.walk(base):
            dirs[:] = [name for name in dirs if name not in ("Packages", "_Index") and not name.startswith(".")]
            for name in names:
                if name.endswith((".luau", ".lua")):
                    files.append(os.path.join(directory, name))
    return sorted(files)


def _provided_names(relative: str) -> set[str]:
    names = set()
    found = re.search(r"/(?:Services|Controllers|Types)/([^/.]+)", "/" + relative)
    if found:
        names.add(found.group(1))
    stem = os.path.basename(relative).split(".", 1)[0]
    names.add(os.path.basename(os.path.dirname(relative)) if stem == "init" else stem)
    return {name for name in names if name and name not in ("Default", "Development", "Typed")}


def _dependency_names(source: str) -> set[str]:
    names = {
        found.group(1)
        for found in re.finditer(r"\b(?:Services|Controllers|Types)\s*\.\s*([A-Za-z_]\w*)", source)
    }
    names.update(
        found.group(1)
        for found in re.finditer(r"\bget(?:Child|Service|Controller)\s*\(\s*[\"']([A-Za-z_]\w*)[\"']\s*\)", source)
    )
    names.update(
        found.group(1)
        for found in re.finditer(r"\b[A-Za-z_]\w*Typed\s*\.\s*([A-Za-z_]\w*)", source)
    )
    names.update(
        found.group(1)
        for found in re.finditer(r"\brequire\s*\(\s*script(?:\s*\.\s*Parent)*\s*\.\s*([A-Za-z_]\w*)\s*\)", source)
    )
    return names


def affected(root: str, base: str, additional_paths: list[str] | None = None) -> list[str]:
    changed = subprocess.run(
        ["git", "-C", root, "diff", "--name-only", base, "--", "*.luau", "*.lua"],
        capture_output=True,
        text=True,
    )
    if changed.returncode != 0:
        raise OSError("git diff failed: %s" % (changed.stderr.strip() or base))
    changed_paths = sorted(
        set(line for line in changed.stdout.splitlines() if line)
        | set(additional_paths or [])
    )
    consumers = set(changed_paths)
    files = _source_files(root)
    provided = {path: _provided_names(os.path.relpath(path, root).replace(os.sep, "/")) for path in files}
    dependencies = {}
    for path in files:
        try:
            with open(path, encoding="utf-8") as handle:
                dependencies[path] = _dependency_names(handle.read())
        except OSError:
            dependencies[path] = set()
    frontier = set().union(*(_provided_names(path) for path in changed_paths)) if changed_paths else set()
    while frontier:
        next_frontier = set()
        for path in files:
            relative = os.path.relpath(path, root).replace(os.sep, "/")
            if relative in consumers:
                continue
            if dependencies[path] & frontier:
                consumers.add(relative)
                next_frontier.update(provided[path])
        frontier = next_frontier
    return sorted(consumers)


def execute(root: str, queries: list[dict], session_id: str = "", record: bool = True) -> list[str]:
    if not isinstance(queries, list) or not queries or any(not isinstance(query, dict) for query in queries):
        raise QueryError("queries must be a non-empty list of objects")
    _, index = ensure(root)
    outputs = []
    gate_definitions = []
    for query in queries:
        if query.get("scope") == "affected":
            base = query.get("base")
            if not base:
                raise QueryError("base is required")
            outputs.append("\n".join(affected(root, base)) or "nil")
            continue
        matches, member = _matches(index, query)
        grouped = query.get("scope") in ("service", "controller", "place", "project")
        outputs.append(_format(matches, member, grouped))
        gate_definitions.extend(_definition_record(item, member) for item in matches)
    if record and gate_definitions:
        append_tool_record(root, "type-lookup", {"definitions": gate_definitions}, session_id)
    return outputs


def _queries_from_args(args) -> list[dict]:
    if args.request:
        value = json.loads(args.request)
        return value.get("queries", value) if isinstance(value, dict) else value
    queries = []
    queries.extend({"scope": "type", "type_name": value} for value in args.type_name)
    queries.extend({"scope": "service", "service": value} for value in args.service)
    queries.extend({"scope": "controller", "controller": value} for value in args.controller)
    for value in args.service_type:
        owner, separator, name = value.partition(":")
        if not separator:
            raise QueryError("service-type uses Service:Type")
        queries.append({"scope": "service_type", "service": owner, "type_name": name})
    for value in args.controller_type:
        owner, separator, name = value.partition(":")
        if not separator:
            raise QueryError("controller-type uses Controller:Type")
        queries.append({"scope": "controller_type", "controller": owner, "type_name": name})
    queries.extend({"scope": "place", "place": value} for value in args.place)
    if args.project:
        queries.append({"scope": "project"})
    if args.affected:
        queries.append({"scope": "affected", "base": args.affected})
    return queries


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=os.getcwd())
    parser.add_argument("--session", default=os.environ.get("CODEX_THREAD_ID", ""))
    parser.add_argument("--request")
    parser.add_argument("--type", dest="type_name", action="append", default=[])
    parser.add_argument("--service", action="append", default=[])
    parser.add_argument("--controller", action="append", default=[])
    parser.add_argument("--service-type", action="append", default=[])
    parser.add_argument("--controller-type", action="append", default=[])
    parser.add_argument("--place", action="append", default=[])
    parser.add_argument("--project", action="store_true")
    parser.add_argument("--affected")
    parser.add_argument("--gate", action="store_true")
    args = parser.parse_args(argv)
    try:
        queries = _queries_from_args(args)
        if not queries:
            raise QueryError("at least one query is required")
        outputs = execute(args.root, queries, args.session, record=not args.gate)
        if len(outputs) == 1:
            print(outputs[0])
        else:
            for index, output in enumerate(outputs, 1):
                print("@query %d" % index)
                print(output)
                if index != len(outputs):
                    print()
        return 0
    except QueryError as error:
        print("BLOCKED|WRIT33|%s" % error)
        return 2
    except CacheError as error:
        print("ENV|%s" % error)
        return 3
    except (OSError, ValueError, TypeError) as error:
        print("ENV|%s: %s" % (type(error).__name__, error))
        return 3


if __name__ == "__main__":
    sys.exit(main())
