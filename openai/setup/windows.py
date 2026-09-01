#!/usr/bin/env python3
"""One-shot Windows Codex file renderer used by setup_windows.bat.

The batch file repairs transport links first, then this script renders native
Windows hook commands. Project trust and exact hook approval remain human
actions in Codex through `/hooks`.
"""

import argparse
import hashlib
import io
import json
import ntpath
import os
import re
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE_HARNESS = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(SOURCE_HARNESS, "shared", "gates"))
import gatelib  # noqa: E402


WINDOWS_TOOLCHAIN = (
    (
        "lute.exe",
        "https://github.com/luau-lang/lute/releases/download/v1.0.0/lute-windows-x86_64.zip",
        "4f5de7cb1844d0df4e5796ad08d485ce7b6c35f7ba8d54046c7e7a12e7c28d92",
    ),
    (
        "luau-lsp.exe",
        "https://github.com/JohnnyMorganz/luau-lsp/releases/download/1.68.1/luau-lsp-win64.zip",
        "15f2add7c70191c5cd636b047968760f0056893b63be10294453c75430bcb339",
    ),
)


def install_windows_asset(url, expected_sha256, executable, bin_dir, opener=None):
    """Download, verify, and atomically extract one pinned Windows executable."""
    destination = os.path.join(bin_dir, executable)
    if os.path.isfile(destination):
        return False
    response = (opener or urllib.request.urlopen)(url)
    try:
        archive_bytes = response.read()
    finally:
        close = getattr(response, "close", None)
        if close:
            close()
    digest = hashlib.sha256(archive_bytes).hexdigest()
    if digest.casefold() != expected_sha256.casefold():
        raise RuntimeError("%s archive sha256 mismatch" % executable)
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            members = [
                info
                for info in archive.infolist()
                if not info.is_dir() and os.path.basename(info.filename).casefold() == executable.casefold()
            ]
            if len(members) != 1:
                raise RuntimeError("%s archive must contain one %s" % (executable, executable))
            executable_bytes = archive.read(members[0])
    except zipfile.BadZipFile as error:
        raise RuntimeError("%s archive is not a valid zip: %s" % (executable, error))
    os.makedirs(bin_dir, exist_ok=True)
    temporary = destination + ".setup-windows.tmp"
    try:
        with open(temporary, "wb") as handle:
            handle.write(executable_bytes)
        os.chmod(temporary, 0o755)
        os.replace(temporary, destination)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return True


def install_windows_toolchain(harness, opener=None):
    bin_dir = os.path.join(harness, "tools", "bin")
    states = []
    for executable, url, digest in WINDOWS_TOOLCHAIN:
        installed = install_windows_asset(url, digest, executable, bin_dir, opener=opener)
        states.append("%s=%s" % (executable, "installed" if installed else "exact"))
    print("windows-toolchain|" + "|".join(states))
    return True


def _atomic_text(path, text):
    encoded = text.encode("utf-8")
    try:
        with open(path, "rb") as existing:
            if existing.read() == encoded:
                return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".setup-windows.tmp"
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(temporary, path)
    return True


def _load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError:
        return {} if default is None else default
    except (OSError, ValueError, UnicodeError) as error:
        raise RuntimeError("%s is unreadable or malformed: %s" % (path, str(error)[:160]))
    if not isinstance(value, dict):
        raise RuntimeError("%s must contain a JSON object" % path)
    return value


def _powershell_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def _codex_windows_command(command, python_executable, project_local_harness=True):
    match = re.search(r"(--host codex --event [A-Za-z]+(?: --hook-scope project)?)$", command)
    if not match:
        raise RuntimeError("canonical Codex hook command is unsupported: %s" % command)
    root = "$root"
    script = ".roblox-harness\\openai\\hooks\\adapter.py" if project_local_harness else "shared\\gates\\harness_gate.py"
    return (
        "powershell.exe -NoProfile -Command \"$root = git rev-parse --show-toplevel; "
        "& %s -B (Join-Path %s '%s') %s\""
        % (_powershell_quote(python_executable), root, script, match.group(1))
    )


def _render_hook_document(path, host, python_executable, project_local_harness=True):
    document = _load_json(path)
    hooks = document.get("hooks")
    if not isinstance(hooks, dict):
        raise RuntimeError("%s has no hooks object" % path)
    for entries in hooks.values():
        if not isinstance(entries, list):
            raise RuntimeError("%s has a malformed hook event" % path)
        for entry in entries:
            for handler in entry.get("hooks", []) if isinstance(entry, dict) else []:
                if isinstance(handler, dict) and handler.get("type") == "command":
                    if host == "codex":
                        handler["commandWindows"] = _codex_windows_command(
                            str(handler.get("command", "")), python_executable, project_local_harness
                        )
                    else:
                        args = handler.get("args")
                        if not isinstance(args, list) or "-B" not in args:
                            raise RuntimeError("canonical Claude hook command is unsupported")
                        handler["command"] = python_executable
    return document


def _toml_string(value):
    return json.dumps(str(value), ensure_ascii=False)


def render_windows_project(source_harness, runtime_harness, project, python_executable=None):
    """Render owned project integrations; return (hooks_changed, discovery_changed)."""
    project = os.path.abspath(project)
    if not gatelib.is_roblox_project(project):
        raise RuntimeError("%s has no root .roblox sentinel" % project)
    python_executable = python_executable or sys.executable
    if not ntpath.isabs(python_executable):
        python_executable = os.path.abspath(python_executable)

    local_harness = os.path.join(project, gatelib.PROJECT_HARNESS_DIR)
    if os.path.realpath(local_harness) != os.path.realpath(source_harness):
        raise RuntimeError("%s must use this .roblox-harness checkout" % project)

    codex_hooks = _render_hook_document(
        os.path.join(source_harness, "openai", "hooks", "project.json"),
        "codex",
        python_executable,
    )
    codex_dir = os.path.join(project, ".codex")
    codex_hooks_changed = _atomic_text(
        os.path.join(codex_dir, "hooks.json"),
        json.dumps(codex_hooks, indent=1, ensure_ascii=False) + "\n",
    )

    canonical_claude = _render_hook_document(
        os.path.join(source_harness, "claude", "settings", "project.json"),
        "claude",
        python_executable,
    )
    canonical_claude.pop("__doc", None)
    settings_path = os.path.join(project, ".claude", "settings.json")
    existing = _load_json(settings_path)
    claude_hooks_changed = existing.get("hooks") != canonical_claude.get("hooks")
    existing.update(canonical_claude)
    settings_changed = _atomic_text(settings_path, json.dumps(existing, indent=1, ensure_ascii=False) + "\n")

    project_config = (
        "# generated by setup_windows.bat - the Codex-side project config.\n"
        "# Loads only when the project is trusted.\n\n"
        "service_tier = \"fast\"\n\n"
        "[features]\n"
        "fast_mode = true\n"
        "multi_agent = true\n\n"
        "[agents]\n"
        "enabled = true\n\n"
        "[shell_environment_policy]\n"
        "inherit = \"core\"\n\n"
        "[shell_environment_policy.set]\n"
        "CLAUDE_CODE_DISABLE_AUTO_MEMORY = \"1\"\n\n"
        "[mcp_servers.Roblox_Studio]\n"
        "command = %s\n"
        "args = [%s, %s]\n"
        "cwd = %s\n"
        "startup_timeout_sec = 20\n"
        "tool_timeout_sec = 120\n"
        "\n"
        "[mcp_servers.Roblox_Studio.tools.execute_luau]\n"
        "approval_mode = \"approve\"\n"
        % (
            _toml_string(python_executable),
            _toml_string("-B"),
            _toml_string(".roblox-harness/tools/studio_mcp_launcher.py"),
            _toml_string("."),
        )
    )
    config_path = os.path.join(codex_dir, "config.toml")
    try:
        with open(config_path, encoding="utf-8") as existing_file:
            existing_config = existing_file.read()
    except FileNotFoundError:
        existing_config = ""
    config_changed = _atomic_text(
        config_path,
        gatelib.merge_project_codex_config(existing_config, project_config),
    )
    hooks_changed = codex_hooks_changed or claude_hooks_changed
    return hooks_changed, hooks_changed or settings_changed or config_changed


def render_windows_harness(source_harness, python_executable=None):
    """Render harness hook integrations; return (hooks_changed, discovery_changed)."""
    python_executable = python_executable or sys.executable
    codex_path = os.path.join(source_harness, ".codex", "hooks.json")
    codex_hooks = _render_hook_document(
        codex_path,
        "codex",
        python_executable,
        project_local_harness=False,
    )
    codex_changed = _atomic_text(codex_path, json.dumps(codex_hooks, indent=1, ensure_ascii=False) + "\n")
    claude_path = os.path.join(source_harness, ".claude", "settings.json")
    existing_claude = _load_json(claude_path)
    claude_hooks = _render_hook_document(
        claude_path,
        "claude",
        python_executable,
        project_local_harness=False,
    )
    claude_hooks_changed = existing_claude.get("hooks") != claude_hooks.get("hooks")
    claude_changed = _atomic_text(claude_path, json.dumps(claude_hooks, indent=1, ensure_ascii=False) + "\n")
    hooks_changed = codex_changed or claude_hooks_changed
    return hooks_changed, hooks_changed or claude_changed


def setup_messages(project_count, hooks_changed, discovery_changed):
    lines = [
        "codex-bootstrap|projects=%d|hooks=%s|discovery=%s|profile=Roblox"
        % (
            project_count,
            "changed" if hooks_changed else "exact",
            "changed" if discovery_changed else "exact",
        )
    ]
    if hooks_changed:
        lines.append(
            "hook-review-required|open /hooks, review the changed definitions, and approve them"
        )
    if discovery_changed:
        lines.append(
            "fresh-session-required|close Codex windows using the changed integration, then open a new session"
        )
    else:
        lines.append("discovery-exact|no hook approval or new session required")
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--harness", required=True)
    parser.add_argument("--project", action="append", default=[])
    parser.add_argument("--toolchain-only", action="store_true")
    args = parser.parse_args(argv)
    source_harness = SOURCE_HARNESS
    runtime_harness = os.path.realpath(args.harness)
    if runtime_harness != os.path.realpath(source_harness):
        raise RuntimeError("--harness must identify this harness checkout")
    if args.toolchain_only:
        if args.project:
            raise RuntimeError("--toolchain-only does not accept --project")
        install_windows_toolchain(source_harness)
        return 0
    projects = []
    for project in args.project:
        real = os.path.realpath(project)
        if real not in projects:
            projects.append(real)
    if not os.path.isfile(os.path.join(source_harness, "openai", "hooks", "project.json")):
        raise RuntimeError("canonical harness hooks are absent")
    profile_ok, detail = gatelib.permissions_harness()
    if not profile_ok:
        raise RuntimeError("Roblox permission profile is not exact: %s" % detail)
    hooks_changed = False
    discovery_changed = False
    if not projects:
        hooks_changed, discovery_changed = render_windows_harness(source_harness)
    for project in projects:
        if not gatelib.is_roblox_project(project):
            raise RuntimeError("%s has no root .roblox sentinel" % project)
        project_hooks_changed, project_discovery_changed = render_windows_project(
            source_harness,
            runtime_harness,
            project,
        )
        hooks_changed = hooks_changed or project_hooks_changed
        discovery_changed = discovery_changed or project_discovery_changed
    for line in setup_messages(len(projects), hooks_changed, discovery_changed):
        print(line)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        sys.stderr.write("windows-codex-setup: ERROR %s\n" % str(error))
        sys.exit(2)
