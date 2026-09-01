#!/usr/bin/env python3
"""Write project-owned Luau declarations and generated owner data."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
HARNESS = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(HARNESS, "shared", "gates"))
import gatelib  # noqa: E402
from type_cache.type_cache import (  # noqa: E402
    CacheError,
    clear_journal,
    commit,
    ensure,
    project_lock,
    recover,
    stage,
    verify,
    write_journal,
)
from type_core import (  # noqa: E402
    append_tool_record,
    atomic_write,
    cache_json,
    metadata_for_path,
    parse_declarations,
    sha256_text,
)

LUAU_LSP = gatelib.bundled_tool_path("luau-lsp")


class WriteError(Exception):
    def __init__(self, rule: str, message: str, operation: int | None = None):
        super().__init__(message)
        self.rule = rule
        self.operation = operation


def _prefix(place: str | None) -> str:
    return os.path.join("places", place, "src") if place else os.path.join("shared", "src")


def _provider_path(root: str, scope: str, owner: str, module: str, place: str | None, create: bool) -> str:
    relative_root = (
        os.path.join("ServerScriptService", "Services")
        if scope == "service"
        else os.path.join("StarterPlayer", "StarterPlayerScripts", "Controllers")
    )
    base = os.path.join(root, _prefix(place), relative_root)
    flat = os.path.join(base, owner + ".luau")
    folder = os.path.join(base, owner)
    if module:
        if not os.path.isdir(folder):
            raise WriteError("TYPE8", "%s %s has no folder form" % (scope, owner))
        logical = module.replace("\\", "/").strip("/")
        candidates = [os.path.join(folder, logical + ".luau"), os.path.join(folder, logical, "init.luau")]
        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate
        if create:
            return candidates[0]
        raise WriteError("TYPE8", "%s/%s module does not exist" % (owner, logical))
    if os.path.exists(flat):
        return flat
    init = os.path.join(folder, "init.luau")
    if os.path.exists(init):
        return init
    raise WriteError("TYPE8", "%s %s does not exist" % (scope, owner))


def _forced_parent(root: str, parent: str | None) -> str | None:
    if parent is None:
        return None
    if not isinstance(parent, str) or not parent.strip():
        raise WriteError("TYPE8", "parent must be a non-empty directory in the project")
    root = os.path.realpath(root)
    candidate = parent if os.path.isabs(parent) else os.path.join(root, parent)
    candidate = os.path.realpath(candidate)
    try:
        inside = os.path.commonpath((root, candidate)) == root
    except ValueError:
        inside = False
    if not inside or candidate == root:
        raise WriteError("TYPE8", "parent must be a directory inside the project")
    if os.path.exists(candidate) and not os.path.isdir(candidate):
        raise WriteError("TYPE8", "parent must be a directory")
    return candidate


def _forced_destination(parent: str, operation: dict) -> str:
    if operation.get("scope") == "data":
        raise WriteError("TYPE8", "parent cannot override generated owner data")
    module = operation.get("module") or ""
    if not isinstance(module, str):
        raise WriteError("TYPE8", "module must be a project-relative path")
    logical = module.replace("\\", "/").strip("/")
    if logical:
        if any(part in ("", ".", "..") for part in logical.split("/")):
            raise WriteError("TYPE8", "module must stay inside parent")
        relative = logical + ".luau"
    else:
        relative = operation.get("owner", "") + ".luau"
    path = os.path.realpath(os.path.join(parent, relative))
    if os.path.commonpath((parent, path)) != parent:
        raise WriteError("TYPE8", "destination must stay inside parent")
    return path


def destination(root: str, operation: dict, create: bool = False, parent: str | None = None) -> str:
    scope = operation.get("scope")
    owner = operation.get("owner")
    if not owner or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", owner):
        raise WriteError("TYPE8", "owner is required and must be an identifier")
    if scope not in ("public", "service", "controller", "data"):
        raise WriteError("TYPE8", "scope must be public, service, controller, or data")
    place = operation.get("place")
    if parent is not None:
        return _forced_destination(parent, operation)
    if scope == "public":
        return os.path.join(root, _prefix(place), "ReplicatedStorage", "Types", owner + ".luau")
    if scope in ("service", "controller"):
        return _provider_path(root, scope, owner, operation.get("module") or "", place, create)
    raise WriteError("TYPE8", "scope must be public, service, controller, or data")


def _read(path: str, overlay: dict[str, str | None]) -> str | None:
    path = os.path.realpath(path)
    if path in overlay:
        return overlay[path]
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return None


def _find(source: str | None, name: str):
    if source is None:
        return None
    matches = [item for item in parse_declarations(source) if item.name == name]
    if len(matches) > 1:
        raise WriteError("TYPE8", "%s is declared more than once" % name)
    return matches[0] if matches else None


def _validated_declaration(operation: dict, public: bool) -> str:
    declaration = operation.get("declaration")
    name = operation.get("type_name")
    if not name or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise WriteError("TYPE8", "type_name is required and must be an identifier")
    if not isinstance(declaration, str):
        raise WriteError("TYPE8", "declaration is required")
    parsed = parse_declarations(declaration)
    if len(parsed) != 1 or parsed[0].name != name or parsed[0].text.strip() != declaration.strip():
        raise WriteError("TYPE8", "declaration must contain exactly %s" % name)
    if public and not parsed[0].exported:
        raise WriteError("TYPE8", "%s must be exported in the feature Types module" % name)
    if not public and parsed[0].exported:
        raise WriteError("TYPE8", "%s is private and uses a local type declaration" % name)
    return parsed[0].text


def _insert(source: str | None, declaration: str, public: bool) -> str:
    if source is None:
        return declaration + ("\n\nreturn {}\n" if public else "\n")
    returns = list(re.finditer(r"(?m)^[ \t]*return\b", source))
    point = returns[-1].start() if returns else len(source)
    before = source[:point].rstrip()
    after = source[point:].lstrip("\r\n")
    return before + ("\n\n" if before else "") + declaration + ("\n\n" + after if after else "\n")


def _replace(source: str, existing, declaration: str) -> str:
    return source[: existing.start] + declaration + source[existing.end :]


def _delete(source: str, existing) -> str:
    before = source[: existing.start].rstrip()
    after = source[existing.end :].lstrip("\r\n")
    return before + ("\n\n" if before and after else "") + after


def _apply_type(
    root: str,
    operation: dict,
    overlay: dict[str, str | None],
    parent: str | None = None,
) -> tuple[str, str | None, str, str | None]:
    action = operation.get("action")
    if action not in ("create", "update", "move", "delete"):
        raise WriteError("TYPE8", "action must be create, update, move, or delete")
    name = operation.get("type_name")
    if not name:
        raise WriteError("TYPE8", "type_name is required")
    if action == "move":
        source_spec = operation.get("from")
        if not isinstance(source_spec, dict):
            raise WriteError("TYPE8", "move requires from")
        source_operation = dict(source_spec, type_name=name)
        source_path = destination(root, source_operation)
        source_text = _read(source_path, overlay)
        existing = _find(source_text, name)
        if existing is None:
            raise WriteError("TYPE8", "%s does not exist at the move source" % name)
        declaration = operation.get("declaration") or existing.text
        operation = dict(operation, declaration=declaration)
        target_path = destination(root, operation, create=True, parent=parent)
        target_text = _read(target_path, overlay)
        if _find(target_text, name) is not None:
            raise WriteError("TYPE8", "%s already exists at the move destination" % name)
        final_declaration = _validated_declaration(operation, operation.get("scope") == "public")
        overlay[os.path.realpath(source_path)] = _delete(source_text, existing)
        overlay[os.path.realpath(target_path)] = _insert(target_text, final_declaration, operation.get("scope") == "public")
        return "moved", final_declaration, os.path.realpath(target_path), os.path.realpath(source_path)

    path = destination(root, operation, create=action == "create", parent=parent)
    source = _read(path, overlay)
    existing = _find(source, name)
    if action == "delete":
        if existing is None:
            raise WriteError("TYPE8", "%s does not exist" % name)
        overlay[os.path.realpath(path)] = _delete(source, existing)
        return "deleted", None, os.path.realpath(path), None
    declaration = _validated_declaration(operation, operation.get("scope") == "public")
    if action == "create":
        if existing is not None:
            raise WriteError("TYPE8", "%s already exists" % name)
        overlay[os.path.realpath(path)] = _insert(source, declaration, operation.get("scope") == "public")
        return "created", declaration, os.path.realpath(path), None
    if existing is None:
        raise WriteError("TYPE8", "%s does not exist" % name)
    if existing.text == declaration:
        return "unchanged", declaration, os.path.realpath(path), None
    overlay[os.path.realpath(path)] = _replace(source, existing, declaration)
    return "updated", declaration, os.path.realpath(path), None


def _prepare_data(root: str, operations: list[tuple[int, dict]], overlay: dict[str, str | None]) -> list[tuple[int, str, str | None, str, str, bool]]:
    if not operations:
        return []
    temporary = tempfile.mkdtemp(prefix="type_write_data_")
    try:
        source_services = os.path.join(root, "shared", "src", "ServerScriptService", "Services")
        target_services = os.path.join(temporary, "shared", "src", "ServerScriptService", "Services")
        if os.path.isdir(source_services):
            shutil.copytree(source_services, target_services, dirs_exist_ok=True)
        else:
            os.makedirs(target_services, exist_ok=True)
        results = []
        destination_dir = os.path.join(source_services, "PlayerData")
        data_write = os.path.join(TOOLS, "data_write", "data_write.py")
        for number, operation in operations:
            owner = operation.get("owner")
            field = operation.get("field_path")
            if not owner or not field:
                raise WriteError("DATA37", "data operation requires owner and field_path", number)
            keypath = owner + "." + field.strip(".")
            action = operation.get("action")
            if action not in ("create", "update", "delete"):
                raise WriteError("TYPE8", "data action must be create, update, or delete", number)
            default = "nil" if action == "delete" else operation.get("default_value")
            development = "nil" if action == "delete" else operation.get("development_value")
            if default is None or development is None:
                raise WriteError("TYPE8", "data operation requires Default and Development values", number)
            default_path = os.path.join(target_services, "PlayerData", "Default.luau")
            try:
                with open(default_path, encoding="utf-8") as handle:
                    before_source = handle.read()
            except OSError:
                before_source = None
            before = _find(before_source, owner)
            result = subprocess.run(
                [sys.executable, data_write, keypath, "--default", str(default), "--dev", str(development), "--root", temporary],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                detail = " ".join((result.stdout + result.stderr).strip().splitlines())[:240]
                match = re.search(r"(?:^|\|)(GATE[1-7]|TYPE\d+|DATA\d+)(?:!?)\|", detail)
                raise WriteError(match.group(1) if match else "GATE4", detail or "data generation failed", number)
            with open(default_path, encoding="utf-8") as handle:
                generated = handle.read()
            after = _find(generated, owner)
            unchanged = (before is None and after is None) or (
                before is not None and after is not None and after.fingerprint == before.fingerprint
            )
            if action == "delete" and unchanged:
                raise WriteError("TYPE8", "%s does not exist" % keypath, number)
            if action == "delete":
                outcome = "deleted"
                declaration = after.text if after else None
            elif before is None:
                outcome = "created"
                declaration = after.text if after else None
            elif after and after.fingerprint == before.fingerprint:
                outcome = "unchanged"
                declaration = after.text
            else:
                outcome = "updated"
                declaration = after.text if after else None
            results.append(
                (
                    number,
                    outcome,
                    declaration,
                    "PlayerData.%s" % owner,
                    os.path.realpath(os.path.join(destination_dir, "Default.luau")),
                    action != "delete",
                )
            )
        generated_dir = os.path.join(target_services, "PlayerData")
        for name in ("Default.luau", "Development.luau", "Typed.luau"):
            path = os.path.join(generated_dir, name)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as handle:
                    overlay[os.path.realpath(os.path.join(destination_dir, name))] = handle.read()
        return results
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _definition_state(index: dict, root: str, path: str, name: str, declaration: str | None = None) -> dict | None:
    relative = os.path.relpath(os.path.realpath(path), root).replace(os.sep, "/")
    for item in index["definitions"]:
        if item["path"] == relative and item["name"] == name and (declaration is None or item["declaration"] == declaration):
            return {
                "definition": item["fingerprint"],
                "members": {name: sha256_text(text) for name, text in item.get("members", {}).items()},
                "path": item["path"],
                "qualified": item["qualified"],
            }
    return None


def _qualified(root: str, path: str, name: str, operation: dict | None = None) -> str:
    metadata = metadata_for_path(root, path)
    if metadata is None:
        if operation is None:
            raise WriteError("TYPE8", "%s has no type ownership" % path)
        owner = operation["owner"]
        module = operation.get("module") or ""
        return "%s/%s.%s" % (owner, module, name) if module else "%s.%s" % (owner, name)
    if metadata["kind"] == "data":
        return "PlayerData.%s" % name
    if metadata["kind"] == "feature" or not metadata.get("module"):
        return "%s.%s" % (metadata["owner"], name)
    return "%s/%s.%s" % (metadata["owner"], metadata["module"], name)


def _unindexed_definition(root: str, outcome: dict) -> dict:
    parsed = parse_declarations(outcome["declaration"] or "")
    if len(parsed) != 1 or parsed[0].name != outcome["type_name"]:
        raise WriteError("TYPE1", "%s is not a complete Luau declaration" % outcome["name"])
    declaration = parsed[0]
    return {
        "definition": declaration.fingerprint,
        "members": {name: sha256_text(text) for name, text in declaration.members.items()},
        "path": os.path.relpath(outcome["path"], root).replace(os.sep, "/"),
        "qualified": outcome["name"],
    }


def _analyze_result(root: str, paths: list[str]) -> None:
    files = sorted(path for path in paths if path.endswith((".luau", ".lua")) and os.path.exists(path))
    if not files:
        return
    lsp = LUAU_LSP
    if not os.path.exists(lsp):
        lsp = shutil.which("luau-lsp") or ""
    definitions = os.path.join(TOOLS, "globalTypes.d.luau")
    if not lsp or not os.path.exists(definitions):
        raise CacheError("luau-lsp analysis is unavailable")
    command = [
        lsp,
        "analyze",
        "--flag:LuauSolverV2=true",
        "--no-strict-dm-types",
        "--platform",
        "roblox",
        "--definitions",
        "@roblox=" + definitions,
        "--base-luaurc",
        os.path.join(TOOLS, "base.luaurc"),
        "--ignore",
        "**/_Index/**",
        "--ignore",
        "**/Packages/**",
        "--ignore",
        "**/Modules/**",
    ]
    with tempfile.TemporaryDirectory(prefix="type_write_analysis_") as temporary:
        project = os.path.join(root, "default.project.json")
        argon = shutil.which("argon")
        if os.path.exists(project) and argon:
            sourcemap = os.path.join(temporary, "sourcemap.json")
            mapped = subprocess.run([argon, "sourcemap", project, "-o", sourcemap], capture_output=True, text=True)
            if mapped.returncode == 0 and os.path.exists(sourcemap):
                command += ["--sourcemap", sourcemap]
        result = subprocess.run(command + files, capture_output=True, text=True)
    if result.returncode not in (0, 1):
        raise CacheError("luau-lsp analysis failed: %s" % " ".join((result.stdout + result.stderr).splitlines())[:200])
    diagnostics = [
        line
        for line in (result.stdout + result.stderr).splitlines()
        if re.match(r"^.+\(\d+,\d+\): (?:SyntaxError|TypeError):", line)
    ]
    if diagnostics:
        raise WriteError("TYPE1", diagnostics[0][:240])


def execute(root: str, operations: list[dict], session_id: str = "", parent: str | None = None) -> list[dict]:
    if not isinstance(operations, list) or not operations or any(not isinstance(operation, dict) for operation in operations):
        raise WriteError("TYPE8", "operations must be a non-empty list of objects")
    root = os.path.realpath(root)
    parent = _forced_parent(root, parent)
    if parent is not None:
        for number, operation in enumerate(operations, 1):
            if operation.get("scope") == "data":
                raise WriteError("TYPE8", "parent cannot override generated owner data", number)
    _, base_index = ensure(root)
    overlay: dict[str, str | None] = {}
    outcomes = []
    data_operations = []
    for number, operation in enumerate(operations, 1):
        if operation.get("scope") == "data":
            data_operations.append((number, operation))
            continue
        try:
            outcome, declaration, path, source_name = _apply_type(root, operation, overlay, parent)
        except WriteError as error:
            error.operation = number
            raise
        qualified = _qualified(root, path, operation["type_name"], operation if parent is not None else None)
        outcomes.append(
            {
                "declaration": declaration,
                "name": qualified,
                "number": number,
                "outcome": outcome,
                "path": path,
                "source": source_name,
                "show_declaration": declaration is not None,
                "type_name": operation["type_name"],
            }
        )
    outcomes.extend(
        {
            "declaration": declaration,
            "name": name,
            "number": number,
            "outcome": outcome,
            "path": path,
            "source": None,
            "show_declaration": show_declaration,
            "type_name": name.split(".", 1)[1],
        }
        for number, outcome, declaration, name, path, show_declaration in _prepare_data(root, data_operations, overlay)
    )
    outcomes.sort(key=lambda item: item["number"])
    staged_path, resulting_index = stage(root, overlay)
    definitions = []
    for outcome in outcomes:
        indexed = _definition_state(resulting_index, root, outcome["path"], outcome["type_name"], outcome["declaration"])
        if outcome["declaration"] is not None:
            if indexed is None:
                if parent is None or metadata_for_path(root, outcome["path"]) is not None:
                    try:
                        os.remove(staged_path)
                    except OSError:
                        pass
                    raise WriteError("TYPE1", "%s is not a complete Luau declaration" % outcome["name"])
                definitions.append(_unindexed_definition(root, outcome))
            else:
                outcome["name"] = indexed["qualified"]
                definitions.append(indexed)
        else:
            previous = _definition_state(base_index, root, outcome["path"], outcome["type_name"])
            if previous:
                outcome["name"] = previous["qualified"]
        if outcome["source"]:
            source_path = outcome["source"]
            outcome["source_path"] = os.path.relpath(source_path, root).replace(os.sep, "/")
            previous = _definition_state(base_index, root, source_path, outcome["type_name"])
            if previous:
                outcome["source"] = previous["qualified"]
    try:
        with project_lock(root):
            recover(root)
            _, current_index, _ = verify(root)
            if cache_json(current_index) != cache_json(base_index):
                raise CacheError("project types changed during type_write")
            prior = {}
            for path in overlay:
                try:
                    with open(path, encoding="utf-8") as handle:
                        prior[path] = handle.read()
                except OSError:
                    prior[path] = None
            write_journal(root, prior)
            try:
                for path, source in sorted(overlay.items()):
                    if source is None:
                        try:
                            os.remove(path)
                        except OSError:
                            pass
                    else:
                        atomic_write(path, source)
                _analyze_result(root, list(overlay))
                commit(root, staged_path, locked=True)
            except Exception:
                recover(root)
                raise
            clear_journal(root)
    except Exception:
        try:
            os.remove(staged_path)
        except OSError:
            pass
        raise
    append_tool_record(
        root,
        "type-write",
        {
            "cache": sha256_text(cache_json(resulting_index)),
            "definitions": definitions,
            "operations": [
                {
                    "name": item["name"],
                    "outcome": item["outcome"],
                    "path": os.path.relpath(item["path"], root).replace(os.sep, "/"),
                    "source": item.get("source"),
                    "source_path": item.get("source_path"),
                    "type_name": item["type_name"],
                }
                for item in outcomes
            ],
        },
        session_id,
    )
    return outcomes


def _print(outcomes: list[dict]) -> None:
    if len(outcomes) == 1:
        item = outcomes[0]
        print("OK|%s%s" % (item["outcome"], ("|" + item["name"]) if item["outcome"] == "deleted" else ""))
        if item["declaration"] is not None and item.get("show_declaration", True):
            print(item["declaration"])
        return
    print("OK")
    for index, item in enumerate(outcomes):
        print("%d|%s|%s" % (item["number"], item["outcome"], item["name"]))
        if item["declaration"] is not None and item.get("show_declaration", True):
            print(item["declaration"])
        if index != len(outcomes) - 1:
            print()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=os.getcwd())
    parser.add_argument("--parent", help="force named type destinations into this project directory")
    parser.add_argument("--session", default=os.environ.get("CODEX_THREAD_ID", ""))
    parser.add_argument("--request")
    parser.add_argument("--operation", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        if args.request:
            request = json.loads(args.request)
            operations = request.get("operations", request) if isinstance(request, dict) else request
        else:
            operations = [json.loads(value) for value in args.operation]
        if not isinstance(operations, list) or not operations:
            raise WriteError("TYPE8", "at least one operation is required")
        outcomes = execute(args.root, operations, args.session, args.parent)
        _print(outcomes)
        return 0
    except WriteError as error:
        operation = "|operation %d" % error.operation if error.operation else ""
        print("BLOCKED|%s%s|%s" % (error.rule, operation, error))
        return 2
    except CacheError as error:
        print("ENV|%s" % error)
        return 3
    except Exception as error:
        print("ENV|%s: %s" % (type(error).__name__, error))
        return 3


if __name__ == "__main__":
    sys.exit(main())
