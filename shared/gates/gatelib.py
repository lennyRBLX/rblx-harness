"""Shared plumbing for the gates. Every authorization check fails closed."""

import contextlib
import csv
import hashlib
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import time

try:
    import tomllib
except ImportError:  # pragma: no cover - Python 3.11+ is the supported runtime
    tomllib = None

HARNESS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS = os.path.join(HARNESS, "tools")
sys.path.insert(0, TOOLS)
import houseout  # noqa: E402
import rule_policy  # noqa: E402
from type_core import read_tool_records  # noqa: E402

CACHE = os.path.expanduser("~/.cache/harness")
CORPUS_REFRESH = os.path.join(CACHE, "corpus-refresh.json")
CORPUS_MAX_AGE = 86400
GIT_REPAIR_TIMEOUT = 2400


def bundled_tool_path(name, windows=None):
    """Return the host-native path for a tool installed under tools/bin."""
    windows = os.name == "nt" if windows is None else bool(windows)
    suffix = ".exe" if windows and not str(name).lower().endswith(".exe") else ""
    return os.path.join(TOOLS, "bin", str(name) + suffix)


LUTE = bundled_tool_path("lute")
LUAU_LSP = bundled_tool_path("luau-lsp")
PORT_CACHE = os.path.join(CACHE, "studiomcp.port")
PLACE_CACHE = os.path.join(CACHE, "studiomcp.place")
TTL = 30
REVIEW_TTL = 3600
AGENT_MAILBOX_TTL = 3600

RECOVERY_API_SYNC = "api-sync"
RECOVERY_API_GLOBALS = "api-globals"
RECOVERY_GIT_SYNC = "git-sync"
RECOVERY_TYPE_CACHE = "type-cache"
RECOVERY_TOOLCHAIN = "toolchain"
RECOVERY_RELINK = "relink"
RECOVERY_KINDS = {
    RECOVERY_API_SYNC,
    RECOVERY_API_GLOBALS,
    RECOVERY_GIT_SYNC,
    RECOVERY_TYPE_CACHE,
    RECOVERY_TOOLCHAIN,
    RECOVERY_RELINK,
}

PERMISSIONS_HARNESS_PROFILE = "Roblox"
PROJECT_HARNESS_DIR = ".roblox-harness"
RELATIVE_HARNESS = PROJECT_HARNESS_DIR
HANDOFF_RELATIVE = "shared/handoff.md"
RELATIVE_PERMISSIONS_SETUP = PROJECT_HARNESS_DIR + "/openai/setup/permissions_harness.py"
PERMISSIONS_HARNESS_INSTALL_PROMPT = (
    "Install + select the Roblox permission mode; retry the current task: "
    "python3 %s --install"
) % RELATIVE_PERMISSIONS_SETUP
PERMISSIONS_HARNESS_SELECT_PROMPT = (
    "Select the Roblox permission mode; retry the current task."
)
PERMISSIONS_HARNESS_INSTALLED_PROMPT = (
    "Roblox permission mode installed. Select it; retry the current task."
)
PERMISSIONS_HARNESS_STARTUP_MARKER = "ROBLOX_HARNESS_STARTUP_BLOCKED"
REQUIRED_CODEX_AGENTS = ("debugger", "maintainer", "optimizer", "researcher", "reviewer")
PERMISSIONS_HARNESS_CONFIG = '''default_permissions = "Roblox"

[permissions.Roblox]
extends = ":workspace"

[permissions.Roblox.filesystem]
"~/.cache/harness" = "write"
"~/.cache/harness/creator-docs/.git" = "write"

[permissions.Roblox.filesystem.":workspace_roots"]
".git" = "write"
".roblox-harness/tools/bin" = "write"
"tools/bin" = "write"

[permissions.Roblox.network]
enabled = true

[permissions.Roblox.network.domains]
"raw.githubusercontent.com" = "allow"
"github.com" = "allow"
"codeload.github.com" = "allow"
"objects.githubusercontent.com" = "allow"
"release-assets.githubusercontent.com" = "allow"
"localhost" = "allow"
"127.0.0.1" = "allow"'''

PERMISSIONS_HARNESS_REMEDIATION = (
    "Install + select the Roblox permission mode; retry the current task: "
    "python3 %s --install"
) % RELATIVE_PERMISSIONS_SETUP

REQUIRED_ROBLOX_PROFILE = {
    "extends": ":workspace",
    "filesystem": {
        "~/.cache/harness": "write",
        "~/.cache/harness/creator-docs/.git": "write",
        ":workspace_roots": {
            ".git": "write",
            ".roblox-harness/tools/bin": "write",
            "tools/bin": "write",
        },
    },
    "network": {
        "enabled": True,
        "domains": {
            "raw.githubusercontent.com": "allow",
            "github.com": "allow",
            "codeload.github.com": "allow",
            "objects.githubusercontent.com": "allow",
            "release-assets.githubusercontent.com": "allow",
            "localhost": "allow",
            "127.0.0.1": "allow",
        },
    },
}
# Codex maps approval_policy=never to the legacy hook label
# ``bypassPermissions`` even when a managed permission profile and restricted
# sandbox remain active.  Safety is decided from those resolved runtime
# structures below, not from this approval-policy label.
SAFE_PERMISSION_MODES = {"default", "acceptEdits", "plan", "dontAsk", "bypassPermissions"}
UNRESTRICTED_PROFILE_TYPES = {"disabled", "unrestricted", "danger-full-access"}

# the ruled corpus, baked in — rules.json does not survive the build
ACCEPTED_IDS = {
    "BC1", "BC2", "BC3", "BC4", "BC5", "BC6", "BC7",
    "DATA1", "DATA4", "DATA5", "DATA6", "DATA8", "DATA17", "DATA21", "DATA23",
    "DATA29", "DATA30", "DATA31", "DATA32", "DATA33", "DATA34", "DATA35", "DATA36", "DATA37",
    "DEBUG1", "DEBUG2", "DEBUG8", "DEBUG11",
    "DES2", "DES3", "DES5",
    "GATE1", "GATE2", "GATE3", "GATE4", "GATE5", "GATE6", "GATE7",
    "OPT1", "OPT2", "OPT4", "OPT5", "OPT8", "OPT11", "OPT12", "OPT15", "OPT16",
    "OPT17", "OPT18", "OPT19", "OPT20", "OPT21", "OPT22", "OPT23", "OPT24",
    "OUT1", "OUT2", "OUT3", "OUT4", "OUT6",
    "REV2", "REV4", "REV6", "REV9", "REV10", "REV11",
    "TYPE1", "TYPE2", "TYPE3", "TYPE4", "TYPE7", "TYPE8", "TYPE9",
    "WRIT1", "WRIT4", "WRIT8", "WRIT10", "WRIT11", "WRIT12", "WRIT14", "WRIT15",
    "WRIT18", "WRIT19", "WRIT20", "WRIT22", "WRIT23", "WRIT25", "WRIT26",
    "WRIT29", "WRIT30", "WRIT31", "WRIT32", "WRIT33",
}

REMOVED_IDS = {
    "DATA2", "DATA3", "DATA7", "DATA9", "DATA10", "DATA11", "DATA12", "DATA13",
    "DATA14", "DATA15", "DATA16", "DATA18", "DATA19", "DATA20", "DATA22",
    "DATA24", "DATA25", "DATA26", "DATA27", "DATA28",
    "DEBUG3", "DEBUG4", "DEBUG5", "DEBUG6", "DEBUG7", "DEBUG9", "DEBUG10",
    "DEBUG12", "DEBUG13",
    "DES1", "DES4",
    "OPT3", "OPT6", "OPT7", "OPT9", "OPT10",
    "OUT5",
    "REV1", "REV3", "REV5", "REV7", "REV8",
    "TYPE5", "TYPE6", "TYPE10",
    "WRIT2", "WRIT3", "WRIT5", "WRIT6", "WRIT7", "WRIT9", "WRIT13", "WRIT16",
    "WRIT21", "WRIT24", "WRIT27", "WRIT28",
}


def project_name(cwd):
    root = os.path.realpath(cwd) if isinstance(cwd, str) and cwd else ""
    return os.path.basename(root.rstrip(os.sep)) or "project"


def relink_command(cwd):
    return shlex.join(
        [
            "python3",
            RELATIVE_PERMISSIONS_SETUP,
            "--relink",
        ]
    )


def finalization_command(cwd, session_id):
    """Render the exact pre-final validation command for this turn."""
    parts = [
        sys.executable,
        os.path.join(HARNESS, "shared", "gates", "finalize.py"),
        "--root",
        os.path.realpath(cwd),
        "--session",
        str(session_id),
    ]
    return subprocess.list2cmdline(parts) if os.name == "nt" else shlex.join(parts)


def blocker_instruction(code, cwd="", **values):
    """Render one short developer action for a typed write blocker."""
    project = project_name(cwd)
    messages = {
        "new-task": "Start a new Codex task in %s." % project,
        "studio-place": "Open the %s place in Roblox Studio; retry." % project,
        "studio-connect": "Open the %s place and enable MCP in Roblox Studio Assistant Settings; retry." % project,
        "studio-mcp": "Enable MCP in Roblox Studio Assistant Settings; retry.",
        "studio-restart": "Restart Roblox Studio; open the %s place; enable MCP; retry." % project,
        "studio-install": "Install or repair Roblox Studio; retry.",
        "studio-publish": "Publish the %s place in Roblox Studio; retry." % project,
        "studio-ambiguous": "Close other Roblox Studio places; keep %s open; retry." % project,
        "studio-busy": "Wait for the Codex task using %s to finish; retry." % project,
        "permission-install": PERMISSIONS_HARNESS_INSTALL_PROMPT,
        "permission-select": PERMISSIONS_HARNESS_SELECT_PROMPT,
        "trust": "Trust %s in Codex; retry the current task." % project,
        "hooks": "Relink %s; review its hooks; retry the current task: %s" % (project, relink_command(cwd)),
        "cache-write": "Allow writes to ~/.cache/harness; retry the current task.",
        "git-write": "Allow read/write access to %s/.git; retry the current task." % os.path.realpath(cwd),
    }
    return messages.get(code, messages["new-task"])


def read_payload():
    try:
        return json.load(sys.stdin)
    except Exception:
        return None


def hook_scope(argv):
    try:
        index = argv.index("--hook-scope")
        value = argv[index + 1]
    except (ValueError, IndexError):
        return ""
    return value if value in ("project", "user") else ""


def hook_host(argv, payload=None):
    try:
        index = argv.index("--host")
        value = argv[index + 1]
    except (ValueError, IndexError):
        value = payload.get("_harness_host") if isinstance(payload, dict) else ""
    return value if value in ("codex", "claude") else ""


# the DataModel's own containers — every name Argon mounts as a service or as a
# Starter* container, none of which may BE a script [R GATE2]
SERVICE_DIRS = {
    "Chat",
    "Lighting",
    "LocalizationService",
    "MaterialService",
    "Players",
    "ReplicatedFirst",
    "ReplicatedStorage",
    "ServerScriptService",
    "ServerStorage",
    "SoundService",
    "StarterCharacterScripts",
    "StarterGui",
    "StarterPack",
    "StarterPlayer",
    "StarterPlayerScripts",
    "Teams",
    "TestService",
    "TextChatService",
    "VoiceChatService",
    "Workspace",
}


def service_init_container(rel):
    """A service is never a script. An init.luau — or any init.<type>.luau —
    directly under a service directory makes Argon emit the SERVICE as that
    script; entries are named children instead
    (ServerScriptService/Server.server.luau,
    StarterPlayerScripts/Client.client.luau). One level down the form is legal
    and expected: Services/Shop/init.luau is a directory package whose parent
    is a folder, not a service.

    Returns the offending container's path, or None when the file is fine."""
    rel = rel.replace(os.sep, "/")
    if not re.match(r"^init(\.\w+)?\.luau?$", rel.rsplit("/", 1)[-1]):
        return None
    m = re.match(r"^(?:shared/src|places/[^/]+/src)/(.*)$", rel)
    if not m:
        return None
    chain = m.group(1).split("/")[:-1]
    if any(seg not in SERVICE_DIRS for seg in chain):
        return None  # a folder stands between it and the service — a package
    return "/".join(chain) or "the DataModel root"


def preconditions_path(cwd):
    return os.path.join(cwd, "gates", ".preconditions")


def _preconditions_failure(detail):
    return [
        "GATE4|preconditions %s|Start a new Codex task in the project."
        % detail[:160]
    ]


def _valid_precondition(record):
    if not isinstance(record, str):
        return False
    parts = record.split("|")
    return (
        len(parts) == 3
        and parts[0] in ("GATE4", "GATE6")
        and bool(parts[1].strip())
        and bool(parts[2].strip())
    )


def write_preconditions(cwd, session_id, records):
    """Atomically persist a session-bound READY or BLOCKED gate result."""
    records = list(records)
    if any(not _valid_precondition(record) for record in records):
        records = [
            "GATE4|preconditions producer emitted a malformed gate record|Run harness verification; fix the failure; retry: python3 %s"
            % os.path.join(TOOLS, "tests", "run_verify.py")
        ]
    if not session_id and not any("|session identity absent|" in record for record in records):
        records.append(
            "GATE4|session identity absent|Start a new Codex task in the project."
        )
    state = {
        "schema": 1,
        "session": _session_key(session_id),
        "status": "BLOCKED" if records else "READY",
        "errors": records,
    }
    _atomic_text(preconditions_path(cwd), json.dumps(state, sort_keys=True) + "\n")


def read_preconditions(cwd, session_id=None):
    """Read the session gate state. Missing, unreadable, or malformed state
    is itself a blocking precondition; it never means an empty set."""
    path = preconditions_path(cwd)
    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
    except FileNotFoundError:
        return _preconditions_failure("absent")
    except (OSError, ValueError, UnicodeError) as e:
        return _preconditions_failure("unreadable or malformed: %s" % str(e))
    if not isinstance(state, dict) or state.get("schema") != 1:
        return _preconditions_failure("malformed: unsupported schema")
    expected_session = _session_key(session_id) if session_id is not None else None
    recorded_session = state.get("session")
    if not isinstance(recorded_session, str) or not re.fullmatch(r"[0-9a-f]{20}", recorded_session):
        return _preconditions_failure("malformed: invalid session identity")
    if expected_session is not None and recorded_session != expected_session:
        return _preconditions_failure("belongs to a different Codex session")
    status = state.get("status")
    records = state.get("errors")
    if not isinstance(records, list) or any(not _valid_precondition(record) for record in records):
        return _preconditions_failure("malformed: invalid gate record")
    if status == "READY" and not records:
        return []
    if status == "BLOCKED" and records:
        return records
    return _preconditions_failure("malformed: status and gate records disagree")


def codex_config_path():
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return os.path.join(os.path.expanduser(codex_home), "config.toml")
    return os.path.expanduser("~/.codex/config.toml")


def _load_codex_config(config_path=None):
    path = config_path or codex_config_path()
    if tomllib is None:
        return None, path, "Python tomllib is unavailable"
    try:
        with open(path, "rb") as f:
            config = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        return None, path, "%s: %s" % (path, str(e)[:160])
    if not isinstance(config, dict):
        return None, path, "%s: top level is not a table" % path
    return config, path, ""


def _toml_table_name(line):
    match = re.match(r"^\s*\[([^\[\]]+)\]\s*(?:#.*)?$", line)
    return match.group(1).strip() if match else None


def _toml_assignment_key(line):
    match = re.match(r"^\s*([A-Za-z0-9_-]+)\s*=", line)
    return match.group(1) if match else None


def _toml_sections(text):
    sections = [("", [])]
    multiline = ""
    for line in text.splitlines(keepends=True):
        if not multiline:
            table = _toml_table_name(line)
            if table is not None:
                sections.append((table, [line]))
                continue
        sections[-1][1].append(line)
        for delimiter in ('"""', "'''"):
            if multiline and delimiter == multiline:
                if line.count(delimiter) % 2:
                    multiline = ""
                break
            if not multiline and line.count(delimiter) % 2:
                multiline = delimiter
                break
    return sections


def merge_project_codex_config(existing, canonical):
    """Merge harness-owned Codex keys while retaining unrelated project TOML.

    Standalone agent discovery supersedes only the five harness-owned legacy
    ``[agents.<role>]`` tables. Other project keys, comments, and custom agent
    tables remain byte-stable apart from surrounding managed assignments.
    """
    if tomllib is None:
        raise ValueError("Python tomllib is unavailable")
    try:
        if existing.strip():
            tomllib.loads(existing)
        tomllib.loads(canonical)
    except tomllib.TOMLDecodeError as error:
        raise ValueError("project Codex config is malformed: %s" % str(error)[:160])

    canonical_sections = _toml_sections(canonical)
    managed = {
        name: {
            key
            for key in (
                _toml_assignment_key(line)
                for line in (lines[1:] if name else lines)
            )
            if key
        }
        for name, lines in canonical_sections
    }
    canonical_assignments = {
        name: [
            line
            for line in (lines[1:] if name else lines)
            if _toml_assignment_key(line) in keys
        ]
        for (name, lines), keys in zip(canonical_sections, managed.values())
    }

    output = []
    seen = set()
    legacy_prefixes = tuple("agents.%s" % name for name in REQUIRED_CODEX_AGENTS)
    for name, lines in _toml_sections(existing):
        if name in legacy_prefixes or any(name.startswith(prefix + ".") for prefix in legacy_prefixes):
            continue
        if name not in managed:
            output.extend(lines)
            continue
        seen.add(name)
        keys = managed[name]
        header = lines[:1] if name else []
        body = lines[1:] if name else lines
        retained = [line for line in body if _toml_assignment_key(line) not in keys]
        trailing = []
        while retained and not retained[-1].strip():
            trailing.insert(0, retained.pop())
        output.extend(header)
        output.extend(retained)
        output.extend(canonical_assignments[name])
        output.extend(trailing)

    for name, lines in canonical_sections:
        if name in seen:
            continue
        if output and output[-1].strip():
            output.append("\n")
        output.extend(lines)

    merged = "".join(output).strip() + "\n"
    try:
        tomllib.loads(merged)
    except tomllib.TOMLDecodeError as error:
        raise ValueError("merged project Codex config is malformed: %s" % str(error)[:160])
    return merged


def required_codex_agents_status(root):
    """Validate the complete standalone agent discovery surface."""
    project = os.path.realpath(root)
    agents_dir = os.path.join(project, ".codex", "agents")
    if not os.path.isdir(agents_dir) or os.path.islink(agents_dir):
        return False, "%s is absent or is not a project directory" % agents_dir

    for name in REQUIRED_CODEX_AGENTS:
        source = os.path.join(HARNESS, "openai", "agents", name + ".toml")
        destination = os.path.join(agents_dir, name + ".toml")
        if not os.path.lexists(destination):
            return False, "%s is absent" % destination
        if os.path.islink(destination):
            return False, "%s is incorrectly linked; standalone agent definitions must be regular files" % destination
        if not os.path.isfile(destination):
            return False, "%s is not a regular file" % destination
        if not os.access(destination, os.R_OK):
            return False, "%s is unreadable" % destination
        try:
            with open(source, "rb") as expected_file, open(destination, "rb") as actual_file:
                if expected_file.read() != actual_file.read():
                    return False, "%s does not match its harness definition" % destination
        except OSError as error:
            return False, "%s is unreadable: %s" % (destination, str(error)[:120])
        try:
            with open(destination, "rb") as handle:
                definition = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as error:
            return False, "%s is unreadable or invalid: %s" % (destination, str(error)[:120])
        if (
            definition.get("name") != name
            or not isinstance(definition.get("description"), str)
            or not definition["description"].strip()
            or not isinstance(definition.get("developer_instructions"), str)
            or not definition["developer_instructions"].strip()
        ):
            return False, "%s has an invalid standalone agent definition" % destination

    config, path, error = _load_codex_config(os.path.join(project, ".codex", "config.toml"))
    if error:
        return False, "project Codex config is unreadable: %s" % error
    features = config.get("features")
    if not isinstance(features, dict) or features.get("multi_agent") is not True:
        return False, "%s does not enable features.multi_agent" % path
    agents = config.get("agents")
    if not isinstance(agents, dict) or agents.get("enabled") is not True:
        return False, "%s does not enable agents" % path
    if isinstance(agents, dict) and any(name in agents for name in REQUIRED_CODEX_AGENTS):
        return False, "%s still contains obsolete harness agent tables" % path
    return True, ""


def execute_luau_approval_override(root):
    """Verify the one StudioMCP write-tool approval owned by the project."""
    config, path, error = _load_codex_config(os.path.join(os.path.realpath(root), ".codex", "config.toml"))
    if error:
        return False, "project Codex config unreadable: %s" % error
    servers = config.get("mcp_servers")
    studio = servers.get("Roblox_Studio") if isinstance(servers, dict) else None
    tools = studio.get("tools") if isinstance(studio, dict) else None
    execute_luau = tools.get("execute_luau") if isinstance(tools, dict) else None
    mode = execute_luau.get("approval_mode") if isinstance(execute_luau, dict) else None
    if mode != "approve":
        rendered = "absent" if mode is None else json.dumps(mode, ensure_ascii=False)
        return False, "%s execute_luau approval_mode is %s" % (path, rendered)
    return True, ""


def execute_luau_approval_instruction(root):
    return (
        'Relink %s to set [mcp_servers.Roblox_Studio.tools.execute_luau] approval_mode = "approve" '
        "in .codex/config.toml; retry the current task: %s"
        % (project_name(root), relink_command(root))
    )


def _profile_table_header(line):
    return bool(
        re.match(
            r'^\s*\[\s*(?:permissions\s*\.\s*(?:Roblox|"Roblox")\s*(?:\.|\])|sandbox_workspace_write\s*\])',
            line,
        )
    )


def _toml_table_header(line):
    return bool(re.match(r"^\s*\[\[?[^]]+\]\]?\s*(?:#.*)?$", line))


def _without_permissions_harness(text):
    """Remove only the settings owned by PERMISSIONS_HARNESS_CONFIG."""
    kept = []
    in_profile = False
    at_root = True
    for line in text.splitlines():
        if _profile_table_header(line):
            in_profile = True
            at_root = False
            continue
        if _toml_table_header(line):
            in_profile = False
            at_root = False
        if in_profile:
            continue
        if at_root and re.match(
            r'^\s*(?:default_permissions|sandbox_mode|sandbox_workspace_write)\s*=',
            line,
        ):
            continue
        kept.append(line)
    return "\n".join(kept).rstrip()


def _split_root_settings(text):
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if _toml_table_header(line):
            return "\n".join(lines[:index]).rstrip(), "\n".join(lines[index:]).strip()
    return text.rstrip(), ""


def install_permissions_harness(config_path=None):
    """Install the canonical profile and retain all unrelated TOML settings.

    The operation is byte-idempotent. Authorization revalidates the installed
    profile in the current task; identity-bound records are preserved.
    """
    path = config_path or codex_config_path()
    try:
        with open(path, encoding="utf-8") as f:
            original = f.read()
    except FileNotFoundError:
        original = ""
    except (OSError, UnicodeError) as error:
        return False, "%s: %s" % (path, str(error)[:160]), False
    if original.strip():
        if tomllib is None:
            return False, "Python tomllib is unavailable", False
        try:
            parsed = tomllib.loads(original)
        except tomllib.TOMLDecodeError as error:
            return False, "%s: %s" % (path, str(error)[:160]), False
        if not isinstance(parsed, dict):
            return False, "%s: top level is not a table" % path, False
    retained = _without_permissions_harness(original)
    root_settings, tables = _split_root_settings(retained)
    parts = [part for part in (root_settings, PERMISSIONS_HARNESS_CONFIG, tables) if part]
    installed = "\n\n".join(parts) + "\n"
    changed = installed != original
    try:
        if changed:
            _atomic_text(path, installed)
    except OSError as error:
        return False, "%s: %s" % (path, str(error)[:160]), False
    ok, detail = permissions_harness(path)
    if not ok:
        return False, detail, changed
    return True, path, changed


def codex_hooks_path():
    return os.path.join(os.path.dirname(codex_config_path()), "hooks.json")


def _owned_user_hook(entry):
    if not isinstance(entry, dict):
        return False
    handlers = entry.get("hooks")
    if not isinstance(handlers, list):
        return False
    return any(
        isinstance(handler, dict)
        and any(name in hook_handler_text(handler) for name in ("user_launcher.py", "/openai/hooks/adapter.py"))
        and "--hook-scope user" in hook_handler_text(handler)
        for handler in handlers
    )


def install_user_hooks(path=None):
    """Install one stable user hook bootstrap; preserve unrelated hooks."""
    target = path or codex_hooks_path()
    try:
        with open(target, encoding="utf-8") as handle:
            original = handle.read()
    except FileNotFoundError:
        original = ""
    except (OSError, UnicodeError) as error:
        return False, str(error)[:160], False
    if original.strip():
        try:
            document = json.loads(original)
        except ValueError as error:
            return False, "%s: %s" % (target, str(error)[:160]), False
        if not isinstance(document, dict):
            return False, "%s: top level is not an object" % target, False
    else:
        document = {}
    template_path = os.path.join(HARNESS, "openai", "hooks", "bootstrap.json")
    launcher_source = os.path.join(HARNESS, "openai", "hooks", "user_launcher.py")
    launcher_path = os.path.join(os.path.dirname(target), "hooks", "user_launcher.py")
    try:
        with open(launcher_source, encoding="utf-8") as handle:
            launcher_text = handle.read()
        with open(template_path, encoding="utf-8") as handle:
            escaped_launcher = json.dumps(launcher_path, ensure_ascii=False)[1:-1]
            canonical = json.loads(handle.read().replace("{{LAUNCHER}}", escaped_launcher))
    except (OSError, ValueError, UnicodeError) as error:
        return False, "%s: %s" % (template_path, str(error)[:160]), False
    if os.name == "nt":
        for entries in canonical["hooks"].values():
            for entry in entries:
                for handler in entry.get("hooks", []):
                    suffix = str(handler.get("command", "")).split('" --host ', 1)
                    if len(suffix) != 2:
                        return False, "%s: unsupported user hook command" % template_path, False
                    handler["commandWindows"] = subprocess.list2cmdline(
                        [sys.executable, "-B", launcher_path]
                    ) + " --host " + suffix[1]
    hooks = document.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
    for event, owned_entries in canonical["hooks"].items():
        existing = hooks.get(event)
        kept = [entry for entry in existing if not _owned_user_hook(entry)] if isinstance(existing, list) else []
        hooks[event] = kept + owned_entries
    document["hooks"] = hooks
    installed = json.dumps(document, indent=1, ensure_ascii=False) + "\n"
    changed = installed != original
    try:
        launcher_changed = True
        try:
            with open(launcher_path, encoding="utf-8") as handle:
                launcher_changed = handle.read() != launcher_text
        except OSError:
            pass
        if launcher_changed:
            _atomic_text(launcher_path, launcher_text)
        if changed:
            _atomic_text(target, installed)
    except OSError as error:
        return False, "%s: %s" % (target, str(error)[:160]), False
    return True, target, changed or launcher_changed


def _json_digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def permissions_harness(config_path=None):
    """Read-only verification of the exact user-level Roblox definition.

    This verifies configuration only. It is never proof that the current
    Codex session loaded the profile.
    """
    config, _, error = _load_codex_config(config_path)
    if error:
        return False, error

    problems = []
    if config.get("default_permissions") != PERMISSIONS_HARNESS_PROFILE:
        problems.append('default_permissions must be "Roblox"')
    if "sandbox_mode" in config or "sandbox_workspace_write" in config:
        problems.append("legacy sandbox settings must be removed")
    permissions = config.get("permissions")
    profile = permissions.get(PERMISSIONS_HARNESS_PROFILE) if isinstance(permissions, dict) else None
    if not isinstance(profile, dict):
        problems.append("[permissions.Roblox] is absent")
    elif profile != REQUIRED_ROBLOX_PROFILE:
        problems.append("[permissions.Roblox] must exactly match the required preset")
    return (not problems), "; ".join(problems)


def permissions_harness_digest(config_path=None):
    ok, detail = permissions_harness(config_path)
    if not ok:
        return None, detail
    return _json_digest(
        {
            "default_permissions": PERMISSIONS_HARNESS_PROFILE,
            "profile": REQUIRED_ROBLOX_PROFILE,
        }
    ), ""


def permissions_harness_block(detail):
    return "BLOCKED|PERMISSIONS_HARNESS\n%s" % permissions_harness_stop_reason(detail)


def session_block(host, detail, cwd=""):
    if host == "codex":
        return permissions_harness_stop_reason(detail, cwd)
    return "BLOCKED|HARNESS\n%s" % (detail or "Start a new Claude Code session.")


def permissions_harness_stop_reason(detail, cwd=""):
    """Return the concise SessionStart explanation shown by Codex."""
    text = str(detail or "permission profile could not be verified")
    static_profile_failures = (
        'default_permissions must be "Roblox"',
        "legacy sandbox settings must be removed",
        "[permissions.Roblox] is absent",
        "[permissions.Roblox] must exactly match the required preset",
        "config.toml",
    )
    if any(problem in text for problem in static_profile_failures):
        return blocker_instruction("permission-install", cwd)
    if text.startswith(("Open ", "Enable ", "Restart ", "Install/", "Publish ", "Close ", "Wait ", "Allow ", "Start ", "Relink ", "Run ", "Sync ", "Gen ", "Fix ", "Restore ", "Set ", "Add ")):
        return text.splitlines()[0].strip()
    if "active_permission_profile" in text or "active profile" in text or "permission mode is unknown" in text:
        return blocker_instruction("permission-select", cwd)
    if "trust" in text:
        return blocker_instruction("trust", cwd)
    if any(token in text for token in ("hook", "adapter", "scope", "SessionStart source", "workspace is absent")):
        return blocker_instruction("hooks", cwd)
    if any(token in text for token in ("cache write", "authorization was not created")):
        return blocker_instruction("cache-write", cwd)
    return blocker_instruction("new-task", cwd)


def permissions_harness_prompt_context(reason):
    """Make a denied SessionStart visible despite Codex dropping stopReason."""
    return (
        PERMISSIONS_HARNESS_STARTUP_MARKER + "\n"
        "Startup authorization was not granted. Do not perform the user's task "
        "and do not call tools. Reply to the user with exactly this text and nothing else:\n"
        + reason
    )


def session_precheck_stop_reason(detail, cwd=""):
    """Render the first concrete precheck failure for the user."""
    text = str(detail or "session precheck failed without a diagnostic")
    fallback = None
    for line in text.splitlines():
        if not line.startswith("GATE"):
            continue
        parts = line.split("|", 2)
        subject = parts[1].strip() if len(parts) > 1 else line.strip()
        repair = parts[2].strip() if len(parts) > 2 else "repair the precondition"
        if "SKIPPED" in subject:
            fallback = fallback or repair
            continue
        return repair
    return fallback or permissions_harness_stop_reason(text, cwd)


def permissions_harness_install_accepted(prompt):
    """Recognize an unambiguous answer to the installation offer."""
    if not isinstance(prompt, str):
        return False
    answer = re.sub(r"[^a-z0-9]+", " ", prompt.casefold()).strip()
    return answer in {
        "y",
        "yes",
        "yes please",
        "agree",
        "i agree",
        "approve",
        "i approve",
        "ok",
        "okay",
        "sure",
        "do it",
        "add it",
        "install it",
        "add roblox",
        "install roblox",
        "add the roblox permission mode",
        "install the roblox permission mode",
    }


def require_permissions_harness(config_path=None):
    ok, detail = permissions_harness(config_path=config_path)
    return ok, "" if ok else permissions_harness_block(detail)


def project_trust_status(cwd, config_path=None):
    """Resolve the most specific user-config project trust entry."""
    config, _, error = _load_codex_config(config_path)
    if error:
        return False, error
    root = os.path.realpath(cwd)
    projects = config.get("projects")
    if not isinstance(projects, dict):
        return False, "project trust is absent"
    candidates = []
    for path, value in projects.items():
        if not isinstance(path, str) or not isinstance(value, dict):
            continue
        candidate = os.path.realpath(os.path.expanduser(path))
        try:
            if os.path.commonpath((root, candidate)) == candidate:
                candidates.append((len(candidate), candidate, value.get("trust_level")))
        except ValueError:
            continue
    if not candidates:
        return False, "project is not listed as trusted"
    _, path, level = max(candidates)
    if level != "trusted":
        return False, "%s is %s" % (path, level or "not trusted")
    return True, ""


def hook_source_path(cwd, scope, host="codex"):
    if scope == "project":
        if host == "codex":
            return os.path.join(os.path.realpath(cwd), ".codex", "hooks.json")
        if host == "claude":
            return os.path.join(os.path.realpath(cwd), ".claude", "settings.json")
    if scope == "user" and host == "codex":
        return os.path.join(os.path.dirname(codex_config_path()), "hooks.json")
    return ""


def hook_handler_text(handler):
    if not isinstance(handler, dict):
        return ""
    parts = [str(handler.get("command", ""))]
    args = handler.get("args")
    if isinstance(args, list):
        parts.extend(str(value) for value in args)
    windows = handler.get("commandWindows", handler.get("command_windows"))
    if isinstance(windows, str):
        parts.append(windows)
    return " ".join(part for part in parts if part)


def _hook_commands(document, event):
    hooks = document.get("hooks") if isinstance(document, dict) else None
    entries = hooks.get(event) if isinstance(hooks, dict) else None
    commands = []
    if not isinstance(entries, list):
        return commands
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for handler in entry.get("hooks", []):
            if isinstance(handler, dict) and handler.get("type") == "command" and not handler.get("async"):
                commands.append((entry.get("matcher"), hook_handler_text(handler)))
    return commands


def hook_command_disables_bytecode(command):
    """Accept the native Unix env form or Python's portable -B switch."""
    return isinstance(command, str) and (
        "PYTHONDONTWRITEBYTECODE=1" in command
        or bool(re.search(r"(?:^|\s)-B(?:\s|$)", command))
    )


def hook_definition_status(cwd, scope, host="codex"):
    """Verify the exact running bootstrap source and return its file digest.

    Codex skips unapproved definitions. A matching hook invocation is the
    runtime approval evidence; this function verifies the invoked source is
    still the source that contains the blocking contract.
    """
    path = hook_source_path(cwd, scope, host)
    if not path:
        return False, "unknown hook scope", None
    try:
        with open(path, "rb") as f:
            raw = f.read()
        document = json.loads(raw)
    except (OSError, ValueError, UnicodeError) as e:
        return False, "hook bootstrap unavailable or malformed: %s" % str(e)[:160], None
    adapter = (
        "user_launcher.py"
        if scope == "user" and host == "codex"
        else "%s/hooks/adapter.py" % ("openai" if host == "codex" else "claude")
    )
    required = {"SessionStart", "PreToolUse"}
    if scope == "project":
        required.update({"Stop", "PreCompact", "SubagentStart", "SubagentStop", "UserPromptSubmit"})
    for event in required:
        found = False
        for matcher, command in _hook_commands(document, event):
            if not isinstance(command, str):
                continue
            command = command.replace("\\", "/")
            if adapter not in command or "--event %s" % event not in command:
                continue
            if "--hook-scope %s" % scope not in command:
                continue
            if not hook_command_disables_bytecode(command):
                continue
            if event == "SessionStart":
                if not isinstance(matcher, str):
                    continue
                try:
                    sources = ("startup", "resume", "clear", "compact")
                    if host == "claude":
                        sources += ("fork",)
                    if not all(re.search(matcher, source) for source in sources):
                        continue
                except re.error:
                    continue
            elif event == "PreToolUse" and matcher != ".*":
                continue
            found = True
            break
        if not found:
            return False, "%s hook is unavailable or obsolete" % event, None
    return True, "", hashlib.sha256(raw).hexdigest()


def verified_session_snapshot(payload, cwd, hook_scope, expected_event, host=None):
    """Verify only documented hook fields and stable public configuration."""
    if not isinstance(payload, dict):
        return False, "malformed hook payload", None
    host = host or payload.get("_harness_host")
    if host not in ("codex", "claude"):
        return False, "hook host is absent or malformed", None
    if payload.get("hook_event_name") != expected_event:
        return False, "hook event is absent or malformed", None
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        return False, "session identity is absent", None
    hook_ok, detail, hook_digest = hook_definition_status(cwd, hook_scope, host)
    if not hook_ok:
        return False, detail, None
    snapshot = {
        "host": host,
        "root": _session_key(os.path.realpath(cwd)),
        "session": _session_key(session_id),
        "hook_definition": hook_digest,
        "hook_scope": hook_scope,
        "preconditions": [],
    }
    if host == "codex":
        profile_digest, detail = permissions_harness_digest()
        if detail:
            return False, detail, None
        trusted, detail = project_trust_status(cwd)
        if not trusted:
            return False, "project trust verification failed: %s" % detail, None
        permission_mode = payload.get("permission_mode")
        if permission_mode not in SAFE_PERMISSION_MODES:
            return False, "permission mode is unknown: %s" % (permission_mode or "absent"), None
        snapshot.update(
            {
                "profile": PERMISSIONS_HARNESS_PROFILE,
                "permission_mode": permission_mode,
                "profile_definition": profile_digest,
            }
        )
    return True, "", snapshot


def _session_key(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:20]


def session_authorization_path(cwd, session_id):
    root_key = _session_key(os.path.realpath(cwd))
    return os.path.join(CACHE, "sessions", root_key, _session_key(session_id) + ".ready")


def session_failure_path(cwd, session_id):
    root_key = _session_key(os.path.realpath(cwd))
    return os.path.join(CACHE, "sessions", root_key, _session_key(session_id) + ".blocked")


def read_session_failure_record(cwd, session_id):
    if not cwd or not session_id:
        return None
    try:
        with open(session_failure_path(cwd, session_id), encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, ValueError, UnicodeError):
        return None
    return state if isinstance(state, dict) else None


@contextlib.contextmanager
def _session_recovery_lock(cwd, session_id):
    """Serialize degraded-session read/modify/write operations."""
    path = session_failure_path(cwd, session_id)
    lock = path + ".recovery.lock"
    deadline = time.monotonic() + 5
    os.makedirs(os.path.dirname(lock), exist_ok=True)
    while True:
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            try:
                os.write(descriptor, ("%d\n" % os.getpid()).encode("ascii"))
            finally:
                os.close(descriptor)
            break
        except FileExistsError:
            try:
                stale = time.time() - os.path.getmtime(lock) > 30
            except OSError:
                stale = False
            if stale:
                try:
                    os.remove(lock)
                except OSError:
                    pass
                continue
            if time.monotonic() >= deadline:
                raise OSError("recovery-attempt lock timed out")
            time.sleep(0.01)
        except OSError as error:
            raise OSError("recovery-attempt lock failed: %s" % str(error)[:120])
    try:
        yield path
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass


def write_session_failure(cwd, session_id, message):
    if not cwd or not session_id or not message:
        return False
    state = {"schema": 1, "message": str(message).splitlines()[0].strip()}
    try:
        _atomic_text(session_failure_path(cwd, session_id), json.dumps(state, sort_keys=True) + "\n")
        return True
    except OSError:
        return False


def write_session_degraded(cwd, session_id, snapshot, message, repairs):
    """Persist a trusted session that may run only exact recovery commands."""
    repairs = sorted(set(repairs))
    if (
        not cwd
        or not session_id
        or not isinstance(snapshot, dict)
        or not repairs
        or any(repair not in RECOVERY_KINDS for repair in repairs)
    ):
        return False
    stable = {
        key: value
        for key, value in snapshot.items()
        if key not in ("hook_definition", "hook_scope", "preconditions")
    }
    try:
        with _session_recovery_lock(cwd, session_id) as path:
            prior = read_session_failure_record(cwd, session_id)
            attempted = []
            observed_scopes = []
            if (
                isinstance(prior, dict)
                and prior.get("schema") == 2
                and prior.get("snapshot") == stable
            ):
                if isinstance(prior.get("attempted_repairs"), list):
                    attempted = [
                        repair
                        for repair in prior["attempted_repairs"]
                        if repair in repairs and repair in RECOVERY_KINDS
                    ]
                if isinstance(prior.get("observed_scopes"), list):
                    observed_scopes = [
                        scope for scope in prior["observed_scopes"]
                        if scope in ("project", "user")
                    ]
            scope = snapshot.get("hook_scope")
            if scope in ("project", "user"):
                observed_scopes.append(scope)
            state = {
                "schema": 2,
                "status": "DEGRADED|RECOVERABLE",
                "message": str(message).splitlines()[0].strip(),
                "repairs": repairs,
                "attempted_repairs": sorted(set(attempted)),
                "observed_scopes": sorted(set(observed_scopes)),
                "snapshot": stable,
            }
            _atomic_text(path, json.dumps(state, sort_keys=True) + "\n")
        return True
    except OSError:
        return False


def read_session_failure(cwd, session_id):
    state = read_session_failure_record(cwd, session_id)
    message = state.get("message") if isinstance(state, dict) and state.get("schema") in (1, 2) else ""
    return message if isinstance(message, str) else ""


def session_recovery_status(payload, cwd, hook_scope, expected_event="PreToolUse", host=None):
    """Validate a DEGRADED record against the current trusted hook envelope."""
    ok, detail, snapshot = verified_session_snapshot(payload, cwd, hook_scope, expected_event, host)
    if not ok:
        return False, detail, [], None
    state = read_session_failure_record(cwd, payload.get("session_id"))
    if not isinstance(state, dict) or state.get("schema") != 2 or state.get("status") != "DEGRADED|RECOVERABLE":
        return False, read_session_failure(cwd, payload.get("session_id")) or blocker_instruction("new-task", cwd), [], snapshot
    stable = {
        key: value
        for key, value in snapshot.items()
        if key not in ("hook_definition", "hook_scope", "preconditions")
    }
    repairs = state.get("repairs")
    if state.get("snapshot") != stable:
        return False, blocker_instruction("new-task", cwd), [], snapshot
    if not isinstance(repairs, list) or not repairs or any(repair not in RECOVERY_KINDS for repair in repairs):
        return False, blocker_instruction("new-task", cwd), [], snapshot
    return True, "", list(repairs), snapshot


def consume_session_recovery(cwd, session_id, recovery_kind):
    """Consume one degraded-session recovery kind across hook processes."""
    if not cwd or not session_id or recovery_kind not in RECOVERY_KINDS:
        return False, "recovery identity is invalid"
    try:
        with _session_recovery_lock(cwd, session_id) as path:
            state = read_session_failure_record(cwd, session_id)
            repairs = state.get("repairs") if isinstance(state, dict) else None
            attempted = state.get("attempted_repairs", []) if isinstance(state, dict) else []
            if (
                not isinstance(state, dict)
                or state.get("schema") != 2
                or state.get("status") != "DEGRADED|RECOVERABLE"
                or not isinstance(repairs, list)
                or recovery_kind not in repairs
                or not isinstance(attempted, list)
            ):
                return False, "recoverable session state is unavailable"
            if recovery_kind in attempted:
                return False, "this exact recovery was already attempted"
            state["attempted_repairs"] = sorted(set(attempted + [recovery_kind]))
            _atomic_text(path, json.dumps(state, sort_keys=True) + "\n")
        return True, ""
    except OSError as error:
        return False, "recovery-attempt state write failed: %s" % str(error)[:120]


def session_recovery_scope_observed(cwd, session_id, hook_scope):
    """Return whether a trusted degraded SessionStart ran in this hook scope."""
    if hook_scope not in ("project", "user"):
        return False
    state = read_session_failure_record(cwd, session_id)
    return bool(
        isinstance(state, dict)
        and state.get("schema") == 2
        and state.get("status") == "DEGRADED|RECOVERABLE"
        and isinstance(state.get("observed_scopes"), list)
        and hook_scope in state["observed_scopes"]
    )


def refresh_degraded_session(payload, cwd, hook_scope, host, snapshot):
    """Re-run every precondition and promote a repaired session atomically."""
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        [
            sys.executable,
            os.path.join(HARNESS, "shared", "gates", "precheck.py"),
            "--root",
            cwd,
            "--session-id",
            payload.get("session_id", ""),
            "--session-start",
            "--host",
            host,
            "--operation",
            "bootstrap",
        ],
        capture_output=True,
        text=True,
        timeout=900,
        env=environment,
    )
    output = result.stdout.strip()
    if result.returncode == 0 and output == "session-gate: READY":
        try:
            return authorize_session(cwd, payload.get("session_id", ""), snapshot), ""
        except OSError as error:
            return False, "session authorization cache write failed: %s" % str(error)[:160]
    detail = output or result.stderr.strip() or "session recovery precheck failed without a diagnostic"
    repairs = recovery_kinds_from_precheck(detail)
    if repairs:
        write_session_degraded(cwd, payload.get("session_id", ""), snapshot, detail, repairs)
        commands = [recovery_command(repair, cwd) for repair in repairs]
        commands = [command for command in commands if command]
        return False, "Run only this recovery command: %s" % (
            commands[0] if commands else blocker_instruction("new-task", cwd)
        )
    write_session_failure(cwd, payload.get("session_id", ""), session_precheck_stop_reason(detail, cwd))
    return False, session_precheck_stop_reason(detail, cwd)


def authorize_session(cwd, session_id, snapshot):
    if not session_id or not isinstance(snapshot, dict):
        return False
    path = session_authorization_path(cwd, session_id)
    lock = path + ".lock"
    deadline = time.monotonic() + 30
    os.makedirs(os.path.dirname(lock), exist_ok=True)
    while True:
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(descriptor, ("%d\n" % os.getpid()).encode("ascii"))
            os.close(descriptor)
            break
        except FileExistsError:
            try:
                stale = time.time() - os.path.getmtime(lock) > 5
            except OSError:
                stale = False
            if stale:
                try:
                    os.remove(lock)
                except OSError:
                    pass
                continue
            if time.monotonic() >= deadline:
                raise OSError("session authorization merge lock timed out")
            time.sleep(0.01)
    try:
        record = dict(snapshot)
        record.update({"schema": 3, "status": "READY|HARNESS"})
        prior = read_session_authorization(cwd, session_id)
        if _authorization_record_shape(prior, record):
            old_scope = prior.get("hook_scope")
            old_digest = prior.get("hook_definition")
            new_scope = record.get("hook_scope")
            new_digest = record.get("hook_definition")
            same_identity = all(
                prior.get(key) == record.get(key)
                for key in ("host", "root", "session")
            )
            if not same_identity:
                return False
            if same_identity and (old_scope != new_scope or prior.get("schema") == 4):
                hooks = dict(prior.get("hooks", {})) if prior.get("schema") == 4 else {}
                if prior.get("schema") == 3 and old_scope and old_digest:
                    hooks[old_scope] = old_digest
                hooks[new_scope] = new_digest
                record.pop("hook_scope", None)
                record.pop("hook_definition", None)
                record["hooks"] = hooks
                record["schema"] = 4
        _atomic_text(path, json.dumps(record, sort_keys=True) + "\n")
        try:
            os.remove(session_failure_path(cwd, session_id))
        except OSError:
            pass
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass
    return True


def _authorization_record_shape(record, template):
    """Accept only canonical schema-3/4 authorization records for refresh."""
    if not isinstance(record, dict) or record.get("status") != "READY|HARNESS":
        return False
    if record.get("preconditions") != []:
        return False
    if record.get("schema") == 3:
        return set(record) == set(template)
    if record.get("schema") != 4:
        return False
    expected = (set(template) - {"hook_scope", "hook_definition"}) | {"hooks"}
    hooks = record.get("hooks")
    return bool(
        set(record) == expected
        and isinstance(hooks, dict)
        and hooks
        and set(hooks).issubset({"project", "user"})
        and all(isinstance(value, str) and value for value in hooks.values())
    )


def revoke_session(cwd, session_id):
    if not session_id:
        return True
    ok = True
    for path in (session_authorization_path(cwd, session_id), session_failure_path(cwd, session_id)):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError:
            ok = False
    return ok


def read_session_authorization(cwd, session_id):
    if not session_id:
        return None
    try:
        with open(session_authorization_path(cwd, session_id), encoding="utf-8") as f:
            record = json.load(f)
    except (OSError, ValueError, UnicodeError):
        return None
    return record if isinstance(record, dict) else None


def session_authorization_status(
    payload,
    cwd,
    hook_scope,
    expected_event="PreToolUse",
    host=None,
    required_scopes=None,
):
    """Revalidate stable state and compare it with the SessionStart record."""
    ok, detail, snapshot = verified_session_snapshot(payload, cwd, hook_scope, expected_event, host)
    if not ok:
        return False, detail
    record = read_session_authorization(cwd, payload.get("session_id"))
    expected = dict(snapshot)
    expected.update({"schema": 3, "status": "READY|HARNESS"})
    authorized = record == expected
    if isinstance(record, dict) and record.get("schema") == 4 and record.get("status") == "READY|HARNESS":
        expected_base = {
            key: value
            for key, value in expected.items()
            if key not in ("schema", "hook_scope", "hook_definition")
        }
        authorized = (
            all(record.get(key) == value for key, value in expected_base.items())
            and isinstance(record.get("hooks"), dict)
            and record["hooks"].get(hook_scope) == snapshot.get("hook_definition")
        )
    recorded_scope = record.get("hook_scope") if isinstance(record, dict) else ""
    recorded_hooks = record.get("hooks") if isinstance(record, dict) else None
    scope_was_authorized = (
        recorded_scope == hook_scope
        or (isinstance(recorded_hooks, dict) and hook_scope in recorded_hooks)
    )
    same_identity = bool(
        _authorization_record_shape(record, expected)
        and record.get("status") == "READY|HARNESS"
        and all(record.get(key) == expected.get(key) for key in ("host", "root", "session"))
    )
    if not authorized and same_identity and scope_was_authorized:
        prior_hook = (
            recorded_hooks.get(hook_scope)
            if isinstance(recorded_hooks, dict)
            else record.get("hook_definition")
        )
        hook_changed = prior_hook != snapshot.get("hook_definition")
        try:
            authorize_session(cwd, payload.get("session_id"), snapshot)
        except OSError as error:
            return False, "session authorization refresh failed: %s" % str(error)[:160]
        if hook_changed:
            sys.stderr.write(
                "authorization: NOTED|loaded hook bytes changed; continue this task; "
                "review integration during maintenance\n"
            )
        return session_authorization_status(
            payload,
            cwd,
            hook_scope,
            expected_event,
            host,
            required_scopes,
        )
    if authorized and required_scopes:
        required_scopes = tuple(sorted(set(required_scopes)))
        recorded_hooks = record.get("hooks") if isinstance(record, dict) else None
        recorded_scope = record.get("hook_scope") if isinstance(record, dict) else None
        if isinstance(recorded_hooks, dict):
            recorded_scopes = sorted(
                scope
                for scope in recorded_hooks
                if scope in ("project", "user")
            )
        elif recorded_scope in ("project", "user"):
            recorded_scopes = [recorded_scope]
        else:
            recorded_scopes = []
        for required_scope in required_scopes:
            hook_ok, hook_detail, hook_digest = hook_definition_status(cwd, required_scope, host)
            if not hook_ok:
                return False, hook_detail
            if not isinstance(recorded_hooks, dict) or recorded_hooks.get(required_scope) != hook_digest:
                if recorded_scopes and required_scope not in recorded_scopes:
                    return False, (
                        "Start a new Codex task in %s; SessionStart authorized only the %s integration, "
                        "and the %s integration did not complete."
                        % (project_name(cwd), " and ".join(recorded_scopes), required_scope)
                    )
                if required_scope in recorded_scopes:
                    refreshed = dict(snapshot)
                    refreshed["hook_scope"] = required_scope
                    refreshed["hook_definition"] = hook_digest
                    try:
                        if not authorize_session(cwd, payload.get("session_id"), refreshed):
                            return False, "session authorization identity changed"
                    except OSError as error:
                        return False, "session authorization refresh failed: %s" % str(error)[:160]
                    sys.stderr.write(
                        "authorization: NOTED|loaded hook bytes changed; continue this task; "
                        "review integration during maintenance\n"
                    )
                    record = read_session_authorization(cwd, payload.get("session_id"))
                    recorded_hooks = record.get("hooks") if isinstance(record, dict) else None
                    continue
                return False, (
                    "Start a new Codex task in %s; SessionStart did not create a matching "
                    "authorization record for the %s integration."
                    % (project_name(cwd), required_scope)
                )
    if not authorized:
        stored = read_session_failure(cwd, payload.get("session_id"))
        if stored:
            return False, stored
        recorded_scope = record.get("hook_scope") if isinstance(record, dict) else ""
        recorded_hooks = record.get("hooks") if isinstance(record, dict) else None
        if isinstance(recorded_hooks, dict):
            recorded_scopes = sorted(scope for scope in recorded_hooks if scope in ("project", "user"))
        elif recorded_scope in ("project", "user"):
            recorded_scopes = [recorded_scope]
        else:
            recorded_scopes = []
        if recorded_scopes and hook_scope not in recorded_scopes:
            return False, (
                "Start a new Codex task in %s; SessionStart authorized only the %s integration, "
                "and the %s integration did not complete."
                % (project_name(cwd), " and ".join(recorded_scopes), hook_scope)
            )
        return False, (
            "Start a new Codex task in %s; SessionStart did not create a matching "
            "authorization record for the %s integration."
            % (project_name(cwd), hook_scope or "required")
        )
    return True, ""


def session_authorized(cwd, session_id):
    """Read a current documented-contract authorization record."""
    record = read_session_authorization(cwd, session_id)
    return bool(
        isinstance(record, dict)
        and record.get("schema") in (3, 4)
        and record.get("root") == _session_key(os.path.realpath(cwd))
        and record.get("session") == _session_key(session_id)
        and record.get("host") in ("codex", "claude")
        and record.get("status") == "READY|HARNESS"
    )


def elide(path, root):
    return houseout.elide(path, root)


def emit_json(obj):
    sys.stdout.write(json.dumps(obj))


def _atomic_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".%d.tmp" % os.getpid()
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _agent_component(value):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(value)) or "unknown"


def agent_mailbox_dir(cwd, session_id):
    return os.path.join(cwd, "gates", ".agents", _agent_component(session_id))


def _agent_mailbox_turn_id(cwd, session_id):
    turn = read_turn_record(cwd, session_id)
    return turn.get("turn_id", "") if isinstance(turn, dict) else ""


def _agent_mailbox_record_valid(entry, cwd, session_id, turn_id, now):
    if not isinstance(entry, dict) or entry.get("schema") != 1:
        return False
    created_at = entry.get("created_at")
    expires_at = entry.get("expires_at")
    return bool(
        isinstance(turn_id, str)
        and turn_id
        and entry.get("cwd") == os.path.realpath(cwd)
        and entry.get("session_id") == str(session_id)
        and entry.get("turn_id") == turn_id
        and isinstance(entry.get("agent_id"), str)
        and entry.get("agent_id")
        and isinstance(created_at, (int, float))
        and isinstance(expires_at, (int, float))
        and float(created_at) <= now < float(expires_at)
        and float(expires_at) <= float(created_at) + AGENT_MAILBOX_TTL + 1
    )


def agent_mailbox_entries(cwd, session_id, now=None):
    """Return only live mailboxes bound to this session's current turn."""
    directory = agent_mailbox_dir(cwd, session_id)
    now = time.time() if now is None else float(now)
    turn_id = _agent_mailbox_turn_id(cwd, session_id)
    entries = []
    try:
        names = os.listdir(directory)
    except OSError:
        return entries
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(directory, name), encoding="utf-8") as f:
                entry = json.load(f)
            if _agent_mailbox_record_valid(entry, cwd, session_id, turn_id, now):
                entries.append(entry)
            else:
                os.remove(os.path.join(directory, name))
        except (OSError, ValueError):
            continue
    return entries


def clear_session_agent_mailboxes(cwd, session_id):
    """Retire every prior-turn mailbox for this session."""
    directory = agent_mailbox_dir(cwd, session_id)
    try:
        names = os.listdir(directory)
    except OSError:
        return
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            os.remove(os.path.join(directory, name))
        except OSError:
            pass
    try:
        os.rmdir(directory)
    except OSError:
        pass


def agent_mailbox_type(cwd, session_id, agent_id):
    """Return the trusted role recorded for one spawned agent."""
    if not session_id or not agent_id:
        return ""
    for entry in agent_mailbox_entries(cwd, session_id):
        if (
            entry.get("cwd") == os.path.realpath(cwd)
            and entry.get("session_id") == str(session_id)
            and entry.get("agent_id") == str(agent_id)
        ):
            role = entry.get("agent_type")
            return role if isinstance(role, str) else ""
    return ""


def effective_agent_type(payload, cwd):
    """Resolve Codex's transient default role from the session mailbox."""
    reported = payload.get("agent_type") or payload.get("agent_name") or ""
    if reported not in ("", "default"):
        return reported
    recorded = agent_mailbox_type(cwd, payload.get("session_id"), payload.get("agent_id"))
    return recorded or reported


def agent_mailbox_write(cwd, session_id, agent_id, now=None, **changes):
    """Create or update one bounded mailbox without extending its lifetime."""
    now = time.time() if now is None else float(now)
    turn_id = _agent_mailbox_turn_id(cwd, session_id)
    if not turn_id:
        return {}
    directory = agent_mailbox_dir(cwd, session_id)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, _agent_component(agent_id) + ".json")
    entry = {}
    try:
        with open(path, encoding="utf-8") as f:
            entry = json.load(f)
    except (OSError, ValueError):
        pass
    if not _agent_mailbox_record_valid(entry, cwd, session_id, turn_id, now):
        entry = {
            "created_at": now,
            "expires_at": now + AGENT_MAILBOX_TTL,
        }
    entry.update(changes)
    entry.update(
        {
            "schema": 1,
            "cwd": os.path.realpath(cwd),
            "session_id": str(session_id),
            "turn_id": turn_id,
            "agent_id": str(agent_id),
        }
    )
    _atomic_text(path, json.dumps(entry, sort_keys=True) + "\n")
    return entry


def agent_mailbox_delete(cwd, session_id, agent_id):
    path = os.path.join(agent_mailbox_dir(cwd, session_id), _agent_component(agent_id) + ".json")
    try:
        os.remove(path)
    except OSError:
        return
    try:
        os.rmdir(os.path.dirname(path))
    except OSError:
        pass


def _review_key(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:20]


def turn_record_path(cwd, session_id):
    return os.path.join(cwd, "gates", ".turn-s%s" % _review_key(session_id))


def veto_path(cwd, session_id):
    return os.path.join(cwd, "gates", ".veto-s%s" % _review_key(session_id))


def mutation_check_path(cwd, session_id):
    return os.path.join(cwd, "gates", ".mutation-s%s" % _review_key(session_id))


def untracked_baseline_path(cwd, session_id):
    return os.path.join(cwd, "gates", ".untracked-s%s" % _review_key(session_id))


def studio_requirement_path(cwd, session_id):
    return os.path.join(cwd, "gates", ".studio-required-s%s" % _review_key(session_id))


def stop_cache_path(cwd, session_id):
    return os.path.join(cwd, "gates", ".stop-cache-s%s.json" % _review_key(session_id))


def stop_cache_key(cwd, session_id):
    turn = read_turn_record(cwd, session_id)
    target, _ = review_target(cwd, turn)
    if not turn or not target:
        return ""
    receipt_state = [
        (receipt.get("target_digest"), receipt.get("verdict"), receipt.get("completed_at"))
        for _, receipt in valid_review_receipts(cwd, session_id)
    ]
    inputs = [
        os.path.join(HARNESS, "shared", "gates", name)
        for name in ("done_gate.py", "finalize.py", "write_gate.py", "record_check.py")
    ]
    inputs += [
        os.path.join(TOOLS, "deny_scan", "deny_table.luau"),
        os.path.join(TOOLS, "style_assess", "fix_pass.luau"),
        os.path.join(TOOLS, "replication_audit", "replication_audit.py"),
    ]
    checker_inputs = []
    for path in inputs:
        try:
            stat = os.stat(path)
            checker_inputs.append((path, stat.st_size, stat.st_mtime_ns))
        except OSError:
            checker_inputs.append((path, "missing"))
    try:
        changed_paths = changed_paths_since_turn(cwd, turn)
    except OSError:
        return ""
    settled_tree = []
    for relative in changed_paths:
        path = os.path.join(cwd, relative)
        digest = hashlib.sha256()
        try:
            stat = os.lstat(path)
            digest.update(("%o\0" % stat.st_mode).encode("ascii"))
            if os.path.islink(path):
                digest.update(os.readlink(path).encode("utf-8", "surrogateescape"))
            else:
                with open(path, "rb") as handle:
                    for chunk in iter(lambda: handle.read(65536), b""):
                        digest.update(chunk)
            settled_tree.append((relative, digest.hexdigest()))
        except OSError:
            settled_tree.append((relative, "deleted"))
    payload = {
        "authorization": read_session_authorization(cwd, session_id),
        "checkers": checker_inputs,
        "receipts": receipt_state,
        "settled_tree": settled_tree,
        "studio": studio_required(cwd, session_id),
        "target": target,
        "turn": turn.get("turn_id"),
    }
    return _json_digest(payload)


def workspace_digest(cwd):
    """Hash the settled Git worktree without charging lifecycle state.

    HEAD represents unchanged tracked bytes.  The binary diff represents all
    staged and unstaged tracked changes, and untracked file bytes are included
    explicitly.  This keeps a pre-final receipt cheap to verify while making
    every post-validation workspace change invalidate it.
    """
    root = os.path.realpath(cwd)
    digest = hashlib.sha256()
    digest.update(b"workspace-v1\0")
    digest.update(root.encode("utf-8", "surrogateescape") + b"\0")
    try:
        head = subprocess.run(
            ["git", "-C", root, "rev-parse", "HEAD"],
            capture_output=True,
            timeout=30,
            env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"),
        )
        tracked = subprocess.run(
            ["git", "-C", root, "diff", "--binary", "--no-ext-diff", "HEAD", "--"],
            capture_output=True,
            timeout=60,
            env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"),
        )
        untracked = subprocess.run(
            ["git", "-C", root, "ls-files", "--others", "--exclude-standard", "-z"],
            capture_output=True,
            timeout=30,
            env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"),
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if any(result.returncode != 0 for result in (head, tracked, untracked)):
        return ""
    def as_bytes(value):
        return value if isinstance(value, bytes) else str(value or "").encode("utf-8", "surrogateescape")

    digest.update(as_bytes(head.stdout).strip() + b"\0")
    digest.update(as_bytes(tracked.stdout) + b"\0")
    for raw in sorted(path for path in as_bytes(untracked.stdout).split(b"\0") if path):
        relative = raw.decode("utf-8", "surrogateescape")
        if relative == "gates" or relative.startswith("gates/"):
            continue
        digest.update(raw + b"\0")
        path = os.path.join(root, relative)
        try:
            stat = os.lstat(path)
            digest.update(("%o\0" % stat.st_mode).encode("ascii"))
            if os.path.islink(path):
                digest.update(os.readlink(path).encode("utf-8", "surrogateescape"))
            elif os.path.isfile(path):
                with open(path, "rb") as handle:
                    for chunk in iter(lambda: handle.read(65536), b""):
                        digest.update(chunk)
            else:
                digest.update(b"non-file")
        except OSError:
            digest.update(b"missing")
        digest.update(b"\0")
    return digest.hexdigest()


def stop_cache_hit(cwd, session_id, key):
    if not key:
        return False
    try:
        with open(stop_cache_path(cwd, session_id), encoding="utf-8") as handle:
            record = json.load(handle)
    except (OSError, ValueError, UnicodeError):
        return False
    return bool(isinstance(record, dict) and record.get("schema") == 1 and record.get("key") == key)


def write_stop_cache(cwd, session_id, key):
    if not key:
        return False
    _atomic_text(
        stop_cache_path(cwd, session_id),
        json.dumps({"schema": 1, "key": key, "completed_at": time.time()}, sort_keys=True) + "\n",
    )
    return True


def clear_stop_cache(cwd, session_id):
    try:
        os.remove(stop_cache_path(cwd, session_id))
    except OSError:
        pass


def mark_studio_required(cwd, session_id):
    if not session_id:
        return False
    _atomic_text(studio_requirement_path(cwd, session_id), "v1\n")
    return True


def studio_required(cwd, session_id):
    try:
        with open(studio_requirement_path(cwd, session_id), encoding="utf-8") as handle:
            return handle.read().strip() == "v1"
    except OSError:
        return False


def current_untracked_paths(cwd):
    """Return untracked paths without changing the index or worktree."""
    result = subprocess.run(
        ["git", "-C", cwd, "ls-files", "--others", "--exclude-standard", "-z"],
        capture_output=True,
        env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"),
    )
    if result.returncode != 0:
        raise OSError((result.stderr or b"untracked-file query failed").decode("utf-8", "replace")[:160])
    return sorted(
        raw.decode("utf-8", "surrogateescape")
        for raw in result.stdout.split(b"\0")
        if raw and not raw.decode("utf-8", "surrogateescape").startswith("gates/.")
    )


def current_untracked_luau(cwd):
    return [path for path in current_untracked_paths(cwd) if path.endswith((".lua", ".luau"))]


def _untracked_source_digest(cwd, relative):
    """Hash one untracked source entry without following a project symlink."""
    path = os.path.join(cwd, relative)
    stat = os.lstat(path)
    digest = hashlib.sha256()
    if os.path.islink(path):
        digest.update(b"link\0")
        digest.update(os.readlink(path).encode("utf-8", "surrogateescape"))
    elif os.path.isfile(path):
        digest.update(b"file\0")
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
    else:
        digest.update(b"other\0")
        digest.update(("%o" % stat.st_mode).encode("ascii"))
    return digest.hexdigest()


def write_untracked_baseline(cwd, session_id):
    if not session_id:
        raise OSError("session identity is absent")
    paths = current_untracked_paths(cwd)
    source_hashes = {
        path: _untracked_source_digest(cwd, path)
        for path in paths
        if path.endswith((".lua", ".luau"))
    }
    _atomic_text(
        untracked_baseline_path(cwd, session_id),
        json.dumps(
            {"schema": 2, "paths": paths, "source_hashes": source_hashes},
            sort_keys=True,
        )
        + "\n",
    )
    return paths


def changed_paths_since_turn(cwd, turn):
    """Return tracked and new-untracked paths changed after the turn stamp."""
    if not turn or turn.get("head") == "no-head":
        return []
    head = turn.get("head", "")
    result = subprocess.run(
        ["git", "-C", cwd, "diff", "--name-only", "-z", head, "--"],
        capture_output=True,
        env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"),
    )
    if result.returncode != 0:
        raise OSError((result.stderr or b"turn diff failed").decode("utf-8", "replace")[:160])
    tracked = {
        raw.decode("utf-8", "surrogateescape")
        for raw in result.stdout.split(b"\0")
        if raw
    }
    current = set(current_untracked_paths(cwd))
    baseline_record = read_untracked_baseline_record(cwd, turn.get("session_id", ""))
    baseline = set(baseline_record["paths"])
    changed_untracked_sources = set()
    for path, baseline_digest in baseline_record["source_hashes"].items():
        if path not in current:
            changed_untracked_sources.add(path)
            continue
        try:
            current_digest = _untracked_source_digest(cwd, path)
        except OSError:
            changed_untracked_sources.add(path)
            continue
        if current_digest != baseline_digest:
            changed_untracked_sources.add(path)
    return sorted(tracked | (current - baseline) | changed_untracked_sources)


def read_untracked_baseline_record(cwd, session_id):
    try:
        with open(untracked_baseline_path(cwd, session_id), encoding="utf-8") as handle:
            record = json.load(handle)
    except (OSError, ValueError, UnicodeError):
        return {"paths": [], "source_hashes": {}}
    if not isinstance(record, dict) or record.get("schema") not in (1, 2):
        return {"paths": [], "source_hashes": {}}
    paths = record.get("paths")
    paths = sorted(path for path in paths if isinstance(path, str)) if isinstance(paths, list) else []
    raw_hashes = record.get("source_hashes") if record.get("schema") == 2 else {}
    source_hashes = {
        path: digest
        for path, digest in raw_hashes.items()
        if isinstance(path, str)
        and path in paths
        and path.endswith((".lua", ".luau"))
        and isinstance(digest, str)
        and re.fullmatch(r"[0-9a-f]{64}", digest)
    } if isinstance(raw_hashes, dict) else {}
    return {"paths": paths, "source_hashes": source_hashes}


def read_untracked_baseline(cwd, session_id):
    return read_untracked_baseline_record(cwd, session_id)["paths"]


def clear_mutation_check(cwd, session_id):
    try:
        os.remove(mutation_check_path(cwd, session_id))
    except OSError:
        pass


def mutation_check_current(cwd, session_id, turn):
    if not turn:
        return False
    try:
        with open(mutation_check_path(cwd, session_id), encoding="utf-8") as handle:
            record = json.load(handle)
    except (OSError, ValueError, UnicodeError):
        return False
    identity = mutation_identity(cwd)
    return (
        isinstance(record, dict)
        and record.get("schema") == 2
        and record.get("turn_id") == turn.get("turn_id")
        and identity is not None
        and record.get("head") == identity["head"]
        and record.get("branch") == identity["branch"]
    )


def write_mutation_check(cwd, session_id, turn):
    if not turn or not turn.get("turn_id"):
        return False
    identity = mutation_identity(cwd)
    if identity is None:
        return False
    record = {
        "schema": 2,
        "turn_id": turn["turn_id"],
        "head": identity["head"],
        "branch": identity["branch"],
    }
    _atomic_text(mutation_check_path(cwd, session_id), json.dumps(record, sort_keys=True) + "\n")
    return True


def mutation_identity(cwd):
    """Return the local Git identity bound by the once-per-turn mutation check."""
    rc, head, _ = git(cwd, "rev-parse", "--verify", "HEAD^{commit}")
    if rc != 0 or not re.fullmatch(r"[0-9a-fA-F]{40,64}", head):
        return None
    rc, branch, _ = git(cwd, "symbolic-ref", "--quiet", "--short", "HEAD")
    if rc != 0 or not branch:
        return None
    return {"head": head, "branch": branch}


def read_turn_record(cwd, session_id):
    if not session_id:
        return None
    try:
        with open(turn_record_path(cwd, session_id), encoding="utf-8") as f:
            parts = f.read().strip().split("|")
    except OSError:
        return None
    if len(parts) != 4 or parts[0] != "v1" or not parts[1]:
        return None
    if parts[2] != "no-head" and not re.match(r"^[0-9a-fA-F]{40,64}$", parts[2]):
        return None
    try:
        started_at = float(parts[3])
    except ValueError:
        return None
    return {
        "turn_id": parts[1],
        "head": parts[2],
        "started_at": started_at,
        "session_id": session_id,
    }


def write_turn_record(cwd, session_id, turn_id, head, started_at=None):
    if not session_id:
        return None
    token = _agent_component(turn_id)
    started_at = time.time() if started_at is None else float(started_at)
    path = turn_record_path(cwd, session_id)
    _atomic_text(path, "v1|%s|%s|%.6f\n" % (token, head, started_at))
    return read_turn_record(cwd, session_id)


def _isolated_worktree_tree(cwd, head):
    """Snapshot tracked worktree bytes through a disposable Git index.

    ``git stash create`` refuses an otherwise valid intent-to-add entry.  A
    HEAD-to-worktree binary patch applied to an isolated index produces the
    same tracked tree without changing the caller's index, worktree, or refs.
    """
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    diff = subprocess.run(
        [
            "git",
            "-C",
            cwd,
            "diff",
            "--binary",
            "--full-index",
            "--no-ext-diff",
            "--no-textconv",
            head,
            "--",
        ],
        capture_output=True,
        env=environment,
    )
    if diff.returncode != 0:
        detail = (diff.stderr or diff.stdout or b"tracked worktree diff failed").decode("utf-8", "replace")
        raise OSError(detail.strip())
    descriptor, index_path = tempfile.mkstemp(prefix="harness-turn-index-")
    os.close(descriptor)
    try:
        os.remove(index_path)
        isolated = dict(environment, GIT_INDEX_FILE=os.path.abspath(index_path))
        read_tree = subprocess.run(
            ["git", "-C", cwd, "read-tree", head],
            capture_output=True,
            env=isolated,
        )
        if read_tree.returncode != 0:
            detail = (read_tree.stderr or read_tree.stdout or b"isolated index initialization failed").decode(
                "utf-8", "replace"
            )
            raise OSError(detail.strip())
        if diff.stdout:
            applied = subprocess.run(
                ["git", "-C", cwd, "apply", "--cached", "--binary", "--whitespace=nowarn", "-"],
                input=diff.stdout,
                capture_output=True,
                env=isolated,
            )
            if applied.returncode != 0:
                detail = (applied.stderr or applied.stdout or b"isolated worktree patch failed").decode(
                    "utf-8", "replace"
                )
                raise OSError(detail.strip())
        written = subprocess.run(
            ["git", "-C", cwd, "write-tree"],
            capture_output=True,
            env=isolated,
        )
        tree = written.stdout.decode("ascii", "replace").strip()
        if written.returncode != 0 or not re.fullmatch(r"[0-9a-fA-F]{40,64}", tree):
            detail = (written.stderr or written.stdout or b"isolated worktree tree failed").decode(
                "utf-8", "replace"
            )
            raise OSError(detail.strip())
        return tree
    finally:
        for path in (index_path, index_path + ".lock"):
            try:
                os.remove(path)
            except OSError:
                pass


def current_turn_baseline(cwd):
    """Create a non-checkout-changing snapshot of the tracked working tree."""
    rc, head, detail = git(cwd, "rev-parse", "HEAD")
    if rc != 0 or not head.strip():
        raise OSError((detail or "Git HEAD is unavailable").strip())
    result = subprocess.run(
        ["git", "-C", cwd, "stash", "create", "done-gate turn baseline"],
        capture_output=True,
        text=True,
        env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"),
    )
    if result.returncode != 0:
        primary = (result.stderr or result.stdout or "tracked worktree snapshot failed").strip()
        try:
            return _isolated_worktree_tree(cwd, head.strip())
        except OSError as error:
            raise OSError("%s; isolated fallback failed: %s" % (primary, str(error)[:240]))
    return result.stdout.strip() or head.strip()


def ensure_turn_record(cwd, session_id, turn_id=None):
    turn = read_turn_record(cwd, session_id)
    expected_turn = _agent_component(turn_id) if turn_id else ""
    if turn and (not expected_turn or turn.get("turn_id") == expected_turn):
        return turn
    if not session_id:
        raise OSError("session identity is absent")
    turn = write_turn_record(
        cwd,
        session_id,
        turn_id or str(time.time_ns()),
        current_turn_baseline(cwd),
    )
    if not turn:
        raise OSError("turn baseline could not be recorded")
    return turn


def review_receipt_path(cwd, session_id, turn_id, agent_id):
    name = ".review-s%s-t%s-a%s" % (
        _review_key(session_id),
        _review_key(turn_id),
        _review_key(agent_id),
    )
    return os.path.join(cwd, "gates", name)


def review_candidate_path(cwd, session_id, turn_id, agent_id):
    name = ".review-candidate-s%s-t%s-a%s" % (
        _review_key(session_id),
        _review_key(turn_id),
        _review_key(agent_id),
    )
    return os.path.join(cwd, "gates", name)


def read_review_receipt(path):
    try:
        with open(path, encoding="utf-8") as f:
            parts = f.read().strip().split("|")
    except OSError:
        return None
    if len(parts) != 6 or parts[0] != "v1" or parts[1] not in ("pending", "done"):
        return None
    if not re.match(r"^[0-9a-f]{64}$", parts[2]):
        return None
    verdicts = ("CLEAN", "NOTED", "BLOCKED")
    if (parts[1] == "pending" and parts[3] != "void") or (parts[1] == "done" and parts[3] not in verdicts):
        return None
    try:
        completed_at = float(parts[4])
        expires_at = float(parts[5])
    except ValueError:
        return None
    if expires_at <= completed_at:
        return None
    return {
        "state": parts[1],
        "target_digest": parts[2],
        "verdict": parts[3],
        "completed_at": completed_at,
        "expires_at": expires_at,
    }


def _review_receipt_write(path, state, digest, verdict, completed_at, expires_at):
    _atomic_text(
        path,
        "v1|%s|%s|%s|%.6f|%.6f\n" % (state, digest, verdict, completed_at, expires_at),
    )


def cleanup_review_receipts(cwd, now=None):
    """Remove expired or malformed flat receipts. A malformed file can never
    become a project-global precondition."""
    now = time.time() if now is None else float(now)
    gates_dir = os.path.join(cwd, "gates")
    try:
        names = os.listdir(gates_dir)
    except OSError:
        return
    for name in names:
        if not name.startswith((".review-s", ".review-candidate-s")):
            continue
        path = os.path.join(gates_dir, name)
        receipt = read_review_receipt(path)
        if receipt is not None and receipt["expires_at"] > now:
            continue
        try:
            os.remove(path)
        except OSError:
            pass


def clear_session_review_receipts(cwd, session_id):
    session_key = _review_key(session_id)
    prefixes = (".review-s%s-" % session_key, ".review-candidate-s%s-" % session_key)
    gates_dir = os.path.join(cwd, "gates")
    try:
        names = os.listdir(gates_dir)
    except OSError:
        return
    for name in names:
        if name.startswith(prefixes):
            try:
                os.remove(os.path.join(gates_dir, name))
            except OSError:
                pass


def clear_session_type_records(cwd, session_id):
    session_key = _review_key(session_id)
    gates_dir = os.path.join(cwd, "gates")
    try:
        names = os.listdir(gates_dir)
    except OSError:
        return
    for name in names:
        if name.startswith((".type-lookup-s%s-" % session_key, ".type-write-s%s-" % session_key)):
            try:
                os.remove(os.path.join(gates_dir, name))
            except OSError:
                pass


def current_type_records(cwd, session_id, tool):
    return read_tool_records(cwd, tool, session_id)


def type_context_valid(cwd, session_id, definition, member=None, tools=("type-lookup", "type-write")):
    wanted_definition = definition.get("fingerprint") if isinstance(definition, dict) else None
    wanted_member = definition.get("members", {}).get(member) if member and isinstance(definition, dict) else None
    if member and wanted_member is None:
        return False
    for tool in tools:
        for record in current_type_records(cwd, session_id, tool):
            for item in record.get("definitions", []):
                if item.get("qualified") != definition.get("qualified") or item.get("definition") != wanted_definition:
                    continue
                if member is None or item.get("members", {}).get(member) == hashlib.sha256(wanted_member.encode("utf-8")).hexdigest():
                    return True
    return False


def review_target_details(cwd, turn):
    """Hash the settled Lua/Luau state and return its affected consumers.

    UserPromptSubmit snapshots the tracked working tree, including changes
    that predate the turn.  The hash includes that baseline, changed paths,
    file modes, and current worktree bytes.  It therefore covers committed,
    staged, unstaged, renamed, and deleted tracked Luau changes made after the
    prompt without charging the turn for pre-existing dirty files.
    """
    if not turn or turn.get("head") == "no-head":
        return None, [], None
    head = turn.get("head", "")
    rc, _, _ = git(cwd, "cat-file", "-e", head)
    if rc != 0:
        return None, [], None
    try:
        paths = {
            path for path in changed_paths_since_turn(cwd, turn)
            if path.endswith((".lua", ".luau"))
        }
    except OSError:
        return None, [], None
    paths = sorted(paths)
    try:
        from type_lookup.type_lookup import affected as affected_consumers

        affected = sorted(set(affected_consumers(cwd, head, paths)) | set(paths))
    except Exception:
        return None, [], None
    digest = hashlib.sha256()
    digest.update(b"review-target-v1\0")
    digest.update(str(turn.get("turn_id", "")).encode("utf-8") + b"\0")
    digest.update(head.encode("ascii") + b"\0")
    for rel in paths:
        digest.update(rel.encode("utf-8", "surrogateescape") + b"\0")
        path = os.path.join(cwd, rel)
        try:
            stat = os.lstat(path)
            digest.update(("%o" % stat.st_mode).encode("ascii") + b"\0")
            if os.path.islink(path):
                digest.update(b"link\0" + os.readlink(path).encode("utf-8", "surrogateescape"))
            else:
                with open(path, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        digest.update(chunk)
        except OSError:
            digest.update(b"deleted")
        digest.update(b"\0")
    digest.update(b"affected\0")
    for rel in affected:
        digest.update(rel.encode("utf-8", "surrogateescape") + b"\0")
        path = os.path.join(cwd, rel)
        try:
            with open(path, "rb") as handle:
                for chunk in iter(lambda: handle.read(65536), b""):
                    digest.update(chunk)
        except OSError:
            digest.update(b"deleted")
        digest.update(b"\0")
    return digest.hexdigest(), paths, affected


def review_target(cwd, turn):
    digest, paths, _ = review_target_details(cwd, turn)
    return digest, paths


def start_review_receipt(cwd, session_id, agent_id, now=None, expected_digest=None):
    turn = read_turn_record(cwd, session_id)
    digest, _ = review_target(cwd, turn)
    if (
        not turn
        or not digest
        or not agent_id
        or (expected_digest is not None and digest != expected_digest)
    ):
        return None
    now = time.time() if now is None else float(now)
    path = review_receipt_path(cwd, session_id, turn["turn_id"], agent_id)
    _review_receipt_write(path, "pending", digest, "void", now, now + REVIEW_TTL)
    return path


def start_review_candidate(cwd, session_id, agent_id, now=None):
    """Capture a default-profile agent's immutable target without reserving
    the single reviewer slot until SubagentStop identifies its final role."""
    turn = read_turn_record(cwd, session_id)
    digest, _ = review_target(cwd, turn)
    if not turn or not digest or not agent_id:
        return None
    now = time.time() if now is None else float(now)
    path = review_candidate_path(cwd, session_id, turn["turn_id"], agent_id)
    _review_receipt_write(path, "pending", digest, "void", now, now + REVIEW_TTL)
    return path


def fail_review_receipt(cwd, session_id, agent_id):
    if not session_id or not agent_id:
        return
    session_key = _review_key(session_id)
    prefixes = (".review-s%s-" % session_key, ".review-candidate-s%s-" % session_key)
    suffix = "-a%s" % _review_key(agent_id)
    gates_dir = os.path.join(cwd, "gates")
    try:
        names = os.listdir(gates_dir)
    except OSError:
        return
    for name in names:
        if name.startswith(prefixes) and name.endswith(suffix):
            try:
                os.remove(os.path.join(gates_dir, name))
            except OSError:
                pass


def pending_review_receipts(cwd, session_id, now=None):
    """Return unexpired pending receipts for the current immutable target."""
    now = time.time() if now is None else float(now)
    cleanup_review_receipts(cwd, now)
    turn = read_turn_record(cwd, session_id)
    digest, _ = review_target(cwd, turn)
    if not turn or not digest:
        return []
    prefix = ".review-s%s-t%s-" % (_review_key(session_id), _review_key(turn["turn_id"]))
    gates_dir = os.path.join(cwd, "gates")
    try:
        names = os.listdir(gates_dir)
    except OSError:
        return []
    pending = []
    for name in names:
        if not name.startswith(prefix):
            continue
        path = os.path.join(gates_dir, name)
        receipt = read_review_receipt(path)
        if (
            receipt is not None
            and receipt["state"] == "pending"
            and receipt["target_digest"] == digest
            and receipt["expires_at"] > now
            and receipt["completed_at"] >= turn["started_at"]
        ):
            pending.append((path, receipt))
    return pending


def finish_review_receipt(cwd, session_id, agent_id, verdict, now=None):
    turn = read_turn_record(cwd, session_id)
    if not turn or verdict not in ("CLEAN", "NOTED", "BLOCKED"):
        fail_review_receipt(cwd, session_id, agent_id)
        return None
    path = review_receipt_path(cwd, session_id, turn["turn_id"], agent_id)
    receipt = read_review_receipt(path)
    now = time.time() if now is None else float(now)
    digest, _ = review_target(cwd, turn)
    if (
        receipt is None
        or receipt["state"] != "pending"
        or receipt["expires_at"] <= now
        or receipt["target_digest"] != digest
    ):
        fail_review_receipt(cwd, session_id, agent_id)
        return None
    _review_receipt_write(path, "done", digest, verdict, now, receipt["expires_at"])
    return path


def finish_review_candidate(cwd, session_id, agent_id, verdict, now=None):
    """Promote a default-profile candidate only when its dispatch target is
    still current and its SubagentStop verdict identifies a reviewer."""
    turn = read_turn_record(cwd, session_id)
    if not turn or verdict not in ("CLEAN", "NOTED", "BLOCKED"):
        fail_review_receipt(cwd, session_id, agent_id)
        return None
    candidate = review_candidate_path(cwd, session_id, turn["turn_id"], agent_id)
    receipt = read_review_receipt(candidate)
    now = time.time() if now is None else float(now)
    digest, _ = review_target(cwd, turn)
    if (
        receipt is None
        or receipt["state"] != "pending"
        or receipt["expires_at"] <= now
        or receipt["target_digest"] != digest
    ):
        fail_review_receipt(cwd, session_id, agent_id)
        return None
    path = review_receipt_path(cwd, session_id, turn["turn_id"], agent_id)
    _review_receipt_write(path, "done", digest, verdict, now, receipt["expires_at"])
    try:
        os.remove(candidate)
    except OSError:
        pass
    return path


def valid_review_receipts(cwd, session_id, now=None):
    now = time.time() if now is None else float(now)
    cleanup_review_receipts(cwd, now)
    turn = read_turn_record(cwd, session_id)
    digest, _ = review_target(cwd, turn)
    if not turn or not digest:
        return []
    prefix = ".review-s%s-t%s-" % (_review_key(session_id), _review_key(turn["turn_id"]))
    gates_dir = os.path.join(cwd, "gates")
    try:
        names = os.listdir(gates_dir)
    except OSError:
        return []
    valid = []
    for name in names:
        if not name.startswith(prefix):
            continue
        path = os.path.join(gates_dir, name)
        receipt = read_review_receipt(path)
        if (
            receipt is not None
            and receipt["state"] == "done"
            and receipt["verdict"] in ("CLEAN", "NOTED")
            and receipt["target_digest"] == digest
            and receipt["expires_at"] > now
            and receipt["completed_at"] >= turn["started_at"]
        ):
            valid.append((path, receipt))
    return valid


def git(cwd, *args):
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, env=environment)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def git_mutate(cwd, *args, timeout=90):
    """Run the small set of Git mutations owned by GATE6.

    Read helpers disable optional locks; fetch, rebase, and stash must retain
    normal Git locking so two processes cannot update one clone concurrently.
    """
    try:
        r = subprocess.run(
            ["git", "-C", cwd] + list(args),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return 1, "", str(error)[:240]
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def is_harness(cwd):
    """Return whether cwd is the checkout that supplied the running gates."""
    return os.path.realpath(cwd) == os.path.realpath(HARNESS)


def project_harness_root(cwd):
    """Return a managed project's local harness checkout, if it is complete."""
    if not isinstance(cwd, str) or not cwd:
        return ""
    candidate = os.path.join(os.path.realpath(cwd), PROJECT_HARNESS_DIR)
    required = (
        os.path.join(candidate, "shared", "CORE.md"),
        os.path.join(candidate, "shared", "gates", "gatelib.py"),
        os.path.join(candidate, "openai", "hooks", "adapter.py"),
    )
    if not all(os.path.isfile(path) for path in required) or not os.path.exists(os.path.join(candidate, ".git")):
        return ""
    repository_rc, _, _ = git(candidate, "rev-parse", "--show-toplevel")
    remote_rc, _, _ = git(candidate, "remote", "get-url", "origin")
    return candidate if repository_rc == 0 and remote_rc == 0 else ""


def project_uses_harness(cwd, harness=HARNESS):
    """Return whether cwd is bound to the checkout supplying these gates."""
    candidate = project_harness_root(cwd)
    return bool(candidate) and os.path.realpath(candidate) == os.path.realpath(harness)


def is_roblox_project(cwd):
    """The root-level .roblox file is the only managed-project signal."""
    if not isinstance(cwd, str) or not cwd:
        return False
    return os.path.isfile(os.path.join(os.path.realpath(cwd), ".roblox"))


def canonical_remote_branch(cwd):
    """Return origin's live default branch, which is the shared branch policy."""
    rc, output, error = git_mutate(cwd, "ls-remote", "--symref", "origin", "HEAD", timeout=60)
    if rc != 0:
        return None, (error or output or "origin HEAD could not be read")[:200]
    match = re.search(r"^ref:\s+refs/heads/([^\s]+)\s+HEAD$", output, re.MULTILINE)
    if not match:
        return None, "origin HEAD does not name a branch"
    branch = match.group(1)
    rc, _, error = git(cwd, "check-ref-format", "--branch", branch)
    if rc != 0:
        return None, (error or "origin HEAD names an invalid branch")[:200]
    return branch, ""


def gate6_disposition(state):
    """Return the operation policy for one GATE6 state."""
    if state == "ok":
        return "ok"
    if state in ("behind", "diverged"):
        return "repair"
    if state == "fetch-failed":
        return "advisory"
    return "hard"


def gate6_state(cwd, fetch=True):
    """Fetch and compare HEAD with the live canonical origin branch.

    ``ok`` includes equality and local-ahead history. A pushed remote commit
    makes another clone ``behind`` or ``diverged`` on its next check.
    """
    rc, _, _ = git(cwd, "rev-parse", "--git-dir")
    if rc != 0:
        return "not-repo", "working directory is not a git repository"
    rc, head, error = git(cwd, "rev-parse", "--verify", "HEAD^{commit}")
    if rc != 0 or not re.fullmatch(r"[0-9a-fA-F]{40,64}", head):
        return "head-read-failed", (error.strip()[:160] or "HEAD could not be read")
    rc, branch, error = git(cwd, "symbolic-ref", "--quiet", "--short", "HEAD")
    if rc != 0 or not branch:
        if error:
            return "ref-read-failed", error.strip()[:160]
        return "no-upstream", "detached HEAD has no branch to pull"
    rc, remote_url, error = git(cwd, "remote", "get-url", "origin")
    if rc != 0 or not remote_url:
        if error and "No such remote" not in error:
            return "ref-read-failed", error.strip()[:160]
        return "no-remote", "origin is not configured"
    canonical, error = canonical_remote_branch(cwd)
    if canonical is None:
        return "remote-head-read-failed", error
    if branch != canonical:
        return "wrong-branch", "%s is checked out; origin requires %s" % (branch, canonical)
    upstream = "origin/" + canonical
    rc, configured_upstream, _ = git(cwd, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if rc != 0 or configured_upstream != upstream:
        return "no-upstream", "%s does not track %s" % (branch, upstream)

    if fetch:
        refspec = "+refs/heads/%s:refs/remotes/origin/%s" % (canonical, canonical)
        rc, output, error = git_mutate(cwd, "fetch", "--quiet", "--no-tags", "origin", refspec)
        if rc != 0:
            return "fetch-failed", (error or output or "git fetch failed")[:200]

    rc, _, error = git(cwd, "rev-parse", "--verify", upstream + "^{commit}")
    if rc != 0:
        if error and "Needed a single revision" not in error and "unknown revision" not in error:
            return "ref-read-failed", error.strip()[:160]
        return "no-upstream", "%s does not exist locally" % upstream
    rc, unmerged, error = git(cwd, "diff", "--name-only", "--diff-filter=U")
    if rc != 0:
        return "ref-read-failed", (error.strip()[:160] or "could not inspect merge conflicts")
    if unmerged.strip():
        return "unmerged", "the working tree has unresolved paths"

    rc, behind_ahead, error = git(cwd, "rev-list", "--left-right", "--count", "%s...HEAD" % upstream)
    if rc != 0:
        return "ref-read-failed", (error.strip()[:160] or "could not compare HEAD with %s" % upstream)
    try:
        behind, ahead = (int(x) for x in behind_ahead.split())
    except ValueError:
        return "ref-read-failed", "git returned an unreadable commit comparison"
    if behind and ahead:
        return "diverged", "%d behind, %d ahead of %s" % (behind, ahead, upstream)
    if behind:
        return "behind", "%d behind %s" % (behind, upstream)
    return "ok", ""


def gate6_probe_state(cwd):
    """Run GATE6 with a real fetch into the writable harness cache.

    This is for a developer-selected project that is not a workspace root.
    It reads the project's Git state but does not update its refs or objects.
    """
    rc, _, _ = git(cwd, "rev-parse", "--git-dir")
    if rc != 0:
        return "not-repo", "working directory is not a git repository"
    rc, head, error = git(cwd, "rev-parse", "--verify", "HEAD^{commit}")
    if rc != 0 or not re.fullmatch(r"[0-9a-fA-F]{40,64}", head):
        return "head-read-failed", (error.strip()[:160] or "HEAD could not be read")
    rc, branch, error = git(cwd, "symbolic-ref", "--quiet", "--short", "HEAD")
    if rc != 0 or not branch:
        return ("ref-read-failed", error.strip()[:160]) if error else ("no-upstream", "detached HEAD has no branch to pull")
    rc, remote_url, error = git(cwd, "remote", "get-url", "origin")
    if rc != 0 or not remote_url:
        return "no-remote", "origin is not configured"
    canonical, error = canonical_remote_branch(cwd)
    if canonical is None:
        return "remote-head-read-failed", error
    if branch != canonical:
        return "wrong-branch", "%s is checked out; origin requires %s" % (branch, canonical)
    upstream = "origin/" + canonical
    rc, configured_upstream, _ = git(cwd, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if rc != 0 or configured_upstream != upstream:
        return "no-upstream", "%s does not track %s" % (branch, upstream)
    rc, unmerged, error = git(cwd, "diff", "--name-only", "--diff-filter=U")
    if rc != 0:
        return "ref-read-failed", (error.strip()[:160] or "could not inspect merge conflicts")
    if unmerged.strip():
        return "unmerged", "the working tree has unresolved paths"
    cache_ok, cache_detail = cache_write_ready()
    if not cache_ok:
        return "fetch-failed", cache_detail
    try:
        with tempfile.TemporaryDirectory(prefix="git-probe-", dir=CACHE) as probe:
            initialized = subprocess.run(["git", "init", "--bare", "--quiet", probe], capture_output=True, text=True, timeout=30)
            if initialized.returncode != 0:
                return "fetch-failed", (initialized.stderr or initialized.stdout or "temporary Git repository failed")[:200]
            refspec = "+refs/heads/%s:refs/remotes/origin/%s" % (canonical, canonical)
            fetched = subprocess.run(
                ["git", "--git-dir", probe, "fetch", "--quiet", "--no-tags", remote_url, refspec],
                capture_output=True,
                text=True,
                timeout=90,
            )
            if fetched.returncode != 0:
                return "fetch-failed", (fetched.stderr or fetched.stdout or "git fetch failed")[:200]
            remote_ref = "refs/remotes/origin/" + canonical
            remote = subprocess.run(
                ["git", "--git-dir", probe, "rev-parse", "--verify", remote_ref + "^{commit}"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            remote_tip = remote.stdout.strip()
            if remote.returncode != 0 or not re.fullmatch(r"[0-9a-fA-F]{40,64}", remote_tip):
                return "ref-read-failed", (remote.stderr or "fetched remote tip is unreadable")[:160]
            rc, objects, error = git(cwd, "rev-parse", "--git-path", "objects")
            if rc != 0 or not objects:
                return "ref-read-failed", (error or "project object directory is unreadable")[:160]
            if not os.path.isabs(objects):
                objects = os.path.join(cwd, objects)
            environment = dict(os.environ, GIT_ALTERNATE_OBJECT_DIRECTORIES=os.path.realpath(objects), GIT_OPTIONAL_LOCKS="0")
            compared = subprocess.run(
                ["git", "--git-dir", probe, "rev-list", "--left-right", "--count", "%s...%s" % (remote_tip, head)],
                capture_output=True,
                text=True,
                timeout=30,
                env=environment,
            )
            if compared.returncode != 0:
                return "ref-read-failed", (compared.stderr or "could not compare fetched origin with HEAD")[:160]
            try:
                behind, ahead = (int(value) for value in compared.stdout.split())
            except ValueError:
                return "ref-read-failed", "git returned an unreadable commit comparison"
            if behind and ahead:
                return "diverged", "%d behind, %d ahead of %s" % (behind, ahead, upstream)
            if behind:
                return "behind", "%d behind %s" % (behind, upstream)
            return "ok", ""
    except (OSError, subprocess.SubprocessError) as error:
        return "fetch-failed", str(error)[:200]


def gate6_repair(cwd, state):
    """Return the single repair path for live remote drift."""
    parts = [
        sys.executable,
        os.path.join(TOOLS, "git_sync", "git_sync.py"),
        "repair",
        "--root",
        os.path.realpath(cwd),
    ]
    command = subprocess.list2cmdline(parts) if os.name == "nt" else shlex.join(parts)
    if state in ("behind", "diverged"):
        return command
    if state == "fetch-failed":
        return "restore remote access before the next remote validation"
    if state == "no-remote":
        return "configure origin and its tracking branch outside this Codex session"
    if state == "no-upstream":
        return "repair the existing origin tracking ref outside this Codex session"
    if state == "not-repo":
        return "open a clone of the remote repository"
    if state == "wrong-branch":
        return "check out origin's default branch, then retry"
    if state == "unmerged":
        return "resolve or abort the existing merge/rebase before writing"
    if state in ("head-read-failed", "ref-read-failed"):
        return "repair project .git permission"
    if state == "remote-head-read-failed":
        return "repair origin HEAD or network access"
    return "repair the repository before writing"


def gate6_instruction(cwd, state, detail=""):
    command = gate6_repair(cwd, state)
    branch = ""
    match = re.search(r"origin requires ([^\s]+)", detail or "")
    if match:
        branch = match.group(1)
    current = ""
    match = re.search(r"^([^\s]+) does not track origin/([^\s]+)", detail or "")
    if match:
        current = match.group(1)
        branch = match.group(2)
    messages = {
        "behind": "Sync the proj; retry: %s" % command,
        "diverged": "Sync the proj; retry: %s" % command,
        "fetch-failed": "Remote validation unavailable; restore origin access before the next validation.",
        "no-remote": "Set origin and its tracking branch; retry.",
        "no-upstream": "Set %s to track origin/%s; retry." % (current or "the branch", branch or "the branch"),
        "not-repo": "Open a Git clone of %s → start a new Codex task there." % project_name(cwd),
        "wrong-branch": "Check out %s; retry." % (branch or "origin's default branch"),
        "unmerged": "Resolve/abort the merge/rebase; retry.",
        "head-read-failed": blocker_instruction("git-write", cwd),
        "ref-read-failed": blocker_instruction("git-write", cwd),
        "remote-head-read-failed": "Restore origin access and set its default branch; retry.",
    }
    return messages.get(state, blocker_instruction("new-task", cwd))


def _shell_argv(tool_name, tool_input):
    if tool_name not in ("Bash", "Shell", "exec_command") or not isinstance(tool_input, dict):
        return None
    command = tool_input.get("command") or tool_input.get("cmd")
    if not isinstance(command, str) or not command.strip() or "\n" in command or "\r" in command:
        return None
    try:
        argv = shlex.split(command, posix=os.name != "nt")
    except ValueError:
        return None
    if os.name == "nt":
        argv = [part.strip('"') for part in argv]
    return argv


def _is_python_executable(value):
    if os.path.isabs(value):
        return os.path.realpath(value) == os.path.realpath(sys.executable)
    resolved = which(value)
    return bool(resolved and os.path.realpath(resolved) == os.path.realpath(sys.executable))


def finalization_invocation(tool_name, tool_input, cwd, session_id):
    """Recognize only this turn's exact pre-final validation command."""
    argv = _shell_argv(tool_name, tool_input)
    if not argv or len(argv) != 6 or not _is_python_executable(argv[0]):
        return False
    tool = os.path.realpath(os.path.expanduser(argv[1]))
    expected = os.path.realpath(os.path.join(HARNESS, "shared", "gates", "finalize.py"))
    return bool(
        tool == expected
        and argv[2] == "--root"
        and os.path.realpath(os.path.expanduser(argv[3])) == os.path.realpath(cwd)
        and argv[4] == "--session"
        and argv[5] == str(session_id)
    )


def _command_text(parts):
    return subprocess.list2cmdline(parts) if os.name == "nt" else shlex.join(parts)


def recovery_command(kind, cwd):
    """Render the canonical exact command for one in-session repair."""
    root = os.path.realpath(cwd)
    if kind == RECOVERY_API_SYNC:
        parts = [sys.executable, os.path.join(TOOLS, "api_dump", "api_dump.py"), "--sync"]
    elif kind == RECOVERY_API_GLOBALS:
        parts = [sys.executable, os.path.join(TOOLS, "api_dump", "api_dump.py"), "--emit-globals"]
        updates = os.path.join(root, "shared", "src", "ServerScriptService", "Services", "Updates")
        if os.path.isdir(updates):
            parts += ["--updates", updates]
    elif kind == RECOVERY_GIT_SYNC:
        parts = [sys.executable, os.path.join(TOOLS, "git_sync", "git_sync.py"), "repair", "--root", root]
    elif kind == RECOVERY_TYPE_CACHE:
        parts = [sys.executable, os.path.join(TOOLS, "type_cache", "type_cache.py"), "ensure", "--root", root]
    elif kind == RECOVERY_TOOLCHAIN:
        parts = toolchain_install_command()
    elif kind == RECOVERY_RELINK:
        parts = [
            sys.executable,
            os.path.join(HARNESS, "openai", "setup", "permissions_harness.py"),
            "--relink",
        ]
    else:
        return ""
    return _command_text(parts)


def recovery_prompt_context(cwd, repairs):
    commands = [recovery_command(repair, cwd) for repair in repairs]
    commands = [command for command in commands if command]
    if not commands:
        return ""
    context = (
        "ROBLOX_HARNESS_RECOVERY_ONLY\n"
        "Session authorization is degraded. Run only an exact recovery command shown below. "
        "Do not edit project files or run another tool until recovery succeeds.\n"
        + "\n".join(commands)
    )
    if RECOVERY_RELINK in repairs:
        context += "\nAfter relink, review changed hooks and retry the current task."
    return context


def recovery_kinds_from_precheck(detail):
    """Return repairs only when every reported precondition is recoverable."""
    records = [line for line in str(detail or "").splitlines() if line.startswith(("GATE4|", "GATE6|"))]
    if not records:
        return []
    repairs = []
    for record in records:
        fields = record.split("|", 2)
        text = " ".join(fields[1:]).casefold()
        if "api_globals" in text or "api globals" in text:
            repairs.append(RECOVERY_API_GLOBALS)
        elif "corpus" in text:
            repairs.append(RECOVERY_API_SYNC)
        elif "type cache" in text:
            repairs.append(RECOVERY_TYPE_CACHE)
        elif any(token in text for token in ("toolchain", "lute", "luau-lsp", "argon")):
            repairs.append(RECOVERY_TOOLCHAIN)
        elif "relink" in text:
            repairs.append(RECOVERY_RELINK)
        elif fields[0] == "GATE6" and any(state in text for state in ("behind", "diverged")):
            repairs.append(RECOVERY_GIT_SYNC)
        else:
            return []
    return sorted(set(repairs))


def recovery_invocation(tool_name, tool_input, cwd):
    """Recognize one exact, unchained recovery command and return its kind."""
    argv = _shell_argv(tool_name, tool_input)
    if not argv:
        return None
    if os.name == "nt" and len(argv) == 5 and _is_python_executable(argv[0]):
        windows_setup = os.path.realpath(os.path.join(HARNESS, "openai", "setup", "windows.py"))
        if (
            os.path.realpath(os.path.expanduser(argv[1])) == windows_setup
            and argv[2] == "--harness"
            and os.path.realpath(os.path.expanduser(argv[3])) == os.path.realpath(HARNESS)
            and argv[4] == "--toolchain-only"
        ):
            return RECOVERY_TOOLCHAIN
    toolchain = os.path.realpath(os.path.join(TOOLS, "get_toolchain.sh"))
    shell = "/bin/sh" if os.path.isfile("/bin/sh") else which("sh")
    if len(argv) == 2 and shell and os.path.realpath(os.path.expanduser(argv[0])) == os.path.realpath(shell):
        return RECOVERY_TOOLCHAIN if os.path.realpath(os.path.expanduser(argv[1])) == toolchain else None
    if len(argv) < 3 or not _is_python_executable(argv[0]):
        return None
    tool = os.path.realpath(os.path.expanduser(argv[1]))
    root = os.path.realpath(cwd)
    api_dump = os.path.realpath(os.path.join(TOOLS, "api_dump", "api_dump.py"))
    if tool == api_dump:
        if argv[2:] == ["--sync"]:
            return RECOVERY_API_SYNC
        if argv[2:] == ["--emit-globals"]:
            return RECOVERY_API_GLOBALS
        updates = os.path.join(root, "shared", "src", "ServerScriptService", "Services", "Updates")
        if argv[2:4] == ["--emit-globals", "--updates"] and len(argv) == 5:
            if os.path.realpath(os.path.expanduser(argv[4])) == os.path.realpath(updates):
                return RECOVERY_API_GLOBALS
        return None
    git_sync = os.path.realpath(os.path.join(TOOLS, "git_sync", "git_sync.py"))
    if tool == git_sync and len(argv) == 5 and argv[2:4] == ["repair", "--root"]:
        return RECOVERY_GIT_SYNC if os.path.realpath(os.path.expanduser(argv[4])) == root else None
    type_cache = os.path.realpath(os.path.join(TOOLS, "type_cache", "type_cache.py"))
    if tool == type_cache and len(argv) == 5 and argv[2] in ("ensure", "recover") and argv[3] == "--root":
        return RECOVERY_TYPE_CACHE if os.path.realpath(os.path.expanduser(argv[4])) == root else None
    permissions_setup = os.path.realpath(os.path.join(HARNESS, "openai", "setup", "permissions_harness.py"))
    if tool == permissions_setup and argv[2:] == ["--relink"]:
        return RECOVERY_RELINK
    scaffold = os.path.realpath(os.path.join(HARNESS, "shared", "skills", "roblox-new-game", "scripts", "scaffold.py"))
    if tool == scaffold and len(argv) == 5 and argv[2:4] == ["relink", "--root"]:
        return RECOVERY_RELINK if os.path.realpath(os.path.expanduser(argv[4])) == root else None
    return None


def maintenance_read_invocation(tool_name, tool_input):
    """Recognize the small read-only command surface of the maintainer agent."""
    argv = _shell_argv(tool_name, tool_input)
    if not argv or len(argv) < 3 or not _is_python_executable(argv[0]):
        return False
    tool = os.path.realpath(os.path.expanduser(argv[1]))
    api_dump = os.path.realpath(os.path.join(TOOLS, "api_dump", "api_dump.py"))
    if tool != api_dump:
        return False
    return argv[2] in {
        "class", "instance", "props", "services", "enum", "enumitems", "library",
        "ops", "describe", "find", "docs", "doc", "code", "sample", "--check-overlay",
    }


def maintenance_spawn_invocation(tool_name, tool_input, cwd, repairs):
    """Recognize a maintainer dispatch for a prescribed recovery.

    Codex encrypts the delegated message before PreToolUse. The explicit
    custom-agent role is therefore the authority; the child gate still admits
    only exact commands from ``repairs``.
    """
    name = re.sub(r"[^a-z0-9]", "", str(tool_name or "").casefold())
    if name not in ("spawnagent", "collaborationspawnagent", "functionsspawnagent"):
        return None
    if not isinstance(tool_input, dict):
        return None
    explicit_role = tool_input.get("agent_type") or tool_input.get("agent_name")
    task_name = tool_input.get("task_name") or tool_input.get("name")
    if explicit_role:
        return repairs[0] if explicit_role == "maintainer" and repairs else None
    if task_name != "maintainer":
        return None
    prompt = tool_input.get("message") or tool_input.get("prompt")
    if not isinstance(prompt, str) or not prompt:
        return None
    matched = [repair for repair in repairs if recovery_command(repair, cwd) in prompt]
    return matched[0] if len(matched) == 1 else None


def maintenance_control_invocation(tool_name):
    """Recognize the read-only join needed to collect a maintainer result."""
    name = re.sub(r"[^a-z0-9]", "", str(tool_name or "").casefold())
    return name in ("waitagent", "collaborationwaitagent", "functionswaitagent")


def is_git_sync_repair(tool_name, tool_input, cwd):
    """Recognize only the exact repair command that may cross a stale GATE6."""
    return recovery_invocation(tool_name, tool_input, cwd) == RECOVERY_GIT_SYNC


# ------------------------------------------------ GATE4 probe: three tiers --


def _cache_studio_port(port):
    os.makedirs(CACHE, exist_ok=True)
    with open(PORT_CACHE, "w") as f:
        f.write(str(port))
    return int(port)


def _resolve_port_windows():
    try:
        tasks = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq StudioMCP.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
        )
        pids = {
            row[1]
            for row in csv.reader(tasks.stdout.splitlines())
            if len(row) > 1 and row[0].casefold() == "studiomcp.exe" and row[1].isdigit()
        }
        sockets = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True)
    except OSError:
        return None
    for line in sockets.stdout.splitlines():
        cells = line.split()
        if len(cells) < 5 or cells[-1] not in pids or cells[-2].upper() != "LISTENING":
            continue
        local = cells[1]
        port = local.rsplit(":", 1)[-1]
        if port.isdigit():
            return _cache_studio_port(port)
    return None


def resolve_port():
    """Tier 0: resolve StudioMCP's listening port once at SessionStart."""
    if os.name == "nt":
        return _resolve_port_windows()
    try:
        r = subprocess.run(["pgrep", "-f", "StudioMCP"], capture_output=True, text=True)
    except OSError:
        return None
    pids = [p for p in r.stdout.split() if p.isdigit()]
    for pid in pids:
        try:
            r2 = subprocess.run(
                ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-a", "-p", pid],
                capture_output=True,
                text=True,
            )
        except OSError:
            return None
        for line in r2.stdout.splitlines():
            for cell in line.split():
                if cell.startswith("127.0.0.1:") or cell.startswith("*:"):
                    port = cell.rsplit(":", 1)[-1]
                    if port.isdigit():
                        return _cache_studio_port(port)
    return None


def studio_running():
    """True when Roblox Studio is running, independent of StudioMCP."""
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq RobloxStudioBeta.exe", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
            )
        except OSError:
            return False
        return "RobloxStudioBeta.exe" in result.stdout
    try:
        result = subprocess.run(["pgrep", "-f", "RobloxStudio"], capture_output=True, text=True)
    except OSError:
        return False
    return result.returncode == 0 and any(value.isdigit() for value in result.stdout.split())


def cached_port():
    try:
        with open(PORT_CACHE) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def proxy_alive():
    """Tier 1: connect() to the cached port — 0.1 ms, every write, uncached.
    A failed connect re-resolves once before it blocks."""
    port = cached_port()
    if port is None:
        port = resolve_port()
        if port is None:
            return False
    for attempt in (0, 1):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            if attempt == 0:
                port = resolve_port()
                if port is None:
                    return False
    return False


def studio_attached(session_id="gate", raise_errors=False):
    """Tier 2: one spawned-stdio round-trip proving Studio is attached AND
    yielding the lock key. TTL 30 s; only success is cached, so a failed probe
    is never cached and recovery is immediate."""
    try:
        with open(PLACE_CACHE) as f:
            stamp, place = f.read().strip().split("|")
        if time.time() - float(stamp) < TTL:
            return int(place)
    except (OSError, ValueError):
        pass
    try:
        from studio_rpc import StudioRPC

        with StudioRPC(timeout=10) as rpc:
            _, place = rpc.select_studio(set())
        os.makedirs(CACHE, exist_ok=True)
        with open(PLACE_CACHE, "w") as f:
            f.write("%f|%d" % (time.time(), place))
        return place
    except Exception:
        if raise_errors:
            raise
        return None


def corpus_assets_error():
    """Return a precise corpus validation error, or an empty string."""
    dump_path = os.path.join(CACHE, "API-Dump.json")
    docs_root = os.path.join(CACHE, "creator-docs")
    docs_git = os.path.join(docs_root, ".git")
    engine = os.path.join(docs_root, "content", "en-us", "reference", "engine")
    index_path = os.path.join(CACHE, "docs_index.json")
    for path, label, directory in (
        (dump_path, "API-Dump.json", False),
        (docs_git, "Creator Docs .git", True),
        (engine, "Creator Docs engine corpus", True),
        (index_path, "docs_index.json", False),
    ):
        present = os.path.isdir(path) if directory else os.path.isfile(path)
        if not present:
            return "%s is missing" % label
    try:
        with open(dump_path, encoding="utf-8") as f:
            dump = json.load(f)
        if not isinstance(dump, dict) or not isinstance(dump.get("Classes"), list) or not isinstance(dump.get("Enums"), list):
            return "API-Dump.json has an invalid schema"
        has_yaml = False
        for directory, _, names in os.walk(engine):
            if any(name.endswith((".yaml", ".yml")) for name in names):
                has_yaml = True
                break
        if not has_yaml:
            return "Creator Docs engine corpus has no YAML records"
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)
        if not isinstance(index, list):
            return "docs_index.json has an invalid schema"
        os.listdir(docs_git)
    except (OSError, ValueError, UnicodeError) as e:
        return "corpus is unreadable or malformed: %s" % str(e)[:160]
    return ""


def corpus_status(now=None):
    """Return fresh, stale, missing, or malformed and its diagnostic."""
    dump_path = os.path.join(CACHE, "API-Dump.json")
    docs_root = os.path.join(CACHE, "creator-docs")
    docs_git = os.path.join(docs_root, ".git")
    engine = os.path.join(docs_root, "content", "en-us", "reference", "engine")
    index_path = os.path.join(CACHE, "docs_index.json")
    if not os.path.isfile(dump_path) or not os.path.isdir(docs_git) or not os.path.isdir(engine) or not os.path.isfile(index_path):
        return "missing", "API dump or Creator Docs corpus is missing"
    error = corpus_assets_error()
    if error:
        return "malformed", error
    refresh_path = os.path.join(CACHE, "corpus-refresh.json")
    if not os.path.exists(refresh_path):
        return "stale", "successful-refresh timestamp is missing"
    try:
        with open(refresh_path, encoding="utf-8") as f:
            refresh = json.load(f)
        refreshed_at = refresh.get("refreshed_at") if isinstance(refresh, dict) else None
        if not isinstance(refreshed_at, (int, float)) or isinstance(refreshed_at, bool):
            return "malformed", "successful-refresh timestamp is malformed"
        age = (time.time() if now is None else now) - float(refreshed_at)
        if age < -300:
            return "malformed", "successful-refresh timestamp is in the future"
    except (OSError, ValueError, UnicodeError) as e:
        return "malformed", "successful-refresh timestamp is unreadable or malformed: %s" % str(e)[:160]
    if age >= CORPUS_MAX_AGE:
        return "stale", "successful refresh is at least 24 hours old"
    return "fresh", ""


def corpus_present():
    """A write-authorizing corpus is valid and successfully refreshed."""
    return corpus_status()[0] == "fresh"


def cache_write_ready():
    """Read-only permission check for ordinary harness-cache writes."""
    path = CACHE
    candidate = path
    while not os.path.exists(candidate):
        parent = os.path.dirname(candidate)
        if parent == candidate:
            break
        candidate = parent
    if not os.path.isdir(candidate) or not os.access(candidate, os.W_OK | os.X_OK):
        return False, "%s cannot be created or updated" % path
    if os.path.exists(path) and not os.access(path, os.R_OK | os.W_OK | os.X_OK):
        return False, "%s is not readable and writable" % path
    return True, ""


def cache_sync_ready():
    """Read-only permission check for paths a required --sync will mutate."""
    for path in (CACHE, os.path.join(CACHE, "creator-docs", ".git")):
        candidate = path
        while not os.path.exists(candidate):
            parent = os.path.dirname(candidate)
            if parent == candidate:
                break
            candidate = parent
        if not os.path.isdir(candidate) or not os.access(candidate, os.W_OK | os.X_OK):
            return False, "%s cannot be created or updated" % path
    return True, ""


def api_globals_present():
    path = os.path.join(CACHE, "api_globals.luau")
    return os.path.isfile(path) and os.access(path, os.R_OK) and os.path.getsize(path) > 0


def toolchain_present():
    lute = os.path.isfile(LUTE) and (os.name == "nt" or os.access(LUTE, os.X_OK))
    bundled_lsp = os.path.isfile(LUAU_LSP) and (os.name == "nt" or os.access(LUAU_LSP, os.X_OK))
    return bool(lute and (bundled_lsp or which("luau-lsp")))


def which(name, path=None, pathext=None, windows=None):
    """Resolve an executable with native Windows PATHEXT behavior."""
    windows = os.name == "nt" if windows is None else bool(windows)
    path = os.environ.get("PATH", "") if path is None else str(path)
    pathext = os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD") if pathext is None else str(pathext)
    extensions = [""]
    if windows and not os.path.splitext(str(name))[1]:
        extensions += [item if item.startswith(".") else "." + item for item in pathext.split(";") if item]
    directories = [""] if os.path.dirname(str(name)) else path.split(";" if windows else os.pathsep)
    for directory in directories:
        base = str(name) if not directory else os.path.join(directory.strip('"'), str(name))
        for extension in extensions:
            candidate = base + extension
            if os.path.isfile(candidate) and (windows or os.access(candidate, os.X_OK)):
                return candidate
    return None


def toolchain_install_command(windows=None):
    """Return the one pinned installer for the current host."""
    windows = os.name == "nt" if windows is None else bool(windows)
    if windows:
        return [
            sys.executable,
            os.path.join(HARNESS, "openai", "setup", "windows.py"),
            "--harness",
            HARNESS,
            "--toolchain-only",
        ]
    shell = "/bin/sh" if os.path.isfile("/bin/sh") else (which("sh") or "sh")
    return [shell, os.path.join(TOOLS, "get_toolchain.sh")]
