"""Deterministic Luau type discovery and editing for harness projects."""

from __future__ import annotations

import hashlib
import json
import os
import re
import glob
import tempfile
from dataclasses import dataclass


LUAU_SUFFIXES = (".luau", ".lua")
TYPE_START = re.compile(r"(?m)^(export[ \t]+)?type[ \t]+([A-Za-z_][A-Za-z0-9_]*)\b")
ACCESSOR = re.compile(
    r"(?m)^[ \t]*function[ \t]+m\.([A-Za-z_][A-Za-z0-9_]*)[ \t]*\(([^\n)]*)\)(?:[ \t]*:[ \t]*([^\n]+))?"
)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "surrogateescape")).hexdigest()


def relpath(path: str, root: str) -> str:
    return os.path.relpath(os.path.realpath(path), os.path.realpath(root)).replace(os.sep, "/")


def _masked_source(source: str) -> str:
    """Replace comments and strings with spaces while preserving newlines."""
    out = list(source)
    i = 0
    n = len(source)

    def blank(begin: int, end: int) -> None:
        for j in range(begin, end):
            if out[j] not in ("\n", "\r"):
                out[j] = " "

    while i < n:
        if source.startswith("--", i):
            long_match = re.match(r"--\[(=*)\[", source[i:])
            if long_match:
                equals = long_match.group(1)
                close = "]" + equals + "]"
                end = source.find(close, i + long_match.end())
                end = n if end < 0 else end + len(close)
                blank(i, end)
                i = end
                continue
            end = source.find("\n", i)
            end = n if end < 0 else end
            blank(i, end)
            i = end
            continue
        quote = source[i]
        if quote in ("'", '"'):
            j = i + 1
            while j < n:
                if source[j] == "\\":
                    j += 2
                    continue
                if source[j] == quote:
                    j += 1
                    break
                j += 1
            blank(i, min(j, n))
            i = min(j, n)
            continue
        long_match = re.match(r"\[(=*)\[", source[i:])
        if long_match:
            equals = long_match.group(1)
            close = "]" + equals + "]"
            end = source.find(close, i + long_match.end())
            end = n if end < 0 else end + len(close)
            blank(i, end)
            i = end
            continue
        if quote == "`":
            j = i + 1
            while j < n:
                if source[j] == "\\":
                    j += 2
                    continue
                if source[j] == "`":
                    j += 1
                    break
                j += 1
            blank(i, min(j, n))
            i = min(j, n)
            continue
        i += 1
    return "".join(out)


def _declaration_end(masked: str, match: re.Match[str]) -> int:
    start = match.start()
    equals = masked.find("=", match.end())
    if equals < 0:
        return masked.find("\n", match.end()) if "\n" in masked[match.end() :] else len(masked)
    depth = {"{": 0, "(": 0, "[": 0}
    closing = {"}": "{", ")": "(", "]": "["}
    i = equals + 1
    expression_seen = False
    while i < len(masked):
        char = masked[i]
        if char in depth:
            depth[char] += 1
            expression_seen = True
        elif char in closing:
            opener = closing[char]
            depth[opener] = max(0, depth[opener] - 1)
            expression_seen = True
        elif char == "\n" and all(value == 0 for value in depth.values()):
            current = masked[equals + 1 : i].strip()
            rest_match = re.match(r"[ \t\r\n]*([^\n]*)", masked[i + 1 :])
            next_line = rest_match.group(1).strip() if rest_match else ""
            if current:
                expression_seen = True
            if expression_seen and not next_line.startswith(("|", "&", ",", "->")):
                return i
        elif not char.isspace():
            expression_seen = True
        i += 1
    return len(masked)


def format_declaration(source: str) -> str:
    lines = source.strip().splitlines()
    formatted = []
    for line in lines:
        line = line.rstrip()
        leading = len(line) - len(line.lstrip(" "))
        if leading:
            line = "\t" * (leading // 4) + " " * (leading % 4) + line.lstrip(" ")
        formatted.append(line)
    return "\n".join(formatted)


def _split_members(declaration: str) -> dict[str, str]:
    masked = _masked_source(declaration)
    equals = masked.find("=")
    brace = masked.find("{", equals + 1)
    if equals < 0 or brace < 0:
        return {}
    depth = {"{": 1, "(": 0, "[": 0}
    closing = {"}": "{", ")": "(", "]": "["}
    segments = []
    segment_start = brace + 1
    i = brace + 1
    while i < len(masked):
        char = masked[i]
        if char in depth:
            depth[char] += 1
        elif char in closing:
            opener = closing[char]
            depth[opener] = max(0, depth[opener] - 1)
            if char == "}" and depth["{"] == 0:
                segments.append(declaration[segment_start:i])
                break
        elif char == "," and depth == {"{": 1, "(": 0, "[": 0}:
            segments.append(declaration[segment_start:i])
            segment_start = i + 1
        i += 1
    members = {}
    for segment in segments:
        text = " ".join(part.strip() for part in segment.strip().splitlines()).strip()
        if not text:
            continue
        found = re.match(r"(?:\[\s*[\"']([^\"']+)[\"']\s*\]|([A-Za-z_][A-Za-z0-9_]*))\s*:\s*(.+)$", text)
        if found:
            name = found.group(1) or found.group(2)
            member = "%s: %s" % (name, found.group(3).strip())
            members[name] = member
    return members


@dataclass(frozen=True)
class Declaration:
    name: str
    exported: bool
    start: int
    end: int
    text: str
    fingerprint: str
    members: dict[str, str]

    def as_cache(self, metadata: dict[str, str]) -> dict:
        qualified = qualify(metadata, self.name)
        return {
            "declaration": self.text,
            "exported": self.exported,
            "fingerprint": self.fingerprint,
            "kind": metadata["kind"],
            "members": self.members,
            "module": metadata.get("module", ""),
            "name": self.name,
            "owner": metadata["owner"],
            "path": metadata["path"],
            "place": metadata.get("place", "shared"),
            "qualified": qualified,
        }


def parse_declarations(source: str) -> list[Declaration]:
    masked = _masked_source(source)
    declarations = []
    for match in TYPE_START.finditer(masked):
        end = _declaration_end(masked, match)
        text = format_declaration(source[match.start() : end])
        if "=" not in text:
            continue
        declarations.append(
            Declaration(
                name=match.group(2),
                exported=bool(match.group(1)),
                start=match.start(),
                end=end,
                text=text,
                fingerprint=sha256_text(text),
                members=_split_members(text),
            )
        )
    return declarations


def declaration_signature(source: str) -> list[tuple[str, bool, str]]:
    return [(item.name, item.exported, item.fingerprint) for item in parse_declarations(source)]


def _source_roots(root: str) -> list[tuple[str, str]]:
    roots = []
    shared = os.path.join(root, "shared", "src")
    if os.path.isdir(shared):
        roots.append(("shared", shared))
    places = os.path.join(root, "places")
    if os.path.isdir(places):
        for place in sorted(os.listdir(places)):
            source = os.path.join(places, place, "src")
            if os.path.isdir(source):
                roots.append((place, source))
    return roots


def _luau_files(directory: str, recursive: bool = True) -> list[str]:
    if not os.path.isdir(directory):
        return []
    found = []
    if recursive:
        for base, dirs, files in os.walk(directory):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            for name in sorted(files):
                if name.endswith(LUAU_SUFFIXES):
                    found.append(os.path.join(base, name))
    else:
        for name in sorted(os.listdir(directory)):
            path = os.path.join(directory, name)
            if os.path.isfile(path) and name.endswith(LUAU_SUFFIXES):
                found.append(path)
    return found


def discover_sources(root: str) -> list[dict[str, str]]:
    root = os.path.realpath(root)
    records = {}
    for place, source_root in _source_roots(root):
        types_root = os.path.join(source_root, "ReplicatedStorage", "Types")
        for path in _luau_files(types_root):
            relative = os.path.relpath(path, types_root).replace(os.sep, "/")
            module = relative.rsplit(".", 1)[0]
            owner = module.split("/", 1)[0]
            records[os.path.realpath(path)] = {
                "kind": "feature",
                "module": module,
                "owner": owner,
                "path": relpath(path, root),
                "place": place,
            }
        for kind, relative_root in (
            ("service", os.path.join("ServerScriptService", "Services")),
            ("controller", os.path.join("StarterPlayer", "StarterPlayerScripts", "Controllers")),
        ):
            provider_root = os.path.join(source_root, relative_root)
            for path in _luau_files(provider_root):
                relative = os.path.relpath(path, provider_root).replace(os.sep, "/")
                parts = relative.split("/")
                first = parts[0]
                owner = first.rsplit(".", 1)[0] if len(parts) == 1 else first
                module_parts = parts[1:] if len(parts) > 1 else []
                module = "/".join(module_parts)
                if module.endswith(".luau"):
                    module = module[: -len(".luau")]
                elif module.endswith(".lua"):
                    module = module[: -len(".lua")]
                if module == "init":
                    module = ""
                data_folder = os.path.dirname(path)
                is_data = os.path.exists(os.path.join(data_folder, "Default.luau")) and os.path.exists(
                    os.path.join(data_folder, "Development.luau")
                )
                metadata_kind = "data" if is_data and os.path.basename(path) in (
                    "Default.luau",
                    "Development.luau",
                    "Typed.luau",
                ) else kind
                records[os.path.realpath(path)] = {
                    "kind": metadata_kind,
                    "module": module,
                    "owner": owner,
                    "path": relpath(path, root),
                    "place": place,
                }
    plugins_root = os.path.join(root, "plugins")
    if os.path.isdir(plugins_root):
        for owner in sorted(os.listdir(plugins_root)):
            source_root = os.path.join(plugins_root, owner, "src")
            for path in _luau_files(source_root):
                relative = os.path.relpath(path, source_root).replace(os.sep, "/")
                module = re.sub(r"\.(?:luau|lua)$", "", relative)
                if module == "init":
                    module = ""
                records[os.path.realpath(path)] = {
                    "kind": "plugin",
                    "module": module,
                    "owner": owner,
                    "path": relpath(path, root),
                    "place": "shared",
                }
    return [records[path] for path in sorted(records, key=lambda item: records[item]["path"])]


def qualify(metadata: dict[str, str], type_name: str) -> str:
    if metadata["kind"] == "data":
        return "PlayerData.%s" % type_name
    owner = metadata["owner"]
    if metadata["kind"] == "feature":
        return "%s.%s" % (owner, type_name)
    module = metadata.get("module", "")
    if module:
        leaf = module[:-5] if module.endswith("/init") else module
        return "%s/%s.%s" % (owner, leaf, type_name)
    return "%s.%s" % (owner, type_name)


def _project_map_fingerprint(root: str) -> str:
    digest = hashlib.sha256()
    project_files = []
    for name in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        if name.endswith(".project.json"):
            project_files.append(os.path.join(root, name))
    for path in project_files:
        digest.update(os.path.basename(path).encode("utf-8") + b"\0")
        try:
            with open(path, "rb") as handle:
                digest.update(handle.read())
        except OSError:
            digest.update(b"missing")
        digest.update(b"\0")
    return digest.hexdigest()


def build_index(root: str, overlay: dict[str, str | None] | None = None) -> dict:
    root = os.path.realpath(root)
    overlay = {os.path.realpath(path): value for path, value in (overlay or {}).items()}
    definitions = []
    source_fingerprints = {}
    accessors = []
    discovered = {os.path.realpath(os.path.join(root, item["path"])): item for item in discover_sources(root)}
    for path, content in overlay.items():
        if content is None:
            discovered.pop(path, None)
            continue
        if path not in discovered:
            metadata = metadata_for_path(root, path)
            if metadata:
                discovered[path] = metadata
    for path in sorted(discovered, key=lambda item: discovered[item]["path"]):
        metadata = discovered[path]
        try:
            if path in overlay:
                source = overlay[path]
            else:
                with open(path, encoding="utf-8") as handle:
                    source = handle.read()
        except OSError:
            continue
        if source is None:
            continue
        parsed = parse_declarations(source)
        entries = [item.as_cache(metadata) for item in parsed]
        definitions.extend(entries)
        accessor_entries = []
        if metadata["kind"] == "data" and os.path.basename(path) == "Typed.luau":
            for found in ACCESSOR.finditer(_masked_source(source)):
                name = found.group(1)
                signature = "%s(%s)%s" % (
                    name,
                    found.group(2).strip(),
                    (": " + found.group(3).strip()) if found.group(3) else "",
                )
                accessor_entries.append(
                    {
                        "fingerprint": sha256_text(signature),
                        "name": name,
                        "path": metadata["path"],
                        "place": metadata["place"],
                        "signature": signature,
                    }
                )
        accessors.extend(accessor_entries)
        normalized = json.dumps(
            {
                "accessors": accessor_entries,
                "definitions": [(item["qualified"], item["fingerprint"]) for item in entries],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        source_fingerprints[metadata["path"]] = sha256_text(normalized)
    qualified_paths = {}
    for item in definitions:
        qualified_paths.setdefault(item["qualified"], set()).add(item["path"])
    place_qualified = {name for name, paths in qualified_paths.items() if len(paths) > 1}
    for item in definitions:
        if item["qualified"] in place_qualified:
            item["qualified"] = "%s:%s" % (item["place"], item["qualified"])
    definitions.sort(key=lambda item: (item["place"], item["kind"], item["owner"], item["module"], item["name"], item["path"]))
    accessors.sort(key=lambda item: (item["place"], item["name"], item["path"]))
    return {
        "accessors": accessors,
        "definitions": definitions,
        "project_root": root,
        "source_map_fingerprint": _project_map_fingerprint(root),
        "sources": source_fingerprints,
    }


def metadata_for_path(root: str, path: str) -> dict[str, str] | None:
    root = os.path.realpath(root)
    path = os.path.realpath(path)
    relative = relpath(path, root)
    plugin = re.match(r"^plugins/([^/]+)/src/(.+)\.(?:luau|lua)$", relative)
    if plugin:
        module = plugin.group(2)
        if module == "init":
            module = ""
        return {
            "kind": "plugin",
            "module": module,
            "owner": plugin.group(1),
            "path": relative,
            "place": "shared",
        }
    found = re.match(r"^(shared|places/([^/]+))/src/(.+)$", relative)
    if not found:
        return None
    place = found.group(2) or "shared"
    logical = found.group(3)
    match = re.match(r"^ReplicatedStorage/Types/([^/]+)(?:/(.*))?\.(?:luau|lua)$", logical)
    if match:
        owner = match.group(1)
        module = owner + (("/" + match.group(2)) if match.group(2) else "")
        return {"kind": "feature", "module": module, "owner": owner, "path": relative, "place": place}
    for kind, prefix in (
        ("service", "ServerScriptService/Services/"),
        ("controller", "StarterPlayer/StarterPlayerScripts/Controllers/"),
    ):
        if logical.startswith(prefix):
            tail = logical[len(prefix) :]
            parts = tail.split("/")
            owner = parts[0].rsplit(".", 1)[0] if len(parts) == 1 else parts[0]
            module = "/".join(parts[1:])
            module = re.sub(r"\.(?:luau|lua)$", "", module)
            if module == "init":
                module = ""
            base = os.path.dirname(path)
            data = os.path.exists(os.path.join(base, "Default.luau")) and os.path.exists(os.path.join(base, "Development.luau"))
            if (data or owner == "PlayerData") and os.path.basename(path) in ("Default.luau", "Development.luau", "Typed.luau"):
                kind = "data"
            return {"kind": kind, "module": module, "owner": owner, "path": relative, "place": place}
    return None


def cache_json(index: dict) -> str:
    return json.dumps(index, sort_keys=True, separators=(",", ":")) + "\n"


def atomic_write(path: str, content: str) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".type_cache_", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.remove(temporary)
        except OSError:
            pass


def gate_key(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:20]


def current_turn(root: str, session_id: str = "") -> dict | None:
    gates = os.path.join(root, "gates")
    if session_id:
        candidates = [os.path.join(gates, ".turn-s%s" % gate_key(session_id))]
    else:
        candidates = glob.glob(os.path.join(gates, ".turn-s*"))
        candidates.sort(key=lambda path: os.path.getmtime(path), reverse=True)
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as handle:
                parts = handle.read().strip().split("|")
        except OSError:
            continue
        if len(parts) == 4 and parts[0] == "v1" and parts[1]:
            session_key = os.path.basename(path).split(".turn-s", 1)[1]
            return {"session_key": session_key, "turn_id": parts[1], "turn_key": gate_key(parts[1])}
    return None


def tool_record_path(root: str, tool: str, turn: dict) -> str:
    return os.path.join(
        root,
        "gates",
        ".%s-s%s-t%s.jsonl" % (tool, turn["session_key"], turn["turn_key"]),
    )


def append_tool_record(root: str, tool: str, record: dict, session_id: str = "") -> str | None:
    turn = current_turn(root, session_id)
    if turn is None:
        return None
    path = tool_record_path(root, tool, turn)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, line.encode("utf-8"))
    finally:
        os.close(descriptor)
    return path


def read_tool_records(root: str, tool: str, session_id: str = "") -> list[dict]:
    turn = current_turn(root, session_id)
    if turn is None:
        return []
    path = tool_record_path(root, tool, turn)
    records = []
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError:
        return []
    for line in lines:
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records
