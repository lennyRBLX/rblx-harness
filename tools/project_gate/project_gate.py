#!/usr/bin/env python3
"""Validate the harness or one harness-managed Roblox project before harness closes."""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
HARNESS = os.path.dirname(TOOLS)
GATES = os.path.join(HARNESS, "shared", "gates")
sys.path.insert(0, GATES)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "place_map"))

import gatelib  # noqa: E402
import precheck  # noqa: E402
import session_gate as lifecycle_session_gate  # noqa: E402
import place_map  # noqa: E402
from studio_mcp_launcher import find_studio_mcp  # noqa: E402
from studio_rpc import EnvError, StudioRPC  # noqa: E402
from type_cache.type_cache import ensure as ensure_type_cache  # noqa: E402


class Reporter:
    def __init__(self):
        self.records = []
        self.failed = 0
        self.skipped = 0

    @staticmethod
    def field(value, limit=300):
        return " ".join(str(value).replace("|", "/").split())[:limit]

    def pass_(self, check, detail="ready"):
        self.records.append(("PASS", check, self.field(detail), ""))

    def fail(self, check, detail, remedy):
        self.failed += 1
        self.records.append(("FAIL", check, self.field(detail), self.field(remedy, 1000)))

    def skip(self, check, dependency):
        self.skipped += 1
        self.records.append(("SKIP", check, "blocked-by=" + self.field(dependency), ""))

    def advisory(self, check, detail):
        self.records.append(("ADVISORY", check, self.field(detail), ""))

    def emit(self, root):
        for status, check, detail, remedy in self.records:
            fields = ["CHECK", status, check, detail]
            if remedy:
                fields.append(remedy)
            print("|".join(fields))
        if self.failed:
            print("PROJECT_GATE|BLOCKED|%d" % self.failed)
            return 2
        print("PROJECT_GATE|READY|%s" % root)
        return 0


def run(command, timeout=180, cwd=None):
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    except Exception as error:
        return subprocess.CompletedProcess(command, 3, "", "%s: %s" % (type(error).__name__, error))


def executable_check(reporter, check, command, version_args=("--version",)):
    executable = command if os.path.isabs(command) else gatelib.which(command)
    if not executable or not os.path.isfile(executable) or (os.name != "nt" and not os.access(executable, os.X_OK)):
        reporter.fail(check, "executable absent", "Install the harness toolchain, then retry.")
        return None
    result = run([executable] + list(version_args), timeout=30)
    if result.returncode != 0:
        detail = result.stderr or result.stdout or "version probe failed"
        reporter.fail(check, detail, "Repair %s, then retry." % check)
        return None
    reporter.pass_(check, executable)
    return executable


def validate_root(path, reporter):
    if not path or not os.path.isabs(path):
        reporter.fail("project-root", "absolute path required", "Provide project-root: /absolute/path.")
        return None
    root = os.path.realpath(path)
    if not os.path.isdir(root):
        reporter.fail("project-root", "directory absent", "Provide an existing project root.")
        return None
    if root != os.path.realpath(HARNESS):
        if not gatelib.is_roblox_project(root):
            reporter.fail("project-root", ".roblox absent", "Provide a harness-managed project root.")
            return None
        sibling = os.path.join(os.path.dirname(root), "harness")
        if os.path.realpath(sibling) != os.path.realpath(HARNESS):
            reporter.fail("project-root", "sibling harness absent", "Place the .roblox project beside harness/.")
            return None
    try:
        result = run(["git", "-C", root, "rev-parse", "--show-toplevel"], timeout=30)
    except Exception:
        result = None
    if result is None or result.returncode != 0 or os.path.realpath(result.stdout.strip()) != root:
        detail = (result.stderr if result is not None else "git unavailable") or "path is not the Git root"
        reporter.fail("project-root", detail, "Provide the project Git root.")
        return None
    reporter.pass_("project-root", root)
    return root


def harness_checks(reporter):
    result = run(
        [sys.executable, os.path.join(TOOLS, "tests", "run_verify.py")],
        timeout=1100,
    )
    if result.returncode == 0:
        reporter.pass_("harness-verify", "all cases passed")
        return True
    reporter.fail(
        "harness-verify",
        result.stdout or result.stderr or "verification failed",
        "Repair the failing harness verification case, then retry.",
    )
    return False


def _same_bytes(source, destination):
    try:
        with open(source, "rb") as expected, open(destination, "rb") as actual:
            return expected.read() == actual.read()
    except OSError:
        return False


def generated_integration_readonly(root, host, reporter):
    """Validate selected-project discovery without writing outside the workspace."""
    hook_path = os.path.join(root, ".codex", "hooks.json") if host == "codex" else os.path.join(root, ".claude", "settings.json")
    reports = precheck.hook_registration_reports(hook_path, host) if os.path.exists(hook_path) else ["hook file absent"]
    if reports:
        reporter.fail("generated-integration", reports[0], "Open a task in the selected project and relink it.")
        return False
    if host == "codex":
        agents_ok, agents_detail = gatelib.required_codex_agents_status(root)
        if not agents_ok:
            reporter.fail("generated-integration", agents_detail, "Open a task in the selected project and relink it.")
            return False
        managed = (
            (os.path.join(HARNESS, "shared", "skills", "roblox-writer", "SKILL.md"), os.path.join(root, ".agents", "skills", "roblox-writer", "SKILL.md")),
            (os.path.join(HARNESS, "openai", "skills", "roblox-writer", "agents", "openai.yaml"), os.path.join(root, ".agents", "skills", "roblox-writer", "agents", "openai.yaml")),
        )
    else:
        managed = tuple(
            (os.path.join(HARNESS, "claude", "agents", name + ".md"), os.path.join(root, ".claude", "agents", name + ".md"))
            for name in gatelib.REQUIRED_CODEX_AGENTS
        ) + (
            (os.path.join(HARNESS, "shared", "skills", "roblox-writer", "SKILL.md"), os.path.join(root, ".claude", "skills", "roblox-writer", "SKILL.md")),
        )
    stale = next((destination for source, destination in managed if not _same_bytes(source, destination)), "")
    if stale:
        reporter.fail("generated-integration", "%s is absent or stale" % stale, "Open a task in the selected project and relink it.")
        return False
    reporter.pass_("generated-integration", "%s read-only" % host)
    return True


def generated_integration(root, host, reporter, allow_project_writes=True):
    if not allow_project_writes:
        return generated_integration_readonly(root, host, reporter)
    before = lifecycle_session_gate.discovery_snapshot(root, host)
    before_by_path = {entry[0]: entry[1:] for entry in before}
    relinker = os.path.join(HARNESS, "openai", "setup", "permissions_harness.py")
    result = run([sys.executable, relinker, "--relink", "--host", host], timeout=300, cwd=root)
    if result.returncode != 0:
        reporter.fail(
            "generated-integration",
            result.stdout or result.stderr or "relink failed",
            "Repair generated project integration, then retry.",
        )
        return False
    after = lifecycle_session_gate.discovery_snapshot(root, host)
    after_by_path = {entry[0]: entry[1:] for entry in after}
    hook_paths = (".codex/hooks.json", "<user>/hooks.json") if host == "codex" else (".claude/settings.json",)
    hook_changed = any(before_by_path.get(path) != after_by_path.get(path) for path in hook_paths)
    changed = before != after or "discovery exact; no new task required." not in result.stdout
    hook_path = os.path.join(root, ".codex", "hooks.json") if host == "codex" else os.path.join(root, ".claude", "settings.json")
    reports = precheck.hook_registration_reports(hook_path, host) if os.path.exists(hook_path) else ["hook file absent"]
    if reports:
        reporter.fail("generated-integration", reports[0], "Approve the repaired hooks and start a new task.")
        return False
    if host == "codex":
        agents_ok, agents_detail = gatelib.required_codex_agents_status(root)
        if not agents_ok:
            reporter.fail("generated-integration", agents_detail, "Relink the project agents, then retry.")
            return False
    if changed:
        actions = []
        if "Select Roblox" in result.stdout:
            actions.append("Select Roblox")
        if hook_changed:
            actions.append("approve the repaired hooks")
        actions.append("start a new task")
        remedy = "; ".join(actions)
        reporter.fail("generated-integration", "project discovery changed", remedy[:1].upper() + remedy[1:] + ".")
        return False
    reporter.pass_("generated-integration", host)
    return True


def pinned_toolchain_present():
    lute = os.path.isfile(gatelib.LUTE) and (os.name == "nt" or os.access(gatelib.LUTE, os.X_OK))
    lsp = (
        os.path.isfile(gatelib.LUAU_LSP)
        and (os.name == "nt" or os.access(gatelib.LUAU_LSP, os.X_OK))
    ) or bool(gatelib.which("luau-lsp"))
    return lute and lsp


def ensure_toolchain(reporter):
    """Run the exact installer at most once, then re-check pinned binaries."""
    if pinned_toolchain_present():
        reporter.pass_("toolchain", "current")
        return True
    command = gatelib.toolchain_install_command()
    if not command:
        reporter.fail("toolchain", "installer unavailable", "Install the harness toolchain, then retry.")
        return False
    result = run(command, timeout=600, cwd=HARNESS)
    if result.returncode != 0 or not pinned_toolchain_present():
        detail = result.stderr or result.stdout or "toolchain installer did not produce the pinned binaries"
        reporter.fail("toolchain", detail, "Repair the harness toolchain, then retry.")
        return False
    reporter.pass_("toolchain", "repaired")
    return True


def studio_tool_approval(root, reporter):
    ok, detail = gatelib.execute_luau_approval_override(root)
    if ok:
        reporter.pass_("studio-tool-approval", "execute_luau only")
        return True
    reporter.fail(
        "studio-tool-approval",
        detail,
        gatelib.execute_luau_approval_instruction(root),
    )
    return False


def authorization_checks(root, host, permission_mode, reporter):
    if host == "codex":
        ok, detail = gatelib.permissions_harness()
        if not ok:
            reporter.fail("permissions", detail, gatelib.blocker_instruction("permission-install", root))
        elif permission_mode and permission_mode not in gatelib.SAFE_PERMISSION_MODES:
            reporter.fail("permissions", "permission mode is %s" % permission_mode, gatelib.blocker_instruction("permission-select", root))
        else:
            reporter.pass_("permissions", permission_mode or gatelib.PERMISSIONS_HARNESS_PROFILE)
        trusted, detail = gatelib.project_trust_status(root)
        if trusted:
            reporter.pass_("project-trust", root)
        else:
            reporter.fail("project-trust", detail, gatelib.blocker_instruction("trust", root))
    else:
        reporter.pass_("permissions", "claude project policy")
        reporter.pass_("project-trust", "claude hook invocation")
    ok, detail, _ = gatelib.hook_definition_status(root, "project", host)
    if ok:
        reporter.pass_("authorization", "project hook definition")
    else:
        reporter.fail("authorization", detail, gatelib.blocker_instruction("hooks", root))


def shared_state(root, reporter, require_api=False, require_source=False):
    if not (require_api or require_source):
        reporter.skip("cache", "optional-api-source")
        reporter.skip("corpus", "optional-api-source")
    else:
        corpus_ok, errors = precheck.corpus_preconditions()
        if not corpus_ok:
            record = errors[0].split("|", 2) if errors else []
            reporter.fail("corpus", record[1] if len(record) > 1 else "preparation failed", record[2] if len(record) > 2 else "Repair the corpus.")
            return False
        reporter.pass_("cache", gatelib.CACHE)
        reporter.pass_("corpus", "fresh")
    if not require_source:
        reporter.skip("api-globals", "optional-source")
    else:
        errors = precheck.api_globals_preconditions(root)
        if errors:
            record = errors[0].split("|", 2)
            reporter.fail("api-globals", record[1], record[2])
            return False
        reporter.pass_("api-globals", "generated")
    if not require_source:
        reporter.skip("type-cache", "optional-source")
    else:
        try:
            status, _ = ensure_type_cache(root)
            reporter.pass_("type-cache", status)
        except Exception as error:
            reporter.fail("type-cache", error, "Rebuild the project type cache, then retry.")
            return False
    return True


def gate_sources(reporter):
    bad = []
    for name in precheck.GATE_SCRIPTS:
        path = os.path.join(GATES, name)
        try:
            with open(path, encoding="utf-8") as handle:
                source = handle.read()
            if not source:
                raise ValueError("empty")
            compile(source, path, "exec")
        except Exception as error:
            bad.append("%s: %s" % (name, error))
    if bad:
        reporter.fail("gate-sources", bad[0], "Repair the harness gate source, then retry.")
        return False
    reporter.pass_("gate-sources", "%d scripts" % len(precheck.GATE_SCRIPTS))
    return True


def static_checks(root, lute, reporter, require_api=False):
    if lute:
        deny = run([lute, "run", os.path.join(TOOLS, "deny_scan", "check_table.luau")])
    else:
        deny = None
    if deny is None:
        reporter.skip("deny-table", "lute")
    elif deny.returncode == 0 and deny.stdout.startswith("ok "):
        reporter.pass_("deny-table", deny.stdout.strip())
    else:
        reporter.fail("deny-table", deny.stderr or deny.stdout or "invalid", "Repair deny_table.luau, then retry.")
    if not require_api:
        reporter.skip("api-overlay", "optional-api")
    else:
        overlay = run([sys.executable, os.path.join(TOOLS, "api_dump", "api_dump.py"), "--check-overlay"], timeout=300)
        if overlay.returncode == 0:
            reporter.pass_("api-overlay", "current")
        else:
            reporter.fail("api-overlay", overlay.stdout or overlay.stderr or "invalid", "Repair the API overlay, then retry.")
    misplaced = []
    for path in (
        os.path.expanduser("~/.claude/skills/roblox-writer"),
        os.path.expanduser("~/.agents/skills/roblox-writer"),
        os.path.join(root, ".claude", "skills", "roblox-new-game"),
        os.path.join(root, ".agents", "skills", "roblox-new-game"),
    ):
        if os.path.exists(path):
            misplaced.append(path)
    if misplaced:
        reporter.fail("skill-scope", misplaced[0], "Relink the project skills, then retry.")
    else:
        reporter.pass_("skill-scope", "current")
    dead = []
    for base in (
        os.path.join(HARNESS, "packages"),
        os.path.join(root, ".claude", "agents"),
        os.path.join(root, ".claude", "skills"),
        os.path.join(root, ".codex", "agents"),
        os.path.join(root, ".agents", "skills"),
    ):
        if not os.path.isdir(base):
            continue
        for directory, names, files in os.walk(base):
            for name in names + files:
                path = os.path.join(directory, name)
                if os.path.islink(path) and not os.path.exists(path):
                    dead.append(path)
    if dead:
        reporter.fail("managed-links", dead[0], "Relink the project, then retry.")
    else:
        reporter.pass_("managed-links", "current")


def settle_git_state(root, allow_repair=True):
    """Apply the one permitted repair and return only settled Git evidence."""
    state, detail = gatelib.gate6_probe_state(root)
    disposition = gatelib.gate6_disposition(state)
    if disposition == "repair" and allow_repair:
        result = run(
            [
                sys.executable,
                os.path.join(TOOLS, "git_sync", "git_sync.py"),
                "repair",
                "--root",
                os.path.realpath(root),
            ],
            timeout=gatelib.GIT_REPAIR_TIMEOUT,
            cwd=root,
        )
        if result.returncode == 0:
            state, detail = gatelib.gate6_probe_state(root)
        else:
            detail = result.stderr or result.stdout or detail or "git_sync repair failed"
    return state, detail


def report_git_state(root, reporter, state, detail):
    disposition = gatelib.gate6_disposition(state)
    if disposition == "ok":
        reporter.pass_("git-fetch", "origin current")
        return True
    if disposition == "advisory":
        reporter.advisory("git-fetch", "%s: %s" % (state, detail))
        return True
    reporter.fail("git-fetch", "%s: %s" % (state, detail), gatelib.gate6_instruction(root, state, detail))
    return False


def git_checks(root, reporter, allow_repair=True):
    return report_git_state(root, reporter, *settle_git_state(root, allow_repair=allow_repair))


def argon_projects(root, argon, reporter):
    projects = []
    for directory, names, files in os.walk(root):
        names[:] = [name for name in names if name != ".git"]
        projects.extend(os.path.join(directory, name) for name in files if name.endswith(".project.json"))
    if not projects:
        reporter.fail("argon-projects", "no .project.json files", "Restore the project files, then retry.")
        return False
    with tempfile.TemporaryDirectory(prefix="project_gate_argon_") as temporary:
        for index, project in enumerate(sorted(projects)):
            output = os.path.join(temporary, "%d.json" % index)
            result = run([argon, "sourcemap", project, "-o", output], timeout=120)
            if result.returncode != 0 or not os.path.isfile(output):
                reporter.fail("argon-projects", "%s: %s" % (os.path.relpath(project, root), result.stderr or result.stdout), "Repair the Argon project, then retry.")
                return False
    reporter.pass_("argon-projects", "%d project files" % len(projects))
    return True


def studio_checks(root, mcp, reporter, allow_project_writes=True):
    try:
        with StudioRPC(mcp, timeout=30) as rpc:
            available = set(rpc.tools_list())
            required = {"execute_luau", "list_roblox_studios"}
            missing = sorted(required - available)
            if missing:
                reporter.fail("studio-mcp", "missing tools: %s" % ", ".join(missing), gatelib.blocker_instruction("studio-restart", root))
                return False
            reporter.pass_("studio-mcp", "stdio initialized")
            claude_md = os.path.join(root, "CLAUDE.md")
            mapping = place_map.read_places_block(claude_md)
            children_root = os.path.join(root, "places")
            children = sorted(name for name in os.listdir(children_root) if os.path.isdir(os.path.join(children_root, name))) if os.path.isdir(children_root) else []
            rpc.select_studio(place_map.positive_place_ids(mapping))
            reporter.pass_("studio", "project place connected")
            response = rpc.call("execute_luau", {"code": place_map.UNIVERSE_LUAU, "datamodel_type": "Edit"})
            universe = place_map.parse_universe(response)
            new_mapping, problems, mapped = place_map.reconcile_places(children, mapping, universe)
            if problems:
                reporter.fail("place-map", problems[0], precheck.place_map_instruction(problems[0].split("|", 2)[1], problems[0].split("|", 2)[2], root))
                return False
            if mapped and not allow_project_writes:
                reporter.fail(
                    "place-map",
                    "selected project mapping requires an update",
                    "Open a task in the selected project and update its place map.",
                )
                return False
            if mapped:
                place_map.write_places_block(claude_md, new_mapping)
                agents_md = os.path.join(root, "AGENTS.md")
                if os.path.exists(agents_md):
                    place_map.write_places_block(agents_md, new_mapping)
            reporter.pass_("place-map", "%d places" % len(new_mapping))
            return True
    except EnvError as error:
        reporter.fail("studio-mcp", error.cause, error.remedy)
    except Exception as error:
        reporter.fail("studio-mcp", "%s: %s" % (type(error).__name__, error), gatelib.blocker_instruction("studio-restart", root))
    return False


def check(
    project_root,
    host="codex",
    permission_mode="",
    require_studio=False,
    require_api=False,
    require_source=False,
    allow_project_writes=True,
):
    initial = Reporter()
    root = validate_root(project_root, initial)
    if root is None:
        for name in ("generated-integration", "authorization", "shared-state", "toolchain", "git-fetch", "argon-projects", "studio-mcp"):
            initial.skip(name, "project-root")
        return initial.emit(os.path.realpath(project_root or "."))

    if root == os.path.realpath(HARNESS):
        harness_checks(initial)
        return initial.emit(root)

    # Git repair can replace tracked files and restore local work.  It must
    # therefore settle before any project evidence is retained.  Validate the
    # root again and collect every reported check from the repaired result.
    git_probe = Reporter()
    preflight_git = executable_check(git_probe, "git", "git")
    settled_git = settle_git_state(root, allow_repair=allow_project_writes) if preflight_git else None

    reporter = Reporter()
    root = validate_root(project_root, reporter)
    if root is None:
        for name in ("generated-integration", "authorization", "shared-state", "toolchain", "git-fetch", "argon-projects", "studio-mcp"):
            reporter.skip(name, "project-root-after-git")
        return reporter.emit(os.path.realpath(project_root or "."))

    git = executable_check(reporter, "git", "git")
    if git and settled_git is not None:
        report_git_state(root, reporter, *settled_git)
    else:
        reporter.skip("git-fetch", "git")

    generated_integration(root, host, reporter, allow_project_writes=allow_project_writes)
    if host == "codex" and require_studio:
        studio_tool_approval(root, reporter)
    elif host == "codex":
        reporter.skip("studio-tool-approval", "optional-studio")
    authorization_checks(root, host, permission_mode, reporter)
    shared_state(root, reporter, require_api=require_api, require_source=require_source)
    gate_sources(reporter)

    if require_source:
        argon = executable_check(reporter, "argon", "argon")
        ensure_toolchain(reporter)
        lute = executable_check(reporter, "lute", gatelib.LUTE)
        executable_check(reporter, "luau-lsp", gatelib.LUAU_LSP if os.path.exists(gatelib.LUAU_LSP) else "luau-lsp")
    else:
        reporter.skip("argon", "optional-source")
        reporter.skip("toolchain", "optional-source")
        reporter.skip("lute", "optional-source")
        reporter.skip("luau-lsp", "optional-source")
        argon = None
        lute = None
    mcp_path = find_studio_mcp() if require_studio else None
    if require_studio and mcp_path:
        reporter.pass_("studio-mcp-executable", mcp_path)
    elif require_studio:
        reporter.fail("studio-mcp-executable", "executable absent", gatelib.blocker_instruction("studio-install", root))
    else:
        reporter.skip("studio-mcp-executable", "optional-studio")

    static_checks(root, lute, reporter, require_api=require_api)
    if argon:
        argon_projects(root, argon, reporter)
    else:
        reporter.skip("argon-projects", "argon" if require_source else "optional-source")
    if require_studio and mcp_path:
        studio_checks(root, mcp_path, reporter, allow_project_writes=allow_project_writes)
    else:
        dependency = "studio-mcp-executable" if require_studio else "optional-studio"
        reporter.skip("studio", dependency)
        reporter.skip("studio-mcp", dependency)
        reporter.skip("place-map", dependency)
    return reporter.emit(root)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="project_gate")
    parser.add_argument("command", choices=("check",), nargs="?", default="check")
    parser.add_argument("--project-root", default=HARNESS)
    parser.add_argument("--host", choices=("codex", "claude"), default="codex")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--permission-mode", default="")
    parser.add_argument("--require-studio", action="store_true")
    parser.add_argument("--require-api", action="store_true")
    parser.add_argument("--require-source", action="store_true")
    parser.add_argument("--read-only-project", action="store_true")
    args = parser.parse_args(argv)
    _ = args.command, args.session_id
    try:
        return check(
            args.project_root,
            args.host,
            args.permission_mode,
            args.require_studio,
            args.require_api,
            args.require_source,
            not args.read_only_project,
        )
    except Exception as error:
        print("PROJECT_GATE|ERROR|%s|%s" % (type(error).__name__, Reporter.field(error)))
        return 3


if __name__ == "__main__":
    sys.exit(main())
