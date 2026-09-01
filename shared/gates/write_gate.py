#!/usr/bin/env python3
"""write-gate — authorization plus mutation-specific Roblox checks.

Read-only operations validate authorization only. Project source mutations
prepare their required local state and check GATE6 once per turn before the
tool-specific payload is inspected.

execute_luau stays for console tests and carries one check [R GATE5].
"""

import os
import re
import shlex
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gatelib  # noqa: E402
import agent_dispatch  # noqa: E402
from type_cache.type_cache import CacheError, ensure as ensure_type_cache  # noqa: E402
from type_core import declaration_signature, metadata_for_path, parse_declarations  # noqa: E402
from source_fix.source_fix import fix_text as fix_source_text  # noqa: E402

TOOLS = gatelib.TOOLS


def compact_remedy(fid, subject, remedy, root, path=None):
    type_write = os.path.join(TOOLS, "type_write", "type_write.py")
    lookup = os.path.join(TOOLS, "type_lookup", "type_lookup.py")
    boilerplate = os.path.join(TOOLS, "create_boilerplate", "create_boilerplate.py")
    if fid == "GATE5":
        return "Edit the Luau file, not code via Roblox Studio; retry."
    if fid == "GATE2":
        if any(token in subject for token in ("symlink", "museum")):
            return "Edit harness source, not %s; retry." % (gatelib.elide(path, root) if path else subject)
        if " under " in subject:
            return "Rename it, e.g. Server.server.luau or Client.client.luau; retry."
        return "Move the write to shared/src, places/<Place>/src, plugins or tests/<Place>; retry."
    if fid == "GATE3":
        return "Use python3 %s, not a direct %s edit." % (type_write, gatelib.elide(path, root) if path else subject)
    if fid == "GATE6":
        state, _, detail = subject.partition(":")
        return gatelib.gate6_instruction(root, state.strip(), detail.strip())
    if fid == "GATE4":
        if "type cache" in subject:
            return "Rebuild the type cache, verify it, and retry: python3 %s ensure --root %s" % (
                os.path.join(TOOLS, "type_cache", "type_cache.py"), os.path.realpath(root)
            )
        if "deny_scan" in subject:
            return "Run deny_scan on %s; fix the err; retry." % gatelib.elide(path, root)
        if "replication_audit" in subject:
            return "Run replication_audit on %s; fix the err; retry." % gatelib.elide(path, root)
        if "data_check" in subject:
            return "Run data_check on %s; fix the err; retry." % gatelib.elide(path, root)
        if "corpus" in subject:
            return "Sync the harness API cache: %s" % gatelib.recovery_command(gatelib.RECOVERY_API_SYNC, root)
        if "cache permission" in subject:
            return gatelib.blocker_instruction("cache-write", root)
        if "api_globals" in subject:
            return "Gen API globals: %s" % gatelib.recovery_command(gatelib.RECOVERY_API_GLOBALS, root)
        if "lute" in subject:
            return "Install the harness toolchain, verify it, and retry: %s" % gatelib.recovery_command(
                gatelib.RECOVERY_TOOLCHAIN,
                root,
            )
        return "Run harness verification, fix the failure, and retry: python3 %s" % os.path.join(TOOLS, "tests", "run_verify.py")
    if fid == "DEBUG2":
        if "non-debugger" in subject:
            return "Make this change in a debugger task; retry."
        if "outside tests" in subject:
            return "Move it under tests/<Place>; retry."
        if "no ENABLED" in subject:
            return "Add ENABLED; retry."
        if "header" in subject:
            return "Add ‘what it does’, ‘HOW TO USE’ & ‘delete-when’; retry."
        return "Rename it to tests/{place}/{side}/{mode}.{name}.{side}.luau; retry."
    if fid == "BC4":
        return "Use python3 %s; retry." % boilerplate
    if fid == "TYPE3":
        return "Remove the pragma; .luaurc sets the mode; retry."
    if fid == "OPT8":
        return "Remove native / move the hot path to ServerScriptService; retry."
    if fid == "TYPE8":
        if "outside ReplicatedStorage" in subject:
            return "Move it to ReplicatedStorage/Types/{feature}.luau; retry."
        return "Use python3 %s; retry." % type_write
    if fid == "TYPE9":
        if "without a typed seam" in subject:
            return "Resolve the provider by literal name + cast to its exported type; retry."
        if "computed project-API member" in subject:
            return "Replace computed API access w/ a declared literal member; retry."
        if "dynamic provider seam" in subject:
            return "Resolve it w/ a literal require, Service, Controller or child name; retry."
        return "Add the member w/ python3 %s; retry." % type_write
    if fid == "WRIT33":
        return "Run python3 %s for %s; retry." % (lookup, subject.partition(" has no")[0])
    if fid == "DATA37":
        owner = subject.partition("owner ")[2] or "{owner}"
        return "Replace PlayerData:Get for %s w/ Typed.%s; retry." % (owner, owner)
    if fid == "TYPE7":
        return "Update the canonical type w/ python3 %s in the same diff; retry." % type_write
    if fid == "BC1":
        if "mutates before typeguard" in subject:
            return "Check all remote args before the 1st mutation; retry."
        return "Move the secret to ServerScriptService; retry."
    if fid == "BC3":
        fn = subject.strip()
        return "Replace %s w/ task.%s; retry." % (fn, fn)
    if fid == "BC7":
        return "Remove LocalPlayer; resolve Player on the server; retry."
    if fid == "WRIT18":
        return "Remove %s from game code; use supported Luau structure; retry." % subject
    if fid == "DATA29":
        return "Add RunService:IsStudio() selecting PlayerData.Mock; retry."
    if fid == "OPT11":
        prop = subject.rsplit(" assigned", 1)[0]
        return "Set %s in Roblox Studio; remove the code assignment; retry." % prop
    if fid == "WRIT11":
        return "Remove Request from %s; use the bare intent; retry." % subject
    if fid == "OPT12":
        name = subject.partition("workspace.")[2] or "{name}"
        return 'Use WaitForChild("%s") or FindFirstChild("%s") + nil check; retry.' % (name, name)
    if fid == "DATA1":
        if subject.startswith("Typed."):
            return "Use the Typed accessor matching this Service; retry."
        if "without owner" in subject:
            return "Pass script.Name to PlayerData:Get; retry."
        if "computed owner" in subject:
            return "Use script.Name; retry."
        if "errorId" in remedy:
            return "Set the 1st errorId field to this Service; retry."
        return "Move the read behind its owner Service; retry."
    if fid == "DATA17":
        return "Use ProfileStore:VersionQuery; retry."
    if fid == "DATA30":
        return "Move ProfileStore access into PlayerData; retry."
    if fid == "DATA8":
        if "without errorId" in subject:
            return "Add literal errorId ‘{service}.{migration}’; retry."
        if "computed" in subject:
            return "Use literal errorId ‘{service}.{migration}’; retry."
        return "Use ‘{service}.{migration}’; retry."
    if fid == "DES2":
        return "Move the MarketplaceService call into Payments; retry."
    if fid == "REV6":
        if "SetAttribute" in subject or "GetAttributeChangedSignal" in subject:
            return "Use a Folder + ValueObjects, not a Workspace attr; retry."
        if "Signal" in subject:
            return "Keep Signal in 1 layer; use a remote event across layers; retry."
        if "retained module state" in subject:
            return "Store retained state in replicated instances for late joiners; retry."
        return "Store state in Exclusive / Folder + ValueObjects; send only the event; retry."
    if fid == "WRIT8":
        return "Declare the remote via m.Events + Event package; retry."
    if fid == "DATA23":
        return "Kick on nil StartSessionAsync + OnSessionEnd using ‘PlayerData | reason’; retry."
    if fid == "DATA31":
        return "Put the .Data write right after IsActive w/o a yield; retry."
    if fid == "DATA32":
        return "Call processed before the 1st yield; retry." if "after a yield" in subject else "Use function(message, processed); retry."
    if fid == "DATA33":
        return "Split session + view profile reads into separate fns; retry."
    if fid == "DATA35":
        return "Loop over the template/catalog, not stored profile data; retry."
    if fid == "DATA21":
        if "MessageAsync" in subject:
            return "Remove MessageAsync; use rejoin retry as the receipt queue; retry."
        if "PromptProductPurchaseFinished" in subject:
            return "Move the grant to ProcessReceipt; retry."
        if "NotProcessedYet" in subject:
            return "Return NotProcessedYet before the grant, except dead-profile hold exit; retry."
        return "Return PurchaseGranted only after PurchaseId is in LastSavedData; retry."
    if fid == "DATA36":
        if "handlers" in subject:
            return "Return PurchaseGranted for cached PurchaseId w/o handlers; retry."
        if "below" in subject:
            return "Set PURCHASE_CACHE_MAX ≥ 1000; retry."
        return "Set PURCHASE_CACHE_MAX; evict only past it; retry."
    if fid == "GATE1":
        low = remedy.lower()
        if "utf-8" in low and "key" in low:
            return "Encode the key at %s as valid UTF-8; retry." % subject
        if "utf-8" in low:
            return "Encode %s as valid UTF-8; retry." % subject
        if "not finite" in low or "finite number" in low:
            return "Replace %s w/ a finite number; retry." % subject
        if "cycle" in low:
            return "Remove the cycle at %s; retry." % subject
        if "non-integer" in low or "key type" in low or "positive int key" in low:
            return "Use a string / positive int key at %s; retry." % subject
        if "mixed keys" in low or "all string keys" in low:
            return "Use all string keys / sequential int keys in %s; retry." % subject
        if "sparse" in low or "reindex" in low:
            return "Reindex %s from 1 w/o gaps; retry." % subject
        if "computed key" in low or "literal key" in low:
            return "Use a literal key in %s; retry." % subject
        if "userdata" in low or "primitive fields" in low:
            return "Store primitive fields, not %s; retry." % subject
        if "function" in low or "remove the fn" in low:
            return "Remove the fn from %s; store serializable data; retry." % subject
        if "unparseable" in low or "luau syntax" in low:
            return "Fix Luau syntax in %s; retry." % gatelib.elide(path, root)
        return "Convert %s to a string, finite number, boolean, buffer or serializable table; retry." % subject
    return remedy.rstrip(".") + "; retry."


def block(tool_name, findings, root, **_ignored):
    findings = gatelib.rule_policy.split_findings(findings)["hard"]
    if not findings:
        return 0
    rendered = []
    for path, line, col, fid, subject, remedy in findings:
        action = compact_remedy(fid, subject, remedy, root, path)
        if path is None:
            rendered.append("[%s] %s" % (fid, action))
        else:
            rendered.append("%s:%d: [%s] %s" % (gatelib.elide(path, root), line, fid, action))
    if len(rendered) == 1:
        sys.stderr.write(rendered[0] + "\n")
    else:
        sys.stderr.write("Fix:\n- " + "\n- ".join(rendered) + "\n")
    return 2


def check_gate5(code):
    """Raw-text match on a payload with no CST at all."""
    findings = []
    for n, line in enumerate(code.split("\n"), 1):
        if re.search(r"\.\s*Source\s*=", line):
            findings.append((None, n, 1, "GATE5", "Source assignment", "Studio never writes code - edit the file"))
        m = re.search(r'Instance\.new\s*\(\s*["\'](Script|LocalScript|ModuleScript)["\']', line)
        if m:
            findings.append((None, n, 1, "GATE5", 'Instance.new("%s")' % m.group(1), "Studio never writes code - edit the file"))
    return findings


def museum_names(directory):
    """The scaffolder writes a .gitignore inside Packages/ and Modules/
    listing exactly the museum filenames — consulting it closes the Windows
    byte-copy hole the symlink test cannot see."""
    gi = os.path.join(directory, ".gitignore")
    names = set()
    if os.path.exists(gi):
        try:
            with open(gi, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        names.add(line.rstrip("/"))
        except OSError:
            pass
    return names


def check_gate2(path, cwd):
    root = os.path.realpath(cwd)
    if os.path.islink(path):
        return [(path, 0, 0, "GATE2", "symlinked file", "museum edits happen in .roblox-harness/, never through a link")]
    rel = os.path.relpath(os.path.realpath(path), root).replace(os.sep, "/")
    if rel.startswith(".."):
        return [(path, 0, 0, "GATE2", "outside the project", "writes go in shared/src/, places/<Place>/src/, plugins/ or tests/<Place>/")]
    # a symlinked ANCESTOR inside the project is a museum directory recreated
    # as links; the file itself resolving elsewhere is the same close
    probe = os.path.dirname(os.path.abspath(path))
    while len(probe) > len(root) and probe.startswith(root):
        if os.path.islink(probe):
            return [(path, 0, 0, "GATE2", "under a symlinked directory", "museum edits happen in .roblox-harness/")]
        probe = os.path.dirname(probe)
    ok = (
        rel.startswith("shared/src/")
        or re.match(r"^places/[^/]+/src/", rel)
        or rel.startswith("plugins/")
        or re.match(r"^tests/[^/]+/", rel)
    )
    if not ok:
        return [(path, 0, 0, "GATE2", rel, "writes go in shared/src/, places/<Place>/src/, plugins/ or tests/<Place>/")]
    container = gatelib.service_init_container(rel)
    if container:
        return [
            (
                path,
                0,
                0,
                "GATE2",
                "%s under %s" % (os.path.basename(rel), container),
                "a service is never a script - name the entry, e.g. Server.server.luau / Client.client.luau",
            )
        ]
    base = os.path.basename(path)
    if base in museum_names(os.path.dirname(path)):
        return [(path, 0, 0, "GATE2", base + " is a museum file", "museum edits happen in .roblox-harness/")]
    return []


def check_gate3(path):
    base = os.path.basename(path)
    if base in ("Default.luau", "Development.luau", "Typed.luau") and "/PlayerData" in path.replace(os.sep, "/"):
        return [
            (
                path,
                0,
                0,
                "GATE3",
                base + " written directly",
                "data modules have one writer - type_write (a retype is DATA34, an unpaired edit splits the pair)",
            )
        ]
    return []


def check_debug2(path, content, cwd, agent_type):
    findings = []
    rel = os.path.relpath(os.path.realpath(path), os.path.realpath(cwd)).replace(os.sep, "/")
    in_tests = rel.startswith("tests/")
    is_debugger = agent_type == "debugger"
    if in_tests and not is_debugger:
        findings.append((path, 0, 0, "DEBUG2", "non-debugger writing tests/", "only the debugger writes tests"))
    if in_tests:
        m = re.match(r"^tests/[^/]+/(server|client)/(Fix|Diagnose|LIVE)\.[A-Za-z0-9]+\.(server|client)\.lua(?:u)?$", rel)
        if not m:
            findings.append((path, 0, 0, "DEBUG2", rel, "tests are <Mode>.<Name>.<side>.luau under tests/<Place>/<side>/"))
        if content is not None:
            if "ENABLED" not in content:
                findings.append((path, 0, 0, "DEBUG2", "no ENABLED switch", "the test file contract requires it"))
            header_ok = all(k in content for k in ("what it does", "HOW TO USE", "delete-when"))
            if not header_ok:
                findings.append((path, 0, 0, "DEBUG2", "header incomplete", "what it does - HOW TO USE - delete-when"))
    return findings


def check_bc4(path, content):
    """A hand-written skeleton — the emitter's frame arriving via Write."""
    if content is None:
        return []
    stripped = re.sub(r"\s+", " ", content).strip()
    # the events divider is optional: controller and gui frames end at
    # -- functions, and a hand-written copy of either is the same finding
    skeleton = re.match(
        r"^local m = \{\} -- privates -- functions function m:Start\(\) end (?:-- events )?return m$", stripped
    )
    if skeleton:
        return [(path, 0, 0, "BC4", "hand-written skeleton", "create_boilerplate emits skeletons")]
    return []


def check_pragmas(path, content):
    findings = []
    if content is None:
        return findings
    for n, line in enumerate(content.split("\n"), 1):
        if re.match(r"^\s*--!(strict|nonstrict|nocheck)\b", line):
            findings.append((path, n, 1, "TYPE3", line.strip(), "checking mode is set by checked-in .luaurc, never a pragma"))
        if re.match(r"^\s*--!native\b", line) or re.search(r"@native\b", line):
            rel = path.replace(os.sep, "/")
            if "/ServerScriptService/" not in rel:
                findings.append((path, n, 1, "OPT8", line.strip()[:40], "native is server-only, hot path only"))
    return findings


def check_type8(path, content):
    if content is None or "export type" not in content:
        return []
    rel = path.replace(os.sep, "/")
    if "/ReplicatedStorage/" in rel and "/ReplicatedStorage/Types/" not in rel and "/Packages/" not in rel:
        return [(path, 0, 0, "TYPE8", "export type outside ReplicatedStorage/Types/", "shared types declare once in ReplicatedStorage/Types/<Feature>.luau")]
    return []


def check_type_write_provenance(path, before, after):
    before_signature = declaration_signature(before or "")
    after_signature = declaration_signature(after or "")
    if before_signature == after_signature:
        return []
    return [
        (
            path,
            0,
            0,
            "TYPE8",
            "named type declaration changed through a native write",
            "use tools/type_write/type_write.py",
        )
    ]


def _typed_uses(source):
    aliases = {}
    for found in re.finditer(
        r"\blocal\s+([A-Za-z_]\w*)\s*=\s*require\s*\([^\n)]*\bTypes\s*\.\s*([A-Za-z_]\w*)[^\n)]*\)",
        source,
    ):
        aliases[found.group(1)] = found.group(2)
    seams = {}
    for found in re.finditer(
        r"\blocal\s+([A-Za-z_]\w*)\s*=\s*([^\n]+?)\s*::\s*([A-Za-z_]\w*)\s*\.\s*([A-Za-z_]\w*)",
        source,
    ):
        variable, expression, alias, owner_type = found.groups()
        feature = aliases.get(alias)
        if feature:
            static = bool(
                re.search(r"\b(?:Services|Controllers)\s*\.\s*%s\b" % re.escape(feature), expression)
                or re.search(
                    r"\bget(?:Child|Service|Controller)\s*\(\s*[\"']%s[\"']\s*\)" % re.escape(feature),
                    expression,
                )
            )
            seams[variable] = (feature, owner_type, static)
    uses = {}
    computed = set()
    for variable, (feature, owner_type, static) in seams.items():
        occurrences = {}
        for found in re.finditer(r"\b%s\s*[:.]\s*([A-Za-z_]\w*)" % re.escape(variable), source):
            member = found.group(1)
            line_start = source.rfind("\n", 0, found.start()) + 1
            line_end = source.find("\n", found.end())
            line_end = len(source) if line_end < 0 else line_end
            occurrences.setdefault(member, set()).add(re.sub(r"\s+", " ", source[line_start:line_end].strip()))
        for member, lines in occurrences.items():
            uses[(feature, owner_type, member)] = (variable, static, tuple(sorted(lines)))
        if re.search(r"\b%s\s*\[" % re.escape(variable), source):
            computed.add(variable)
    untyped = {}
    for found in re.finditer(r"\blocal\s+([A-Za-z_]\w*)\s*=\s*require\s*\(([^\n)]*)\)", source):
        variable, expression = found.groups()
        if variable in seams:
            continue
        provider = re.search(r"\b(Services|Controllers)\s*\.\s*([A-Za-z_]\w*)", expression)
        if not provider:
            continue
        for access in re.finditer(r"\b%s\s*[:.]\s*([A-Za-z_]\w*)" % re.escape(variable), source):
            line_start = source.rfind("\n", 0, access.start()) + 1
            line_end = source.find("\n", access.end())
            line_end = len(source) if line_end < 0 else line_end
            untyped[(provider.group(1), provider.group(2), access.group(1))] = re.sub(r"\s+", " ", source[line_start:line_end].strip())
    return uses, untyped, computed


def _definition(index, feature, owner_type, path):
    candidates = [
        item for item in index.get("definitions", [])
        if item.get("kind") == "feature" and item.get("owner") == feature and item.get("name") == owner_type
    ]
    if not candidates:
        return None
    place_match = re.search(r"/places/([^/]+)/", os.path.realpath(path).replace(os.sep, "/"))
    place = place_match.group(1) if place_match else "shared"
    candidates.sort(key=lambda item: (item.get("place") != place, item.get("place") != "shared", item.get("path", "")))
    return candidates[0]


def check_type_system(path, before, after, cwd, session_id):
    findings = check_type_write_provenance(path, before, after)
    try:
        _, index = ensure_type_cache(cwd)
    except CacheError as error:
        findings.append((path, 0, 0, "GATE4", "type cache unavailable", str(error)[:160]))
        return findings
    findings += check_external_types(path, before, after, cwd, session_id, index)
    findings += check_data37(path, before, after, index, cwd)
    findings += check_type7_surface(path, before, after, cwd, session_id, index)
    return findings


def check_external_types(path, before, after, cwd, session_id, index):
    findings = []
    old_uses, old_untyped, old_computed = _typed_uses(before or "")
    new_uses, new_untyped, new_computed = _typed_uses(after or "")
    changed_untyped = {key for key in new_untyped if key not in old_untyped or new_untyped[key] != old_untyped[key]}
    for key in sorted(changed_untyped):
        findings.append(
            (path, 0, 0, "TYPE9", "%s.%s uses %s without a typed seam" % key, "resolve the provider statically and cast it to its exported type")
        )
    for variable in sorted(new_computed - old_computed):
        findings.append((path, 0, 0, "TYPE9", "%s uses a computed project-API member" % variable, "use a declared literal member"))
    changed_uses = {key for key in new_uses if key not in old_uses or new_uses[key][2] != old_uses[key][2]}
    for feature, owner_type, member in sorted(changed_uses):
        variable, static, _ = new_uses[(feature, owner_type, member)]
        if not static:
            findings.append((path, 0, 0, "TYPE9", "%s has a dynamic provider seam" % variable, "resolve require, Service, Controller, or child by a literal name"))
            continue
        definition = _definition(index, feature, owner_type, path)
        if definition is None or member not in definition.get("members", {}):
            findings.append((path, 0, 0, "TYPE9", "%s.%s.%s is not declared" % (feature, owner_type, member), "update the canonical type through type_write"))
            continue
        if not gatelib.type_context_valid(cwd, session_id, definition, member):
            findings.append(
                (
                    path,
                    0,
                    0,
                    "WRIT33",
                    "%s.%s.%s has no current lookup output" % (feature, owner_type, member),
                    "run type_lookup member for this provider and member",
                )
            )
    return findings


def check_data37(path, before, after, index, cwd=None):
    if os.path.basename(path) == "Typed.luau" and "/PlayerData/" in path.replace(os.sep, "/"):
        return []
    accessors = {item.get("name") for item in index.get("accessors", [])}
    pattern = re.compile(r"\bPlayerData\s*:\s*Get\s*\([^\n]*?,\s*(?:[\"']([A-Za-z_]\w*)[\"']|script\s*\.\s*Name)\s*\)")
    metadata = metadata_for_path(cwd, path) if cwd else None
    script_owner = metadata.get("owner") if metadata and metadata.get("kind") in ("service", "controller") else None
    old = {}
    new = {}
    for source, target in ((before or "", old), (after or "", new)):
        for found in pattern.finditer(source):
            owner = found.group(1) or script_owner
            if owner:
                target.setdefault(owner, set()).add(re.sub(r"\s+", " ", found.group(0)))
    changed = {owner for owner in new if owner not in old or new[owner] != old[owner]}
    return [
        (path, 0, 0, "DATA37", "PlayerData:Get reads owner %s" % owner, "use the generated Typed.%s accessor" % owner)
        for owner in sorted(changed & accessors)
    ]


def _public_functions(source):
    return {
        found.group(1)
        for found in re.finditer(r"(?m)^[ \t]*function[ \t]+m\s*[:.]\s*([A-Za-z_]\w*)\s*\(", source or "")
        if found.group(1)[:1].isupper()
    }


def _public_events(source):
    return {
        found.group(1) or found.group(2)
        for found in re.finditer(
            r"\bm\s*\.\s*Events\s*(?:\[\s*[\"']([A-Za-z_]\w*)[\"']\s*\]|\.\s*([A-Za-z_]\w*))\s*=",
            source or "",
        )
    }


def _declared_events(definition):
    if not definition:
        return set()
    member = definition.get("members", {}).get("Events")
    if not member:
        return set()
    _, separator, value = member.partition(":")
    if not separator:
        return set()
    parsed = parse_declarations("type Events = " + value.strip())
    return set(parsed[0].members) if parsed else set()


def check_type7_surface(path, before, after, cwd, session_id, index):
    old = _public_functions(before or "")
    new = _public_functions(after or "")
    old_events = _public_events(before or "")
    new_events = _public_events(after or "")
    if old == new and old_events == new_events:
        return []
    metadata = metadata_for_path(cwd, path)
    if not metadata or metadata.get("kind") not in ("service", "controller"):
        return []
    owner_type = "Service" if metadata["kind"] == "service" else "Controller"
    if metadata.get("module"):
        owner_type = metadata["module"].split("/")[-1]
    definition = _definition(index, metadata["owner"], owner_type, path)
    members = set(definition.get("members", {})) if definition else set()
    declared_events = _declared_events(definition)
    added = new - old
    removed = old - new
    surface_matches = added <= members and not (removed & members)
    if old_events != new_events:
        surface_matches = surface_matches and new_events == declared_events
    if surface_matches and gatelib.type_context_valid(cwd, session_id, definition, tools=("type-write",)):
        return []
    return [
        (
            path,
            0,
            0,
            "TYPE7",
            "%s public function surface differs from %s.%s" % (metadata["owner"], metadata["owner"], owner_type),
            "update the canonical type through type_write in the same diff",
        )
    ]


def check_bc1_handler(path, content):
    """Mutation before typeguard in a remote handler — a lean."""
    if content is None:
        return []
    findings = []
    for m in re.finditer(r"(OnServerEvent|OnServerInvoke)\s*[:=(]", content):
        rest = content[m.end() : m.end() + 800]
        first_guard = None
        first_mutation = None
        for gm in re.finditer(r"\b(typeof|type)\s*\(|:IsA\s*\(", rest):
            first_guard = gm.start()
            break
        for am in re.finditer(r"\n\s*[%\w.\[\]]+\s*(=|\+=|-=)[^=]", rest):
            first_mutation = am.start()
            break
        if first_mutation is not None and (first_guard is None or first_mutation < first_guard):
            line = content[: m.start()].count("\n") + 1
            findings.append((path, line, 1, "BC1", m.group(1) + " mutates before typeguard", "typeguard every argument, then verify, then mutate"))
    return findings


def check_data_rules(path, content):
    """DATA21, DATA23, DATA31, DATA32, DATA33, DATA35 — leans on the write
    payload; the CST checkers own the deeper forms."""
    if content is None:
        return []
    findings = []
    rel = path.replace(os.sep, "/")
    lines = content.split("\n")

    if "StartSessionAsync" in content and ":Kick" not in content:
        n = next((i for i, ln in enumerate(lines, 1) if "StartSessionAsync" in ln), 0)
        findings.append((path, n, 1, "DATA23", "session start without kick path", "kick on nil session or OnSessionEnd, format 'PlayerData | reason'"))

    for i, ln in enumerate(lines):
        if ":IsActive" in ln:
            window = "\n".join(lines[i : i + 6])
            if re.search(r"task\.wait|:Wait\(|Async\(", window[ln.find(":IsActive") + 9 :]) and re.search(r"\.Data\b", window):
                findings.append((path, i + 1, 1, "DATA31", "yield between :IsActive and the .Data write", "write immediately after :IsActive, never across a yield"))
                break

    for m in re.finditer(r"MessageHandler\s*\(\s*function\s*\(([^)]*)\)", content):
        params = [p.strip() for p in m.group(1).split(",") if p.strip()]
        n = content[: m.start()].count("\n") + 1
        if len(params) != 2:
            findings.append((path, n, 1, "DATA32", ":MessageHandler takes %d params" % len(params), "(message, processed)"))
        else:
            body = content[m.end() : m.end() + 600]
            processed = params[1]
            call = body.find(processed + "(")
            yield_pos = re.search(r"task\.wait|:Wait\(|Async\(", body)
            if call >= 0 and yield_pos is not None and yield_pos.start() < call:
                findings.append((path, n, 1, "DATA32", "processed after a yield", "call processed before any yield"))

    for m in re.finditer(r"function\s+[%\w.:]*\s*\(([^)]*)\)", content):
        body_start = m.end()
        body = content[body_start : body_start + 1200]
        if "StartSessionAsync" in body and "GetAsync" in body and "return" in body:
            n = content[: m.start()].count("\n") + 1
            findings.append((path, n, 1, "DATA33", "session and view profiles share a return path", "never one function returning both"))
            break

    for m in re.finditer(r"for\s+[^\n]*\bin\s+(pairs\s*\(\s*)?([\w]+)", content):
        var = m.group(2)
        decl = re.search(r"local\s+%s\s*=\s*PlayerData:Get\(" % re.escape(var), content)
        if decl:
            n = content[: m.start()].count("\n") + 1
            findings.append((path, n, 1, "DATA35", "iteration over the profile subtree", "read by the template/catalog, never what data holds"))
    return findings


def check_payments(path, content):
    """DATA21 + DATA36 on Services/Payments* writes.

    DATA21: Payments grants in ProcessReceipt only: handlers mutate
    Profile.Data only, PurchaseId & grant save as 1 unit, PurchaseGranted
    only after the id is in LastSavedData, NotProcessedYet only before any
    grant.
    DATA36: cached PurchaseId retry returns PurchaseGranted & re-runs no
    handlers; cache is idempotency ledger, evicted only past its recorded
    bound.

    Checks 1, 2 and 6 are literal-token guarantees; 3, 4 and 5 are leans —
    helper indirection defeats them, and the reviewer owns what they miss.
    """
    findings = []
    if content is None or "/Services/Payments" not in path.replace(os.sep, "/"):
        return findings
    lines = content.split("\n")

    def line_of(needle, start=0):
        for i, ln in enumerate(lines[start:], start + 1):
            if needle in ln:
                return i
        return 0

    # 1 [DATA21, guarantee] — MessageAsync in the receipt service: the old
    # doctrine's offline form is now an error; the rejoin retry is the queue
    n = line_of("MessageAsync")
    if n:
        findings.append((path, n, 1, "DATA21", "MessageAsync in Payments",
                         "the rejoin retry is the queue - offline delivery is not the receipt path's"))

    # 2 [DATA21, guarantee] — grants happen in ProcessReceipt only; the
    # product-prompt event is never a grant path. Exact token: the gamepass
    # variant (PromptGamePassPurchaseFinished) stays legal and is not matched.
    for i, ln in enumerate(lines, 1):
        if re.search(r"\bPromptProductPurchaseFinished\b", ln):
            findings.append((path, i, 1, "DATA21", "PromptProductPurchaseFinished",
                             "grants happen in ProcessReceipt only"))

    # 3 [DATA21, lean] — the grant-then-NPY shape: a NotProcessedYet return
    # after the grant-commit marker. The one principled exception, present in
    # the shipped template itself, is the dead-profile hold exit — an NPY
    # return inside the `if not holdForSave(...)` failure branch is exempt,
    # because the grant either died unsaved with the session or rides the
    # final save into the rejoin retry unfinalized.
    # the marker is the grant-commit CALL site, never the function definition
    commit = 0
    for i, ln in enumerate(lines, 1):
        if "cachePurchase(" in ln and "function" not in ln:
            commit = i
            break
    if commit:
        exempt_open = None
        depth = 0
        for i in range(commit, len(lines)):
            ln = lines[i]
            if re.search(r"if\s+not\s+holdForSave\(", ln):
                exempt_open = i + 1
                depth = 0
            if exempt_open is not None:
                depth += len(re.findall(r"\b(?:if|for|while|function)\b", ln)) - len(re.findall(r"\bend\b", ln))
                if depth <= 0 and i + 1 > exempt_open:
                    exempt_open = None
            if "NotProcessedYet" in ln and "return" in ln and exempt_open is None:
                findings.append((path, i + 1, 1, "DATA21", "NotProcessedYet after the grant",
                                 "NPY returns come before any grant - only the dead-profile hold exit follows one"))

    # 4 [DATA21, lean] — a PurchaseGranted return with no save-confirmation
    # evidence in the file: the id must be read back from LastSavedData
    if "PurchaseGranted" in content and not re.search(r"LastSavedData", content):
        findings.append((path, line_of("PurchaseGranted"), 1, "DATA21", "PurchaseGranted without LastSavedData evidence",
                         "PurchaseGranted only after the id is in LastSavedData"))

    # 5 [DATA36, lean] — handlers unguarded by the ledger: a handler
    # invocation with no cache-membership test re-runs grants on every retry
    handler_line = line_of("pcall(handler")
    if handler_line and "purchaseCached" not in content:
        findings.append((path, handler_line, 1, "DATA36", "handlers unguarded by the ledger",
                         "a cached PurchaseId retry re-runs no handlers"))

    # 6 [DATA36, guarantee] — the recorded eviction bound: lowering it widens
    # the re-grant window a failed-to-record PurchaseGranted retry can reach
    m = re.search(r"PURCHASE_CACHE_MAX\s*=\s*(\d+)", content)
    if m and int(m.group(1)) < 1000:
        findings.append((path, line_of("PURCHASE_CACHE_MAX"), 1, "DATA36",
                         "PURCHASE_CACHE_MAX %s below the recorded bound" % m.group(1),
                         "the ledger evicts only past 1000 - the recorded bound"))
    elif not m and re.search(r"table\.remove\([^)]*Purchases", content):
        findings.append((path, line_of("table.remove"), 1, "DATA36", "eviction without a recorded bound",
                         "PURCHASE_CACHE_MAX names the bound the ledger evicts past"))
    return findings


def check_data34_template(path):
    if os.path.basename(path) in ("Default.luau", "Development.luau"):
        # GATE3 already redirects; DATA34's write-scope clause rides the same
        # block — a retype through a direct edit is exactly what fix() would
        # destroy
        return []
    return []


def patch_text(tool_input):
    """Return one V4A patch envelope from a native apply-patch payload."""
    if not isinstance(tool_input, dict):
        return None
    for value in tool_input.values():
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, str) and "*** Begin Patch" in item:
                return item
    return None


def parse_patch(text):
    """The V4A envelope: *** Add File / Update File / Delete File sections.
    Returns [(op, path, content_or_None)] — Add carries full content (lines
    stripped of their leading +), Update carries the hunk lines verbatim."""
    files = []
    current = None
    for line in text.split("\n"):
        m = re.match(r"^\*\*\* (Add|Update|Delete) File: (.+)$", line)
        if m:
            if current:
                files.append(current)
            current = [m.group(1), m.group(2).strip(), []]
            continue
        if line.startswith("*** "):
            if current:
                files.append(current)
            current = None
            continue
        if current is not None:
            current[2].append(line)
    if current:
        files.append(current)
    out = []
    for op, path, body in files:
        if op == "Add":
            content = "\n".join(ln[1:] if ln.startswith("+") else ln for ln in body)
            out.append((op, path, content))
        else:
            out.append((op, path, "\n".join(body) if body else None))
    return out


def apply_hunks(original, hunk_lines):
    """Best-effort V4A apply: context/-/+ runs anchored by content match.
    Returns the new text, or None when a hunk's context does not match —
    never a guessed result."""
    lines = original.split("\n")
    pos = 0
    result = []
    i = 0
    while i < len(hunk_lines):
        ln = hunk_lines[i]
        if ln.startswith("@@"):
            i += 1
            continue
        run = []
        while i < len(hunk_lines) and not hunk_lines[i].startswith("@@"):
            run.append(hunk_lines[i])
            i += 1
        old = [l[1:] if l.startswith(("-", " ")) else l for l in run if not l.startswith("+")]
        new = [l[1:] if l.startswith(("+", " ")) else l for l in run if not l.startswith("-")]
        if not old:
            result.extend(lines[pos:])
            pos = len(lines)
            result.extend(new)
            continue
        found = -1
        for j in range(pos, len(lines) - len(old) + 1):
            if lines[j : j + len(old)] == old:
                found = j
                break
        if found < 0:
            return None
        result.extend(lines[pos:found])
        result.extend(new)
        pos = found + len(old)
    result.extend(lines[pos:])
    return "\n".join(result)


def handle_apply_patch(tool_input, cwd, agent_type):
    patch = patch_text(tool_input)
    if patch is None:
        sys.stderr.write(gatelib.blocker_instruction("new-task", cwd) + "\n")
        return 2
    findings = []
    for op, rel_path, content in parse_patch(patch):
        path = rel_path if os.path.isabs(rel_path) else os.path.join(cwd, rel_path)
        findings += check_gate2(path, cwd)
        if not path.endswith(".luau") and not path.endswith(".lua"):
            continue
        findings += check_gate3(path)
        if op == "Delete":
            try:
                with open(path, encoding="utf-8") as f:
                    before = f.read()
            except OSError:
                before = ""
            findings += check_type_system(path, before, "", cwd, "")
            continue
        resolved = content if op == "Add" else None
        before = ""
        if op == "Update" and content is not None and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    before = f.read()
                    resolved = apply_hunks(before, content.split("\n"))
            except OSError:
                resolved = None
        elif op == "Add":
            before = ""
        findings += check_debug2(path, resolved, cwd, agent_type)
        if resolved is not None:
            findings += check_type_system(path, before, resolved, cwd, "")
            findings += check_bc4(path, resolved)
            findings += check_pragmas(path, resolved)
            findings += check_type8(path, resolved)
            findings += check_bc1_handler(path, resolved)
            findings += check_data_rules(path, resolved)
            findings += check_payments(path, resolved)
            findings += scan_content(path, resolved, cwd)
    if findings:
        return block("apply_patch", findings, cwd)
    return 0


def scan_content(path, content, cwd):
    """deny_scan + replication_audit + data_check --static over a resulting
    file, shared by the Write path and the apply_patch path."""
    import shutil

    findings = []
    rel = os.path.relpath(os.path.realpath(path), os.path.realpath(cwd)).replace(os.sep, "/")
    if rel.startswith(".."):
        rel = os.path.basename(path)
    tmp_dir = tempfile.mkdtemp(prefix="write_gate_scan_")
    try:
        scan_target = os.path.join(tmp_dir, rel)
        os.makedirs(os.path.dirname(scan_target), exist_ok=True)
        with open(scan_target, "w", encoding="utf-8") as f:
            f.write(content)
        in_tests = rel.startswith("tests/")
        r = run_tool([sys.executable, os.path.join(TOOLS, "deny_scan", "deny_scan.py"), "--root", tmp_dir, scan_target])
        if r.returncode == 2:
            found = False
            for line in r.stderr.splitlines():
                m = re.match(r"^(\d+)\|(\d+)\|(\w+)\|(.*)\|(.*)$", line)
                if m:
                    found = True
                    findings.append((path, int(m.group(1)), int(m.group(2)), m.group(3), m.group(4), m.group(5)))
            if not found:
                findings.append((path, 0, 0, "GATE4", "deny_scan exit 2", ""))
        elif r.returncode not in (0, 2):
            findings.append((path, 0, 0, "GATE4", "deny_scan exit %d" % r.returncode, (r.stderr or "").strip()[:120] or "tool crashed"))
        if not in_tests:
            r = run_tool([sys.executable, os.path.join(TOOLS, "replication_audit", "replication_audit.py"), "--root", tmp_dir, scan_target])
            if r.returncode == 2:
                found = False
                for line in r.stderr.splitlines():
                    m = re.match(r"^(\d+)\|(\d+)\|(\w+)\|(.*)\|(.*)$", line)
                    if m:
                        found = True
                        findings.append((path, int(m.group(1)), int(m.group(2)), m.group(3), m.group(4), m.group(5)))
                if not found:
                    findings.append((path, 0, 0, "GATE4", "replication_audit exit 2", ""))
            elif r.returncode not in (0, 2):
                findings.append((path, 0, 0, "GATE4", "replication_audit exit %d" % r.returncode, (r.stderr or "").strip()[:120] or "tool crashed"))
        r = run_tool([gatelib.LUTE, "run", os.path.join(TOOLS, "data_check", "data_check.luau"), "--static", scan_target])
        if r.returncode == 2:
            found = False
            for line in r.stdout.splitlines():
                m = re.match(r"^(\d+)\|(\d+)\|(\w+)\|(.*)\|(.*)$", line)
                if m:
                    found = True
                    findings.append((path, int(m.group(1)), int(m.group(2)), m.group(3), m.group(4), m.group(5)))
            if not found:
                findings.append((path, 0, 0, "GATE4", "data_check exit 2", ""))
        elif r.returncode != 0:
            findings.append((path, 0, 0, "GATE4", "data_check exit %d" % r.returncode, ""))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return findings


def run_tool(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as e:
        class R:
            returncode = 2
            stdout = ""
            stderr = "tool crashed: %s" % e

        return R()


def hook_scope(argv):
    try:
        index = argv.index("--hook-scope")
        value = argv[index + 1]
    except (ValueError, IndexError):
        return ""
    return value if value in ("project", "user") else ""


def _tool_key(tool_name):
    return re.sub(r"[^a-z0-9]", "", str(tool_name or "").casefold())


def _mentions_source_path(text):
    return bool(re.search(r"\.lua(?:u)?(?=$|[\s'\"),;&|<>])", str(text or ""), re.IGNORECASE))


def _mentions_source_tree(text):
    return bool(
        re.search(
            r"(?:^|[\s'\"])(?:\./)?(?:shared/src|places/[^/\s'\"]+/src|plugins(?:/[^/\s'\"]+)?|tests)(?:[/\s'\"]|$)",
            str(text or ""),
            re.IGNORECASE,
        )
    )


def _python_source_write_invocation(command, argv):
    """Recognize Python write forms only when they name a Luau destination."""
    if not _mentions_source_path(command):
        return False
    write_call = re.compile(
        r"(?:"
        r"\bopen\s*\([^)]*(?:,\s*|mode\s*=\s*)['\"][wax+]"
        r"|\.open\s*\(\s*(?:mode\s*=\s*)?['\"][wax+]"
        r"|\.(?:write_text|write_bytes|unlink|rename|replace)\s*\("
        r"|\b(?:os|shutil)\.(?:remove|unlink|rename|replace|move|copy|copy2|copyfile)\s*\("
        r")",
        re.IGNORECASE,
    )
    if write_call.search(command):
        return True
    output_flags = {"-o", "--out", "--output", "--dest", "--destination", "--write"}
    return any(argument in output_flags for argument in argv[1:])


def _source_destination(path, cwd):
    path = str(path).strip().strip("'\"")
    lexical = path if os.path.isabs(path) else os.path.join(cwd, path)
    return lexical.casefold().endswith((".lua", ".luau")) or os.path.realpath(lexical).casefold().endswith(
        (".lua", ".luau")
    )


def token_shrink_source_write_invocation(tool_name, tool_input, cwd):
    """Recognize a token-shortener command that targets Luau source."""
    if tool_name not in ("Bash", "Shell", "exec_command") or not isinstance(tool_input, dict):
        return False
    command = tool_input.get("command") or tool_input.get("cmd")
    if not isinstance(command, str):
        return False
    if not re.search(r"(?:^|[/\\])token_shrink\.py(?=$|[\s'\"])", command, re.IGNORECASE):
        return False
    try:
        lexer = shlex.shlex(command, posix=os.name != "nt", punctuation_chars="|&;<>")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return bool(_mentions_source_path(command) and re.search(r"--output|>>?|\btee\b", command))
    destinations = []
    controls = {"|", "||", "&", "&&", ";", "<", "<<", ">", ">>"}
    for index, token in enumerate(tokens):
        if token == "--output" and index + 1 < len(tokens):
            destinations.append(tokens[index + 1])
        elif token.startswith("--output="):
            destinations.append(token.split("=", 1)[1])
        elif token in (">", ">>") and index + 1 < len(tokens):
            destinations.append(tokens[index + 1])
        elif os.path.basename(token).casefold() == "tee":
            for candidate in tokens[index + 1 :]:
                if candidate in controls:
                    break
                if not candidate.startswith("-"):
                    destinations.append(candidate)
    return any(_source_destination(path, cwd) for path in destinations if path)


def source_mutation_invocation(tool_name, tool_input):
    """Recognize native source writes and harness-owned write commands.

    Unknown and read-only shell commands stay on the authorization-only path.
    The Stop tree sweep remains the floor for source created outside native
    edit tools.
    """
    key = _tool_key(tool_name)
    if key == "applypatch":
        patch = patch_text(tool_input)
        return bool(
            patch
            and any(path.casefold().endswith((".lua", ".luau")) for _, path, _ in parse_patch(patch))
        )
    if key in {"edit", "multiedit", "notebookedit", "write"}:
        path = tool_input.get("file_path") if isinstance(tool_input, dict) else ""
        return isinstance(path, str) and path.endswith((".lua", ".luau"))
    if tool_name in ("Bash", "Shell", "exec_command") and isinstance(tool_input, dict):
        command = tool_input.get("command") or tool_input.get("cmd")
        if isinstance(command, str):
            # `_shell_argv` admits only one simple command. Inspect later shell
            # segments and redirections as well so a read followed by a write
            # cannot bypass the first-mutation preparation.
            mutator = re.compile(
                r"(?:^|[\n;&|]\s*)(?:command\s+)?(?:"
                r"cp|install|mv|rm|rmdir|tee|touch|truncate"
                r"|sed\s+(?:[^\n;&|]*\s)?-i(?:\s|$)"
                r"|perl\s+(?:[^\n;&|]*\s)?-i(?:\s|$)"
                r")\b",
                re.IGNORECASE,
            )
            if (mutator.search(command) and (_mentions_source_path(command) or _mentions_source_tree(command))) or re.search(
                r"(?:^|[^<>])>>?\s*[^\n;&|]*\.(?:lua|luau)(?:\s|$)",
                command,
                re.IGNORECASE,
            ) or re.search(
                r"\bof\s*=\s*[^\n;&|]*\.(?:lua|luau)(?:\s|$)",
                command,
                re.IGNORECASE,
            ):
                return True
    argv = gatelib._shell_argv(tool_name, tool_input)
    if not argv:
        return False
    executable = os.path.basename(argv[0]).casefold()
    command_text = " ".join(argv[1:])
    if executable in {"cp", "install", "mv", "rm", "rmdir", "tee", "touch", "truncate"}:
        return _mentions_source_path(command_text) or _mentions_source_tree(command_text)
    if executable == "git" and len(argv) > 1 and argv[1] in {
        "am",
        "apply",
        "cherry-pick",
        "clean",
        "merge",
        "rebase",
        "reset",
        "restore",
        "stash",
        "switch",
    }:
        return True
    if executable == "git" and len(argv) > 1 and argv[1] in {"mv", "rm"}:
        return _mentions_source_path(command_text) or _mentions_source_tree(command_text)
    if not gatelib._is_python_executable(argv[0]) or len(argv) < 2:
        return False
    command = ""
    if isinstance(tool_input, dict):
        command = tool_input.get("command") or tool_input.get("cmd") or ""
    if isinstance(command, str) and _python_source_write_invocation(command, argv):
        return True
    script = os.path.realpath(os.path.expanduser(argv[1]))
    mutating = {
        os.path.realpath(os.path.join(TOOLS, "create_boilerplate", "create_boilerplate.py")),
        os.path.realpath(os.path.join(TOOLS, "data_write", "data_write.py")),
        os.path.realpath(os.path.join(TOOLS, "type_write", "type_write.py")),
        os.path.realpath(
            os.path.join(
                gatelib.HARNESS,
                "shared",
                "skills",
                "roblox-new-game",
                "scripts",
                "scaffold.py",
            )
        ),
    }
    return script in mutating


def _read_only_shell_command(argv):
    if not argv:
        return False
    executable = os.path.basename(argv[0]).casefold()
    if executable.endswith(".exe"):
        executable = executable[:-4]
    arguments = [str(argument) for argument in argv[1:]]
    is_python = gatelib._is_python_executable(argv[0])
    if not is_python:
        resolved = gatelib.which(argv[0] if os.path.basename(argv[0]) == argv[0] else executable)
        if not resolved or (
            os.path.basename(argv[0]) != argv[0]
            and os.path.realpath(os.path.expanduser(argv[0])) != os.path.realpath(resolved)
        ):
            return False
    if executable in {
        "basename", "cat", "dirname", "du", "grep", "head", "ls",
        "pwd", "realpath", "rg", "stat", "tail", "test", "true", "wc",
    }:
        if executable == "rg" and any(
            argument == "--pre"
            or argument.startswith("--pre=")
            or argument == "--hostname-bin"
            or argument.startswith("--hostname-bin=")
            for argument in arguments
        ):
            return False
        return True
    if executable == "find":
        return not any(
            argument == "-delete"
            or argument.startswith(("-exec", "-fls", "-fprint", "-fprintf", "-ok"))
            for argument in arguments
        )
    if executable == "git" and arguments:
        if arguments[0] != "--no-pager" or len(arguments) < 2:
            return False
        arguments = arguments[1:]
        subcommand = arguments[0]
        if any(
            argument in {"--output", "--paginate"}
            or argument.startswith(("--filter", "--out"))
            or (
                subcommand in {"diff", "diff-tree", "log", "show"}
                and argument.startswith(("--e", "--t"))
            )
            or (
                subcommand == "grep"
                and argument.startswith(("--op", "--t"))
            )
            or argument == "--open-files-in-pager"
            or argument.startswith("--open-files-in-pager=")
            for argument in arguments[1:]
        ):
            return False
        if subcommand in {"diff", "diff-tree", "log", "show"} and not {
            "--no-ext-diff",
            "--no-textconv",
        }.issubset(arguments[1:]):
            return False
        return subcommand in {
            "diff", "diff-tree", "grep", "log", "ls-files",
            "ls-tree", "merge-base", "rev-list", "rev-parse", "show",
            "symbolic-ref",
        }
    if is_python and len(argv) >= 3:
        if gatelib.maintenance_read_invocation(
            "exec_command",
            {"cmd": subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)},
        ):
            return True
        tool = os.path.realpath(os.path.expanduser(argv[1]))
        return tool == os.path.realpath(os.path.join(TOOLS, "type_lookup", "type_lookup.py"))
    return False


def shell_invocation_read_only(tool_name, tool_input):
    """Prove every segment of a shell pipeline is read-only."""
    if tool_name not in ("Bash", "Shell", "exec_command") or not isinstance(tool_input, dict):
        return False
    command = tool_input.get("command") or tool_input.get("cmd")
    if not isinstance(command, str) or not command.strip():
        return False
    if tool_input.get("tty") is True:
        return False
    if any(marker in command for marker in ("\n", "\r", "`", "$", "^", "{", "}", "*", "?", "[", "]", "(", ")")):
        return False
    try:
        lexer = shlex.shlex(command, posix=os.name != "nt", punctuation_chars="|&;<>")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except (TypeError, ValueError):
        return False
    segments = []
    current = []
    for token in tokens:
        if token == "|":
            if not current:
                return False
            segments.append(current)
            current = []
            continue
        if any(character in token for character in "&;<>") or "|" in token:
            return False
        current.append(token)
    if not current:
        return False
    segments.append(current)
    normalized = []
    for segment in segments:
        if segment and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", segment[0]):
            return False
        if segment and segment[0] == "command":
            segment = segment[1:]
        normalized.append(segment)
    return bool(normalized) and all(_read_only_shell_command(segment) for segment in normalized)


def opaque_shell_mutation_invocation(tool_name, tool_input):
    """Return true when a shell command cannot be proved read-only."""
    return (
        tool_name in ("Bash", "Shell", "exec_command")
        and not shell_invocation_read_only(tool_name, tool_input)
        and not source_mutation_invocation(tool_name, tool_input)
    )


def _path_in_project_gates(path, cwd):
    if not isinstance(path, str) or not path:
        return False
    candidate = path if os.path.isabs(path) else os.path.join(cwd, path)
    gate_root = os.path.abspath(os.path.join(cwd, "gates"))
    lexical = os.path.abspath(candidate)
    try:
        if os.path.commonpath((gate_root, lexical)) == gate_root:
            return True
    except ValueError:
        return False
    real_gate_root = os.path.realpath(gate_root)
    real_candidate = os.path.realpath(candidate)
    try:
        return os.path.commonpath((real_gate_root, real_candidate)) == real_gate_root
    except ValueError:
        return False


def _project_gate_reference(command, cwd):
    normalized = str(command or "").replace("\\", "/")
    absolute = os.path.realpath(os.path.join(cwd, "gates")).replace("\\", "/")
    if absolute in normalized:
        return True
    return bool(
        re.search(
            r"(?<![A-Za-z0-9_./-])(?:\./)?gates(?:/|(?=$)|(?=[\s'\";)]))",
            normalized,
        )
        or re.search(r"(?:\$PWD|\$\{PWD\})/gates(?:/|\b)", normalized)
    )


def _project_gate_read_only_shell(argv):
    """Admit only simple commands that cannot mutate the referenced gates tree."""
    if not argv:
        return False
    executable = os.path.basename(argv[0]).casefold()
    arguments = [str(argument) for argument in argv[1:]]
    if executable in {"cat", "file", "grep", "head", "ls", "rg", "stat", "tail", "wc"}:
        return True
    if executable == "find":
        return not any(
            argument in {"-delete", "-exec", "-execdir", "-ok", "-okdir"}
            for argument in arguments
        )
    if executable == "sed":
        return not any(argument == "-i" or argument.startswith("-i") for argument in arguments)
    if executable == "git" and arguments:
        return arguments[0] in {"diff", "grep", "ls-files", "show", "status"}
    return False


def gate_state_mutation_invocation(tool_name, tool_input, cwd):
    """Reject host writes to lifecycle state; only harness gates own it."""
    key = _tool_key(tool_name)
    if key == "applypatch":
        patch = patch_text(tool_input)
        return bool(
            patch
            and any(_path_in_project_gates(path, cwd) for _, path, _ in parse_patch(patch))
        )
    if key in {"edit", "multiedit", "notebookedit", "write"}:
        path = tool_input.get("file_path") if isinstance(tool_input, dict) else ""
        return _path_in_project_gates(path, cwd)
    if tool_name not in ("Bash", "Shell", "exec_command") or not isinstance(tool_input, dict):
        return False
    command = tool_input.get("command") or tool_input.get("cmd")
    if not isinstance(command, str):
        return False
    argv = gatelib._shell_argv(tool_name, tool_input)
    if argv and os.path.basename(argv[0]).casefold() == "git" and len(argv) > 1 and argv[1] == "clean":
        if any("x" in argument.lstrip("-") for argument in argv[2:] if argument.startswith("-")):
            return True
    if not _project_gate_reference(command, cwd):
        return False
    # Lifecycle files have no supported model-driven shell write route.  A
    # small read-only allowlist keeps inspection available while unknown
    # interpreters and writers (dd, tar, rsync, native binaries, and Python
    # variants not recognizable from source text) fail closed.
    if _project_gate_read_only_shell(argv):
        return False
    return True


def _run_required(command, cwd, timeout):
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        )
    except Exception as error:
        return subprocess.CompletedProcess(
            command,
            3,
            "",
            "%s: %s" % (type(error).__name__, error),
        )


def source_toolchain_present():
    lute = os.path.isfile(gatelib.LUTE) and (os.name == "nt" or os.access(gatelib.LUTE, os.X_OK))
    bundled_lsp = os.path.isfile(gatelib.LUAU_LSP) and (os.name == "nt" or os.access(gatelib.LUAU_LSP, os.X_OK))
    return bool(lute and (bundled_lsp or gatelib.which("luau-lsp")))


def ensure_source_toolchain(cwd):
    """Run the one pinned installer when a required source checker is absent."""
    if source_toolchain_present():
        return ""
    installed = _run_required(gatelib.toolchain_install_command(), cwd, 600)
    if installed.returncode == 0 and source_toolchain_present():
        return ""
    return (installed.stderr or installed.stdout or "toolchain installer failed").strip()[:160]


def ensure_api_globals(cwd):
    """Run the bounded corpus/global repair required by settled style rules."""
    corpus_state, corpus_detail = gatelib.corpus_status()
    if corpus_state == "fresh" and gatelib.api_globals_present():
        return ""
    if corpus_state != "fresh":
        cache_ok, cache_detail = gatelib.cache_sync_ready()
        if not cache_ok:
            return cache_detail
        synced = _run_required(
            [sys.executable, os.path.join(TOOLS, "api_dump", "api_dump.py"), "--sync"],
            cwd,
            600,
        )
        if synced.returncode != 0 or gatelib.corpus_status()[0] != "fresh":
            return (synced.stderr or synced.stdout or corpus_detail or "corpus sync failed").strip()[:160]
    command = [
        sys.executable,
        os.path.join(TOOLS, "api_dump", "api_dump.py"),
        "--emit-globals",
    ]
    updates = os.path.join(cwd, "shared", "src", "ServerScriptService", "Services", "Updates")
    if os.path.isdir(updates):
        command += ["--updates", updates]
    generated = _run_required(command, cwd, 300)
    if generated.returncode == 0 and gatelib.api_globals_present():
        return ""
    return (generated.stderr or generated.stdout or "api_globals generation failed").strip()[:160]


def format_write_source(path, content):
    """Run the parse-verified style transform for one full Write payload."""
    fmt_dir = tempfile.mkdtemp(prefix="write_gate_fmt_")
    try:
        temporary = os.path.join(fmt_dir, os.path.basename(path))
        with open(temporary, "w", encoding="utf-8") as handle:
            handle.write(content)
        result = run_tool(
            [gatelib.LUTE, "run", os.path.join(TOOLS, "style_assess", "fix_pass.luau"), temporary, temporary]
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "formatter failed").strip()[:200]
            return content, detail
        output = result.stdout.strip().splitlines()
        marker = output[-1] if output else ""
        if marker == "clean":
            return content, ""
        if not marker.startswith("changed|"):
            return content, "formatter output was not parseable"
        try:
            with open(temporary, encoding="utf-8") as handle:
                return handle.read(), ""
        except OSError as error:
            return content, str(error)[:200]
    finally:
        import shutil

        shutil.rmtree(fmt_dir, ignore_errors=True)


def mutation_prerequisite_findings(cwd, session_id, turn_id=""):
    """Auto-prepare deterministic mutation inputs and check remote state once."""
    try:
        turn = gatelib.ensure_turn_record(cwd, session_id, turn_id)
    except OSError as error:
        return [
            (
                None,
                0,
                0,
                "GATE4",
                "turn baseline unavailable: %s" % str(error)[:120],
                "restore Git and gates write access",
            )
        ]
    if gatelib.mutation_check_current(cwd, session_id, turn):
        return []

    toolchain_error = ensure_source_toolchain(cwd)
    if toolchain_error:
        return [
            (
                None,
                0,
                0,
                "GATE4",
                "required source toolchain unavailable: %s" % toolchain_error,
                "repair the harness toolchain",
            )
        ]

    globals_error = ensure_api_globals(cwd)
    if globals_error:
        return [
            (
                None,
                0,
                0,
                "GATE4",
                "required api_globals repair failed: %s" % globals_error,
                "repair generated API globals",
            )
        ]

    try:
        ensure_type_cache(cwd)
    except (CacheError, OSError, ValueError, TypeError) as error:
        return [(None, 0, 0, "GATE4", "type cache repair failed: %s" % str(error)[:160], "repair the project type cache")]

    if not gatelib.is_harness(cwd):
        state, detail = gatelib.gate6_state(cwd, fetch=True)
        if gatelib.gate6_disposition(state) == "repair":
            repaired = _run_required(
                [
                    sys.executable,
                    os.path.join(TOOLS, "git_sync", "git_sync.py"),
                    "repair",
                    "--root",
                    os.path.realpath(cwd),
                ],
                cwd,
                gatelib.GIT_REPAIR_TIMEOUT,
            )
            if repaired.returncode == 0:
                state, detail = gatelib.gate6_state(cwd, fetch=True)
            else:
                detail = (repaired.stderr or repaired.stdout or detail or "repair failed").strip()[:160]
        disposition = gatelib.gate6_disposition(state)
        if disposition == "advisory":
            sys.stderr.write(
                "write-gate: NOTED [GATE6] fetch-failed: %s\n"
                % detail.replace("|", "/")[:160]
            )
        elif state != "ok":
            return [(None, 0, 0, "GATE6", "%s: %s" % (state, detail), gatelib.gate6_instruction(cwd, state, detail))]

    try:
        recorded = gatelib.write_mutation_check(cwd, session_id, turn)
    except OSError as error:
        return [(None, 0, 0, "GATE4", "mutation check record failed: %s" % str(error)[:120], "allow writes to the project gates directory")]
    if not recorded:
        return [(None, 0, 0, "GATE6", "ref-read-failed: mutation Git identity changed", "retry after the current Git operation settles")]
    return []


def refresh_degraded_session(payload, cwd, scope, host, snapshot):
    """Re-run precheck after a recovery command and promote only a clean session."""
    return gatelib.refresh_degraded_session(payload, cwd, scope, host, snapshot)


def active_agent_entries(cwd, session_id):
    """Return live role mailboxes for dispatch and source-write arbitration."""
    return [
        entry
        for entry in gatelib.agent_mailbox_entries(cwd, session_id)
        if entry.get("cwd") == os.path.realpath(cwd)
        and entry.get("session_id") == str(session_id)
        and entry.get("state") in ("pending", "overlap", "recovering", "reviewing")
    ]


def handle_agent_dispatch(payload, tool_name, tool_input, cwd, session_id):
    """Bind a ruled role to this authorized parent dispatch.

    Host-reported direct role names remain authoritative at SubagentStart.
    Codex default-profile starts consume this short-lived queue instead of
    granting themselves authority from their return text.
    """
    if not agent_dispatch.tool_is_spawn(tool_name):
        return None
    current_role = gatelib.effective_agent_type(payload, cwd)
    if payload.get("agent_id") or current_role in agent_dispatch.AGENTS:
        sys.stderr.write("agent-dispatch: delegation depth is one; a child may not spawn another agent\n")
        return 2
    role = agent_dispatch.dispatch_role(tool_name, tool_input)
    if not role:
        return 0  # a generic agent remains read-only and cannot return harness evidence
    recovery_kind = ""
    if role == "maintainer":
        recovery_kind = requested_maintenance_recovery(tool_input, cwd)
    queued = agent_dispatch.roles(cwd, session_id)
    active = active_agent_entries(cwd, session_id)
    prompt = tool_input.get("message") or tool_input.get("prompt") or ""
    turn = gatelib.read_turn_record(cwd, session_id)
    target_digest = str(tool_input.get("target_digest") or "")
    if not target_digest and role in ("reviewer", "optimizer"):
        target_digest = gatelib.review_target(cwd, turn)[0] or ""
    paths = (
        tool_input.get("lease_paths")
        or tool_input.get("paths")
        or tool_input.get("affected_paths")
        or ([] if role != "debugger" else ["tests/"])
    )
    accepted_role = [
        entry
        for entry in agent_dispatch.entries(cwd, session_id)
        if entry.get("role") == role and entry.get("state") == "accepted"
    ]
    if role == "optimizer" and accepted_role:
        sys.stderr.write(
            "agent-dispatch: REUSE|optimizer\n%s\n"
            % str(accepted_role[0].get("result") or "optimizer: ENV\n\nENV|result|accepted result absent")
        )
        return 2
    if role == "reviewer" and accepted_role:
        sys.stderr.write(
            "agent-dispatch: reviewer cycle is settled; resume its reviewer once after correction writes\n"
        )
        return 2
    if role == "reviewer":
        if (
            "reviewer" in queued
            or any(entry.get("agent_type") == "reviewer" for entry in active)
            or gatelib.pending_review_receipts(cwd, session_id)
            or gatelib.valid_review_receipts(cwd, session_id)
        ):
            sys.stderr.write("agent-dispatch: one reviewer is allowed per immutable target\n")
            return 2
        if any(queued_role in agent_dispatch.WRITERS for queued_role in queued) or any(
            entry.get("agent_type") in agent_dispatch.WRITERS for entry in active
        ):
            sys.stderr.write("agent-dispatch: reviewer cannot start while a debugger mutation lease is active or queued\n")
            return 2
    if role in agent_dispatch.WRITERS:
        if "reviewer" in queued or gatelib.pending_review_receipts(cwd, session_id):
            sys.stderr.write("agent-dispatch: debugger cannot start while a reviewer is active or queued\n")
            return 2
        if role in queued or any(entry.get("agent_type") == role for entry in active):
            sys.stderr.write("agent-dispatch: another debugger is active\n")
            return 2
    if role in ("optimizer", "maintainer") and (
        role in queued or any(entry.get("agent_type") == role for entry in active)
    ):
        sys.stderr.write("agent-dispatch: another %s is active\n" % role)
        return 2
    if role == "maintainer" and not recovery_kind:
        sys.stderr.write(
            "agent-dispatch: maintainer requires one exact parent-selected recovery command\n"
        )
        return 2
    task_name = tool_input.get("task_name") or tool_input.get("name") or role
    reserved, conflict = agent_dispatch.reserve(
        cwd,
        session_id,
        role,
        task_name,
        recovery_kind=recovery_kind,
        prompt=prompt,
        target_digest=target_digest,
        paths=paths,
    )
    if not reserved:
        if conflict == "accepted":
            cached = agent_dispatch.accepted_result(
                cwd,
                session_id,
                role,
                prompt or task_name,
                target_digest,
            )
            sys.stderr.write("agent-dispatch: REUSE|%s\n%s\n" % (role, cached))
            return 2
        if conflict == "duplicate":
            sys.stderr.write("agent-dispatch: matching role work is already queued or claimed\n")
            return 2
        if conflict in ("optimizer", "maintainer", "debugger"):
            sys.stderr.write("agent-dispatch: another %s is active\n" % conflict)
            return 2
        if conflict == "reviewer":
            sys.stderr.write("agent-dispatch: one reviewer or a queued reviewer owns the immutable target\n")
            return 2
        if conflict == "writer" and role == "reviewer":
            sys.stderr.write("agent-dispatch: reviewer cannot start while a debugger mutation lease is active or queued\n")
            return 2
        if conflict == "writer":
            sys.stderr.write("agent-dispatch: another debugger is active\n")
            return 2
        sys.stderr.write("agent-dispatch: role binding could not be recorded\n")
        return 2
    return 0


def requested_maintenance_recovery(tool_input, cwd):
    """Bind one maintainer dispatch to one explicit recovery kind."""
    if not isinstance(tool_input, dict):
        return ""
    requested = tool_input.get("recovery_kind")
    if requested in gatelib.RECOVERY_KINDS:
        return requested
    task_name = str(tool_input.get("task_name") or tool_input.get("name") or "")
    normalized_task = task_name.casefold().replace("-", "_")
    task_matches = [
        kind
        for kind in gatelib.RECOVERY_KINDS
        if normalized_task in {
            kind.replace("-", "_"),
            kind.replace("-", "_") + "_recovery",
        }
    ]
    if len(task_matches) == 1:
        return task_matches[0]
    prompt = tool_input.get("message") or tool_input.get("prompt")
    if not isinstance(prompt, str):
        return ""
    matches = [
        kind
        for kind in gatelib.RECOVERY_KINDS
        if gatelib.recovery_command(kind, cwd) in prompt
    ]
    return matches[0] if len(matches) == 1 else ""


def consume_agent_recovery(payload, cwd, expected_recovery):
    """Consume one live maintainer recovery assignment atomically."""
    session_id = payload.get("session_id") or ""
    agent_id = payload.get("agent_id") or ""
    if not session_id or not agent_id:
        return ""
    with agent_dispatch._locked(cwd, session_id):
        for entry in gatelib.agent_mailbox_entries(cwd, session_id):
            if (
                entry.get("agent_id") == str(agent_id)
                and entry.get("agent_type") == "maintainer"
                and entry.get("state") == "pending"
                and not entry.get("overlap")
                and entry.get("recovery_kind") == expected_recovery
            ):
                updated = gatelib.agent_mailbox_write(
                    cwd,
                    session_id,
                    agent_id,
                    state="recovering",
                    recovery_used_at=time.time(),
                )
                return expected_recovery if updated.get("state") == "recovering" else ""
    return ""


def _paths_overlap(first, second):
    left = str(first).strip("/")
    right = str(second).strip("/")
    return bool(left and right and (left == right or left.startswith(right + "/") or right.startswith(left + "/")))


def mutation_paths(tool_name, tool_input, cwd):
    paths = []
    if tool_name in ("Write", "Edit"):
        value = tool_input.get("file_path")
        if isinstance(value, str) and value:
            paths.append(value)
    elif _tool_key(tool_name) == "applypatch":
        patch = patch_text(tool_input)
        if patch:
            paths.extend(path for _, path, _ in parse_patch(patch))
    return agent_dispatch.normalize_paths(cwd, paths)


def source_writer_conflict(payload, cwd, session_id, paths=None):
    """Return a source-write blocker, or an empty string when this actor owns it."""
    if gatelib.pending_review_receipts(cwd, session_id):
        return "review target is immutable while its reviewer is active"
    actor_id = str(payload.get("agent_id") or "")
    actor_role = gatelib.effective_agent_type(payload, cwd)
    actor_is_child = bool(actor_id or actor_role in agent_dispatch.AGENTS)
    paths = list(paths or [])
    queued_writers = [
        entry
        for entry in agent_dispatch.entries(cwd, session_id)
        if entry.get("role") in agent_dispatch.WRITERS
        and entry.get("state") in agent_dispatch.ACTIVE_STATES
    ]
    active_writers = [
        entry
        for entry in active_agent_entries(cwd, session_id)
        if entry.get("agent_type") in agent_dispatch.WRITERS
    ]
    owned = [entry for entry in active_writers if str(entry.get("agent_id") or "") == actor_id]
    foreign = [entry for entry in active_writers if str(entry.get("agent_id") or "") != actor_id]
    if actor_is_child:
        if actor_role != "debugger":
            return "%s child is read-only for project source" % (actor_role or "unbound")
        if not actor_id or not owned or any(entry.get("overlap") for entry in owned):
            return "debugger does not hold a mutation lease"
        lease_paths = owned[0].get("lease_paths") or ["tests/"]
        if not paths or any(not any(_paths_overlap(path, lease) for lease in lease_paths) for path in paths):
            return "debugger mutation is outside its assigned paths"
        return ""
    leases = foreign + queued_writers
    if leases and not paths:
        return "a debugger mutation lease is active; opaque source mutation must wait"
    for lease in leases:
        for path in paths:
            if any(_paths_overlap(path, reserved) for reserved in (lease.get("lease_paths") or ["tests/"])):
                return "source mutation overlaps an active debugger lease"
    return ""


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(argument in ("-h", "--help") for argument in argv):
        print(
            "usage: write_gate.py --host {codex,claude} "
            "--hook-scope {project,user} < hook-payload.json"
        )
        return 0
    payload = gatelib.read_payload()
    candidate = payload.get("cwd") if isinstance(payload, dict) else os.getcwd()
    if not gatelib.is_roblox_project(candidate):
        return 0
    if payload is None:
        sys.stderr.write(gatelib.blocker_instruction("new-task", candidate) + "\n")
        return 2
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    cwd = payload.get("cwd") or os.getcwd()
    session_id = payload.get("session_id", "")
    host = gatelib.hook_host(argv, payload)
    scope = hook_scope(argv)
    if not host or not scope:
        sys.stderr.write(gatelib.session_block(host, "explicit approved hook adapter is unavailable", cwd) + "\n")
        return 2
    recovery = gatelib.recovery_invocation(tool_name, tool_input, cwd)
    required_scopes = ("project", "user") if host == "codex" and scope == "project" else None
    authorized, detail = gatelib.session_authorization_status(
        payload,
        cwd,
        scope,
        "PreToolUse",
        host,
        required_scopes,
    )
    if not authorized:
        degraded, degraded_detail, repairs, snapshot = gatelib.session_recovery_status(
            payload,
            cwd,
            scope,
            "PreToolUse",
            host,
        )
        if not degraded:
            incomplete_scope = (
                "authorized only the" in detail
                and "integration did not complete" in detail
            )
            failure_detail = detail if incomplete_scope else (degraded_detail or detail)
            sys.stderr.write(gatelib.session_block(host, failure_detail, cwd) + "\n")
            return 2
        if gatelib.maintenance_control_invocation(tool_name):
            return 0
        maintenance_spawn = gatelib.maintenance_spawn_invocation(tool_name, tool_input, cwd, repairs)
        if maintenance_spawn in repairs:
            sys.stderr.write(
                "maintainer-gate: a degraded session cannot dispatch a child; "
                "the primary agent must run the exact recovery command\n"
            )
            return 2
        project_scope_observed = gatelib.session_recovery_scope_observed(
            cwd,
            session_id,
            "project",
        )
        if recovery in repairs and (scope == "project" or not project_scope_observed):
            consumed, consume_detail = gatelib.consume_session_recovery(
                cwd,
                session_id,
                recovery,
            )
            if not consumed:
                sys.stderr.write("maintainer-gate: %s\n" % consume_detail)
                return 2
        if recovery not in repairs:
            if gatelib.RECOVERY_RELINK in repairs:
                sys.stderr.write(gatelib.blocker_instruction("hooks", cwd) + "\n")
                return 2
            promoted, refresh_detail = refresh_degraded_session(payload, cwd, scope, host, snapshot)
            if not promoted:
                sys.stderr.write(refresh_detail + "\n")
                return 2
            authorized, detail = gatelib.session_authorization_status(
                payload,
                cwd,
                scope,
                "PreToolUse",
                host,
                required_scopes,
            )
            if not authorized:
                sys.stderr.write(gatelib.session_block(host, detail, cwd) + "\n")
                return 2

    # The stable user hook proves only bootstrap authorization. Project hooks
    # own all source and environment enforcement.
    if scope == "user":
        return 0

    if gate_state_mutation_invocation(tool_name, tool_input, cwd):
        sys.stderr.write(
            "[GATE2] project gates/ lifecycle state is harness-owned; retry without that write\n"
        )
        return 2

    dispatch_result = handle_agent_dispatch(payload, tool_name, tool_input, cwd, session_id)
    if dispatch_result is not None:
        return dispatch_result

    agent_type = gatelib.effective_agent_type(payload, cwd)
    child_actor = bool(payload.get("agent_id") or agent_type in agent_dispatch.AGENTS)
    pre_final = gatelib.finalization_invocation(tool_name, tool_input, cwd, session_id)
    if pre_final:
        if child_actor:
            sys.stderr.write("finalize-gate: only the parent task may create the pre-final receipt\n")
            return 2
        return 0
    if recovery and child_actor:
        if agent_type != "maintainer":
            sys.stderr.write(
                "maintainer-gate: read-only and debugger agents cannot run recovery commands\n"
            )
            return 2
        assigned_recovery = consume_agent_recovery(payload, cwd, recovery)
        if assigned_recovery != recovery:
            sys.stderr.write(
                "maintainer-gate: recovery command does not match this live maintainer assignment\n"
            )
            return 2
    if agent_type == "maintainer" and not recovery and not gatelib.maintenance_read_invocation(tool_name, tool_input):
        sys.stderr.write("maintainer-gate: only exact recovery commands and api_dump reads are permitted\n")
        return 2

    if recovery in (gatelib.RECOVERY_GIT_SYNC, gatelib.RECOVERY_RELINK) and gatelib.pending_review_receipts(cwd, session_id):
        sys.stderr.write("source-writer-gate: review target is immutable while its reviewer is active\n")
        return 2

    if recovery == gatelib.RECOVERY_GIT_SYNC:
        return 0
    if recovery == gatelib.RECOVERY_TOOLCHAIN:
        return 0
    if recovery == gatelib.RECOVERY_RELINK:
        return 0
    if recovery == gatelib.RECOVERY_API_SYNC:
        cache_ok, cache_detail = gatelib.cache_sync_ready()
        if not cache_ok:
            return block(
                tool_name,
                [(None, 0, 0, "GATE4", "cache permission failure: %s" % cache_detail, "Allow writes to ~/.cache/harness.")],
                cwd,
                env=True,
            )
        return 0
    if recovery == gatelib.RECOVERY_API_GLOBALS:
        corpus_state, corpus_detail = gatelib.corpus_status()
        if corpus_state != "fresh":
            return block(
                tool_name,
                [(None, 0, 0, "GATE4", "corpus %s: %s" % (corpus_state, corpus_detail), gatelib.recovery_command(gatelib.RECOVERY_API_SYNC, cwd))],
                cwd,
                env=True,
            )
        cache_ok, cache_detail = gatelib.cache_write_ready()
        if not cache_ok:
            return block(
                tool_name,
                [(None, 0, 0, "GATE4", "cache permission failure: %s" % cache_detail, "Allow writes to ~/.cache/harness.")],
                cwd,
                env=True,
            )
        return 0
    if recovery == gatelib.RECOVERY_TYPE_CACHE:
        cache_ok, cache_detail = gatelib.cache_write_ready()
        if not cache_ok:
            return block(
                tool_name,
                [(None, 0, 0, "GATE4", "cache permission failure: %s" % cache_detail, "Allow writes to ~/.cache/harness.")],
                cwd,
                env=True,
            )
        return 0

    if tool_name == "mcp__Roblox_Studio__execute_luau":
        code = tool_input.get("code")
        if code is None:
            sys.stderr.write("Retry the Roblox Studio op w/ Luau code.\n")
            return 2
        findings = check_gate5(code)
        if findings:
            return block(tool_name, findings, cwd)
        try:
            gatelib.mark_studio_required(cwd, session_id)
        except OSError:
            pass
        return 0

    if token_shrink_source_write_invocation(tool_name, tool_input, cwd):
        sys.stderr.write("token-shrink-gate: BLOCKED token shortening must not write .lua or .luau files\n")
        return 2

    source_mutation = source_mutation_invocation(tool_name, tool_input)
    opaque_shell_mutation = opaque_shell_mutation_invocation(tool_name, tool_input)
    if opaque_shell_mutation and child_actor:
        sys.stderr.write(
            "source-writer-gate: child shell command is not provably read-only; use the bounded role tool surface\n"
        )
        return 2
    mutation_sensitive = source_mutation or opaque_shell_mutation
    if not mutation_sensitive:
        if _tool_key(tool_name) == "applypatch":
            return handle_apply_patch(tool_input, cwd, agent_type)
        if tool_name in ("Edit", "Write"):
            path = tool_input.get("file_path")
            if not isinstance(path, str) or not path:
                sys.stderr.write(gatelib.blocker_instruction("new-task", cwd) + "\n")
                return 2
            if not os.path.isabs(path):
                path = os.path.join(cwd, path)
            path_findings = check_gate2(path, cwd)
            if path_findings:
                return block(tool_name, path_findings, cwd)
        return 0
    writer_conflict = source_writer_conflict(
        payload,
        cwd,
        session_id,
        mutation_paths(tool_name, tool_input, cwd),
    )
    if writer_conflict:
        sys.stderr.write("source-writer-gate: %s\n" % writer_conflict)
        return 2
    prerequisites = mutation_prerequisite_findings(
        cwd,
        session_id,
        payload.get("turn_id") or "",
    )
    if prerequisites:
        return block(tool_name, prerequisites, cwd)

    if _tool_key(tool_name) == "applypatch":
        # Codex's write tool: a V4A patch envelope, not file+content. Each
        # touched file runs the path checks; Add File carries full content and
        # runs the whole pipeline; Update File applies hunks best-effort and
        # falls back to path checks alone (the Stop floor re-checks the tree).
        return handle_apply_patch(tool_input, cwd, agent_type)

    if tool_name not in ("Edit", "Write"):
        # The permission profile enforces the filesystem/network boundary for
        # tools such as Bash and Agent. The broad hook still proves the live
        # Roblox session before Codex may dispatch them.
        return 0
    path = tool_input.get("file_path")
    content = tool_input.get("content") if tool_name == "Write" else tool_input.get("new_string")
    original_content = content
    if not path or content is None:
        sys.stderr.write(gatelib.blocker_instruction("new-task", cwd) + "\n")
        return 2
    if not os.path.isabs(path):
        path = os.path.join(cwd, path)
    if not path.endswith(".luau") and not path.endswith(".lua"):
        return 0  # non-luau writes are not this gate's subject
    rel_check = os.path.relpath(os.path.realpath(path), os.path.realpath(cwd)).replace(os.sep, "/")
    if rel_check.startswith(".."):
        # Outside the project tree entirely. A harness-checkout task owns its
        # own source; managed projects do not own external paths.
        if gatelib.is_harness(cwd):
            return 0

    if tool_name == "Write":
        content, _, repair_error = fix_source_text(content, cwd)
        if repair_error:
            return block(
                tool_name,
                [
                    (
                        path,
                        0,
                        0,
                        "GATE4",
                        "source auto-fix failed: %s" % repair_error,
                        "repair the deterministic source transform",
                    )
                ],
                cwd,
            )

    findings = []
    findings += check_gate2(path, cwd)
    findings += check_gate3(path)
    findings += check_debug2(path, content, cwd, agent_type)
    if findings:
        # path-level refusals stand alone; content checks would only stack
        # noise on a write that is already not landing
        return block(tool_name, findings, cwd)

    try:
        with open(path, encoding="utf-8") as handle:
            before_content = handle.read()
    except OSError:
        before_content = ""
    if tool_name == "Write":
        resulting_content = content
    else:
        old_string = tool_input.get("old_string", "")
        resulting_content = before_content.replace(old_string, content, 1) if old_string and old_string in before_content else None
    if resulting_content is not None:
        findings += check_type_system(path, before_content, resulting_content, cwd, session_id)

    findings += check_bc4(path, content)
    findings += check_pragmas(path, content)
    findings += check_type8(path, content)
    findings += check_bc1_handler(path, content)
    findings += check_data_rules(path, content)
    findings += check_payments(path, content)

    # full-content checks run on a temp holding the resulting file: Write is
    # whole-content; Edit fragments are checked as fragments (a fragment isn't
    # a syntactic unit, so only Write formats)
    rel = os.path.relpath(os.path.realpath(path), os.path.realpath(cwd)).replace(os.sep, "/")
    scan_target = None
    tmp_dir = tempfile.mkdtemp(prefix="write_gate_")
    try:
        if tool_name == "Write":
            scan_target = os.path.join(tmp_dir, rel)
            os.makedirs(os.path.dirname(scan_target), exist_ok=True)
            with open(scan_target, "w", encoding="utf-8") as f:
                f.write(content)
        elif os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                current = f.read()
            old = tool_input.get("old_string", "")
            if old and old in current:
                scan_target = os.path.join(tmp_dir, rel)
                os.makedirs(os.path.dirname(scan_target), exist_ok=True)
                with open(scan_target, "w", encoding="utf-8") as f:
                    f.write(current.replace(old, content, 1))
        if scan_target:
            in_tests = rel.startswith("tests/")
            r = run_tool([sys.executable, os.path.join(TOOLS, "deny_scan", "deny_scan.py"), "--root", tmp_dir, scan_target])
            if r.returncode == 2:
                found = False
                for line in r.stderr.splitlines():
                    m = re.match(r"^(\d+)\|(\d+)\|(\w+)\|(.*)\|(.*)$", line)
                    if m:
                        found = True
                        findings.append((path, int(m.group(1)), int(m.group(2)), m.group(3), m.group(4), m.group(5)))
                if not found:
                    findings.append((path, 0, 0, "GATE4", "deny_scan exit 2", ""))
            elif r.returncode not in (0, 2):
                findings.append((path, 0, 0, "GATE4", "deny_scan exit %d" % r.returncode, (r.stderr or "").strip()[:120] or "tool crashed"))
            if not in_tests:
                r = run_tool([sys.executable, os.path.join(TOOLS, "replication_audit", "replication_audit.py"), "--root", tmp_dir, scan_target])
                if r.returncode == 2:
                    found = False
                    for line in r.stderr.splitlines():
                        m = re.match(r"^(\d+)\|(\d+)\|(\w+)\|(.*)\|(.*)$", line)
                        if m:
                            found = True
                            findings.append((path, int(m.group(1)), int(m.group(2)), m.group(3), m.group(4), m.group(5)))
                    if not found:
                        findings.append((path, 0, 0, "GATE4", "replication_audit exit 2", ""))
                elif r.returncode not in (0, 2):
                    findings.append((path, 0, 0, "GATE4", "replication_audit exit %d" % r.returncode, (r.stderr or "").strip()[:120] or "tool crashed"))
            # GATE1: a .Data write of a non-serializable value -> data_check
            r = run_tool([gatelib.LUTE, "run", os.path.join(TOOLS, "data_check", "data_check.luau"), "--static", scan_target])
            if r.returncode == 2:
                found = False
                for line in r.stdout.splitlines():
                    m = re.match(r"^(\d+)\|(\d+)\|(\w+)\|(.*)\|(.*)$", line)
                    if m:
                        found = True
                        findings.append((path, int(m.group(1)), int(m.group(2)), m.group(3), m.group(4), m.group(5)))
                if not found:
                    findings.append((path, 0, 0, "GATE4", "data_check exit 2", ""))
            elif r.returncode != 0:
                findings.append((path, 0, 0, "GATE4", "data_check exit %d" % r.returncode, ""))
    finally:
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)

    if findings:
        denied = block(tool_name, findings, cwd)
        if denied:
            return denied

    # formats .luau on Write (whole file, parseable) — emitted as updatedInput
    # when the harness honors it; the floor re-formats either way
    if tool_name == "Write":
        updated_content, format_error = format_write_source(path, content)
        if format_error:
            return block(
                tool_name,
                [
                    (
                        path,
                        0,
                        0,
                        "GATE4",
                        "required style repair failed: %s" % format_error,
                        "repair the parse-verified formatter",
                    )
                ],
                cwd,
            )
        if updated_content != original_content:
            gatelib.emit_json(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "allow",
                        "updatedInput": {"file_path": path, "content": updated_content},
                    }
                }
            )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        sys.stderr.write(
            "Run harness verification, fix the failure, and retry: python3 %s\n"
            % os.path.join(TOOLS, "tests", "run_verify.py")
        )
        sys.exit(2)
