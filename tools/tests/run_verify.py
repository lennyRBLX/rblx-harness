#!/usr/bin/env python3
"""Focused verification for the lean rblx-harness surface."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY = sys.executable
SCAFFOLD = os.path.join(ROOT, "shared", "skills", "rblx-new-game", "scripts", "scaffold.py")
DEPENDENCY = os.path.join(ROOT, "shared", "skills", "rblx-new-game", "scripts", "dependency.py")
PROJECT_GATE = os.path.join(ROOT, "tools", "project_gate", "project_gate.py")
AGENT_GATE = os.path.join(ROOT, "shared", "gates", "agent_gate.py")
TOOL_GATE = os.path.join(ROOT, "shared", "gates", "tool_gate.py")
PERMISSIONS = os.path.join(ROOT, "openai", "setup", "permissions_harness.py")
SUBMODULE_NAME = "rblx-harness"
SUBMODULE_URL = "https://github.com/lennyRBLX/rblx-harness.git"


def run(args, cwd=None, input_text=None, env=None):
    return subprocess.run(
        args,
        cwd=cwd or ROOT,
        input=input_text,
        capture_output=True,
        text=True,
        env=env,
    )


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def harness_fixture(directory):
    source = os.path.join(directory, "harness-origin")
    selected = (
        ".gitignore",
        "setup_project.py",
        "openai",
        "packages",
        "shared/CORE.md",
        "shared/HANDOFF.md",
        "shared/gates",
        "shared/skills",
        "templates",
        "tools/api_dump",
        "tools/create_boilerplate",
        "tools/data_write",
        "tools/frame_census",
        "tools/style_assess",
        "tools/type_write",
    )
    ignored = shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc")
    for relative in selected:
        current = os.path.join(ROOT, *relative.split("/"))
        destination = os.path.join(source, *relative.split("/"))
        if os.path.isdir(current):
            shutil.copytree(current, destination, symlinks=True, ignore=ignored)
        else:
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            shutil.copy2(current, destination)
    run(["git", "init"], cwd=source)
    run(["git", "config", "user.name", "verify"], cwd=source)
    run(["git", "config", "user.email", "verify@example.invalid"], cwd=source)
    run(["git", "add", "."], cwd=source)
    committed = run(["git", "commit", "-m", "fixture"], cwd=source)
    require(committed.returncode == 0, committed.stdout + committed.stderr)
    return source


def submodule_test_environment(source):
    environment = dict(os.environ)
    environment.update(
        GIT_CONFIG_COUNT="2",
        GIT_CONFIG_KEY_0="url.%s.insteadOf" % Path(source).resolve().as_uri(),
        GIT_CONFIG_VALUE_0=SUBMODULE_URL,
        GIT_CONFIG_KEY_1="protocol.file.allow",
        GIT_CONFIG_VALUE_1="always",
    )
    return environment


def require_submodule(root):
    require(os.path.isfile(os.path.join(root, ".gitmodules")), "submodule registration is absent")
    require(not os.path.islink(os.path.join(root, SUBMODULE_NAME)), "submodule path is a symlink")
    require(not os.path.lexists(os.path.join(root, "." + SUBMODULE_NAME)), "legacy hidden dependency remains")
    path = run(
        ["git", "config", "-f", ".gitmodules", "--get", "submodule.rblx-harness.path"],
        cwd=root,
    )
    require(path.returncode == 0 and path.stdout.strip() == SUBMODULE_NAME, path.stdout + path.stderr)
    url = run(
        ["git", "config", "-f", ".gitmodules", "--get", "submodule.rblx-harness.url"],
        cwd=root,
    )
    require(url.returncode == 0 and url.stdout.strip() == SUBMODULE_URL, url.stdout + url.stderr)
    modules_index = run(["git", "ls-files", "--stage", "--", ".gitmodules"], cwd=root)
    require(modules_index.returncode == 0 and modules_index.stdout.startswith("100644 "), modules_index.stdout + modules_index.stderr)
    index = run(["git", "ls-files", "--stage", "--", SUBMODULE_NAME], cwd=root)
    require(index.returncode == 0 and index.stdout.startswith("160000 "), index.stdout + index.stderr)
    status = run(["git", "submodule", "status", "--", SUBMODULE_NAME], cwd=root)
    require(status.returncode == 0 and status.stdout.startswith(" "), status.stdout + status.stderr)


def require_ignored_local_state(root):
    paths = {
        ".agents": ".agents/.verify-probe",
        ".codex": ".codex/.verify-probe",
        ".serena": ".serena/.verify-probe",
        ".roblox": ".roblox",
        ".rblx-new-game.json": ".rblx-new-game.json",
    }
    for relative, probe in paths.items():
        ignored = run(["git", "check-ignore", "--no-index", "--quiet", "--", probe], cwd=root)
        require(ignored.returncode == 0, "%s is not ignored" % relative)
        tracked = run(["git", "ls-files", "--", relative], cwd=root)
        require(tracked.returncode == 0 and not tracked.stdout.strip(), "%s is tracked" % relative)


def case(name):
    def decorator(function):
        CASES.append((name, function))
        return function
    return decorator


CASES = []


@case("repository surface is four skills, four agents, and Codex only")
def _():
    skills = sorted(
        name for name in os.listdir(os.path.join(ROOT, "shared", "skills"))
        if os.path.isfile(os.path.join(ROOT, "shared", "skills", name, "SKILL.md"))
    )
    require(skills == ["rblx-debug", "rblx-new-game", "rblx-optimize", "rblx-writer"], skills)
    agents = sorted(
        os.path.splitext(name)[0]
        for name in os.listdir(os.path.join(ROOT, "openai", "agents"))
        if name.endswith(".toml")
    )
    require(agents == ["debugger", "optimizer", "researcher", "reviewer"], agents)
    require(not os.path.exists(os.path.join(ROOT, "claude")), "claude directory remains")
    require(not os.path.exists(os.path.join(ROOT, ".claude")), ".claude directory remains")
    require(not os.path.exists(os.path.join(ROOT, "setup_windows.bat")), "Windows batch remains")
    require(os.path.isfile(os.path.join(ROOT, "setup_project.py")), "Python setup is absent")
    require(os.path.isfile(os.path.join(ROOT, "shared", "HANDOFF.md")), "shared handoff is absent")
    require(os.path.isfile(os.path.join(ROOT, "templates", "README.md")), "project README template is absent")
    require(not os.path.exists(os.path.join(ROOT, "templates", "HANDOFF.md")), "project handoff template remains")
    tracked_local = run(["git", "ls-files", "--", ".agents", ".codex", ".serena", ".roblox"])
    require(tracked_local.returncode == 0 and not tracked_local.stdout.strip(), tracked_local.stdout)
    for skill in skills:
        text = open(os.path.join(ROOT, "shared", "skills", skill, "SKILL.md"), encoding="utf-8").read()
        require(text.startswith("---\nname: %s\n" % skill), "%s frontmatter" % skill)
        require(os.path.isfile(os.path.join(ROOT, "shared", "skills", skill, "agents", "openai.yaml")), skill)


@case("hooks support only agents, tools, and rules")
def _():
    for relative in ("openai/hooks/project.json",):
        document = json.load(open(os.path.join(ROOT, relative), encoding="utf-8"))
        require(set(document["hooks"]) == {"PreToolUse", "SubagentStart", "SubagentStop"}, relative)
        serialized = json.dumps(document)
        require("SessionStart" not in serialized and "UserPromptSubmit" not in serialized, relative)
    contract = json.load(open(os.path.join(ROOT, "openai", "hooks", "contract.json"), encoding="utf-8"))
    require(contract["session_authorization"] is False, contract)
    require(contract["restart_required"] is False, contract)


@case("harness setup rebuilds ignored Codex support and all source skills")
def _():
    with tempfile.TemporaryDirectory() as directory:
        root = harness_fixture(directory)
        result = run([PY, os.path.join(root, "setup_project.py"), "--harness"], cwd=root)
        require(result.returncode == 0, result.stdout + result.stderr)
        hooks = open(os.path.join(root, ".codex", "hooks.json"), encoding="utf-8").read()
        require("/rblx-harness/openai/" not in hooks, hooks)
        require("/openai/hooks/adapter.py" in hooks, hooks)
        for skill in ("rblx-debug", "rblx-new-game", "rblx-optimize", "rblx-writer"):
            require(os.path.islink(os.path.join(root, ".agents", "skills", skill)), skill)
        require(not os.path.exists(os.path.join(root, ".roblox")), "harness setup created .roblox")
        require(not os.path.exists(os.path.join(root, ".serena")), "harness setup created .serena")
        status = run(["git", "status", "--porcelain"], cwd=root)
        require(status.returncode == 0 and not status.stdout.strip(), status.stdout + status.stderr)


@case("Roblox permission profile is optional and does not become the default")
def _():
    with tempfile.TemporaryDirectory() as directory:
        environment = dict(os.environ, CODEX_HOME=os.path.join(directory, "codex"))
        status = run([PY, PERMISSIONS], env=environment)
        require(status.returncode == 0 and "ABSENT" in status.stdout, status.stdout + status.stderr)
        installed = run([PY, PERMISSIONS, "--install"], env=environment)
        require(installed.returncode == 0, installed.stdout + installed.stderr)
        config = open(os.path.join(environment["CODEX_HOME"], "config.toml"), encoding="utf-8").read()
        require("[permissions.Roblox]" in config, config)
        require("default_permissions" not in config, config)


@case("Codex config merge preserves custom tables")
def _():
    sys.path.insert(0, os.path.join(ROOT, "shared", "gates"))
    import gatelib

    existing = "[custom]\nvalue = 7\n"
    canonical = open(os.path.join(ROOT, "openai", "config", "project.toml"), encoding="utf-8").read()
    merged = gatelib.merge_project_codex_config(existing, canonical)
    import tomllib

    parsed = tomllib.loads(merged)
    require(parsed["custom"]["value"] == 7, merged)
    require(parsed["features"]["multi_agent"] is True, merged)
    repeated = gatelib.merge_project_codex_config(merged, canonical)
    require(repeated == merged, "Codex config merge is not byte-stable")


@case("new-game approval installs the fixed GitHub submodule into an unborn repository")
def _():
    with tempfile.TemporaryDirectory() as directory:
        source = os.path.join(directory, "source")
        os.makedirs(source)
        write(os.path.join(source, "setup_project.py"), "# fixture\n")
        write(os.path.join(source, "shared", "CORE.md"), "# fixture\n")
        write(os.path.join(source, "shared", "skills", "rblx-new-game", "SKILL.md"), "# fixture\n")
        run(["git", "init"], cwd=source)
        run(["git", "config", "user.name", "verify"], cwd=source)
        run(["git", "config", "user.email", "verify@example.invalid"], cwd=source)
        run(["git", "add", "."], cwd=source)
        committed = run(["git", "commit", "-m", "fixture"], cwd=source)
        require(committed.returncode == 0, committed.stdout + committed.stderr)

        copied = os.path.join(directory, "user", ".agents", "skills", "rblx-new-game", "scripts", "dependency.py")
        os.makedirs(os.path.dirname(copied), exist_ok=True)
        shutil.copy2(DEPENDENCY, copied)
        project = os.path.join(directory, "project")
        os.makedirs(project)
        environment = submodule_test_environment(source)
        pending = run([PY, copied, "setup", "--root", project], env=environment)
        require(pending.returncode == 3 and "CONSENT_REQUIRED" in pending.stdout, pending.stdout + pending.stderr)
        require(not os.path.exists(os.path.join(project, ".git")), "Git repository initialized before approval")
        require(not os.path.exists(os.path.join(project, ".gitmodules")), "submodule changed project before approval")
        require(not os.path.exists(os.path.join(project, SUBMODULE_NAME)), "submodule installed before approval")
        installed = run([PY, copied, "setup", "--root", project, "--yes"], env=environment)
        require(installed.returncode == 0, installed.stdout + installed.stderr)
        require_submodule(project)
        require(os.path.isfile(os.path.join(project, ".roblox")), "local marker is absent")
        require_ignored_local_state(project)
        require(os.path.isfile(os.path.join(project, SUBMODULE_NAME, "setup_project.py")), "submodule is absent")
        repeated = run([PY, copied, "setup", "--root", project, "--yes"], env=environment)
        require(repeated.returncode == 0 and "mode=submodule-ready" in repeated.stdout, repeated.stdout + repeated.stderr)
        status = run([PY, copied, "status", "--root", project])
        require(status.returncode == 0 and "READY|submodule" in status.stdout, status.stdout + status.stderr)
        deinitialized = run(["git", "submodule", "deinit", "--force", "--", SUBMODULE_NAME], cwd=project)
        require(deinitialized.returncode == 0, deinitialized.stdout + deinitialized.stderr)
        initialized = run([PY, copied, "init", "--root", project], env=environment)
        require(initialized.returncode == 0 and "READY|submodule" in initialized.stdout, initialized.stdout + initialized.stderr)
        require_submodule(project)


@case("inspection identifies existing scoped modules without writing")
def _():
    with tempfile.TemporaryDirectory() as directory:
        root = os.path.join(directory, "game")
        os.makedirs(root)
        run(["git", "init"], cwd=root)
        write(os.path.join(root, "legacy", "ServerScriptService", "Services", "Combat.luau"), "return { Existing = true }\n")
        write(
            os.path.join(root, "places", "Match", "src", "StarterPlayer", "StarterPlayerScripts", "Controllers", "Movement.luau"),
            "return { Existing = true }\n",
        )
        write(os.path.join(root, "Match.project.json"), "{}\n")
        result = run([PY, SCAFFOLD, "inspect", "--root", root])
        require(result.returncode == 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        require(report["project"] == "existing", report)
        require(report["git"] is True, report)
        require(report["places"] == ["Match"], report)
        require(any(item["name"] == "Combat" and item["scope"] == "shared" for item in report["services"]), report)
        require(any(item["name"] == "Movement" and item["scope"] == "Match" for item in report["controllers"]), report)
        require("PlayerData" in report["harness_assets"]["services"], report)
        require("Gui" in report["harness_assets"]["controllers"], report)
        require(not os.path.exists(os.path.join(root, ".rblx-new-game.json")), "inspection wrote state")


@case("scaffold requires bare service and controller names")
def _():
    with tempfile.TemporaryDirectory() as root:
        places = run([PY, SCAFFOLD, "answer", "places", "Lobby", "--root", root])
        require(places.returncode == 0, places.stdout + places.stderr)
        service = run([PY, SCAFFOLD, "answer", "services", "shared: InventoryService", "--root", root])
        require(service.returncode == 2 and "use Inventory instead of InventoryService" in service.stderr, service.stdout + service.stderr)
        controller = run([PY, SCAFFOLD, "answer", "controllers", "shared: CameraController", "--root", root])
        require(controller.returncode == 2 and "use Camera instead of CameraController" in controller.stderr, controller.stdout + controller.stderr)


def answer_all(root, assets="Accept all"):
    answers = (
        ("gameplay", "Players win matches for loot boxes"),
        ("places", "Lobby, Match, Staging"),
        ("services", "shared: Match, Matchmaking, Combat, Movement, Teams, Inventory, Skins, Rewards"),
        ("controllers", "shared: Combat, Movement, Teams, Inventory, Skins"),
        ("assets", assets),
        ("harness", "Yes"),
    )
    for field, value in answers:
        result = run([PY, SCAFFOLD, "answer", field, value, "--root", root])
        require(result.returncode == 0, result.stdout + result.stderr)


def scaffold_project(root, assets="Accept all", source=""):
    answer_all(root, assets)
    selected = source or harness_fixture(os.path.dirname(root))
    dependency = run(
        [PY, DEPENDENCY, "setup", "--root", root, "--yes"],
        env=submodule_test_environment(selected),
    )
    require(dependency.returncode == 0, dependency.stdout + dependency.stderr)
    require_submodule(root)
    emitted = run([PY, SCAFFOLD, "emit", "--root", root], cwd=root)
    require(emitted.returncode == 0, emitted.stdout + emitted.stderr)
    return emitted


@case("full scaffold links assets and preserves existing module bytes")
def _():
    with tempfile.TemporaryDirectory() as directory:
        root = os.path.join(directory, "game")
        os.makedirs(root)
        run(["git", "init"], cwd=root)
        existing_service = "return { ExistingCombat = true }\n"
        existing_controller = "return { ExistingMovement = true }\n"
        write(os.path.join(root, "legacy", "ServerScriptService", "Services", "Combat.luau"), existing_service)
        write(
            os.path.join(root, "places", "Match", "src", "StarterPlayer", "StarterPlayerScripts", "Controllers", "Movement.luau"),
            existing_controller,
        )
        emitted = scaffold_project(root)
        require("EMITTED|game" in emitted.stdout, emitted.stdout)
        require_submodule(root)
        require(os.path.isfile(os.path.join(root, "manifest.json")), "manifest.json is absent")
        require(not os.path.exists(os.path.join(root, "info.json")), "info.json was emitted")
        combat = os.path.join(root, "shared", "src", "ServerScriptService", "Services", "Combat.luau")
        movement = os.path.join(root, "places", "Match", "src", "StarterPlayer", "StarterPlayerScripts", "Controllers", "Movement.luau")
        require(open(combat, encoding="utf-8").read() == existing_service, "existing service was replaced")
        require(open(movement, encoding="utf-8").read() == existing_controller, "existing controller was replaced")
        require(os.path.islink(os.path.join(root, "shared", "src", "ReplicatedStorage", "Packages", "Signal.luau")), "package link absent")
        require(os.path.islink(os.path.join(root, "shared", "src", "ServerScriptService", "Services", "Payments.luau")), "service link absent")
        effects = os.path.join(root, "shared", "src", "StarterPlayer", "StarterPlayerScripts", "Controllers", "Effects", "init.luau")
        require(os.path.islink(effects), "controller link absent")
        require(os.path.isdir(os.path.join(root, "plugins")), "plugins folder absent")
        require(not os.path.lexists(os.path.join(root, "plugin")), "legacy plugin folder remains")
        require(not os.path.exists(os.path.join(root, ".claude")), "Claude support emitted")
        require(not os.path.exists(os.path.join(root, "CLAUDE.md")), "CLAUDE.md emitted")
        require(not os.path.exists(os.path.join(root, "HANDOFF.md")), "project handoff was emitted")
        readme_path = os.path.join(root, "README.md")
        readme = open(readme_path, encoding="utf-8").read()
        require("Players win matches for loot boxes" in readme, readme)
        require("git submodule update --init --recursive" in readme, readme)
        require("python3 rblx-harness/setup_project.py --project . --from-state" in readme, readme)
        require(len(readme.splitlines()) <= 10, "generated README is not minimal")
        require(sorted(os.path.splitext(name)[0] for name in os.listdir(os.path.join(root, ".codex", "agents"))) == ["debugger", "optimizer", "researcher", "reviewer"], "agent set")
        for skill in ("rblx-writer", "rblx-debug", "rblx-optimize"):
            require(os.path.islink(os.path.join(root, ".agents", "skills", skill)), "%s is not linked" % skill)
        require(not os.path.lexists(os.path.join(root, ".agents", "skills", "rblx-new-game")), "rblx-new-game was installed in project")
        require_ignored_local_state(root)
        inspected = run([PY, SCAFFOLD, "inspect", "--root", root])
        require(inspected.returncode == 0, inspected.stdout + inspected.stderr)
        report = json.loads(inspected.stdout)
        require(
            {item["name"] for item in report["services"]}
            == {"Match", "Matchmaking", "Combat", "Movement", "Teams", "Inventory", "Skins", "Rewards"},
            report["services"],
        )
        require(
            {item["name"] for item in report["controllers"]}
            == {"Combat", "Movement", "Teams", "Inventory", "Skins"},
            report["controllers"],
        )
        validated = run([PY, PROJECT_GATE, "--project-root", root])
        require(validated.returncode == 0, validated.stdout + validated.stderr)

        custom_readme = "# Existing documentation\n"
        write(readme_path, custom_readme)
        shutil.rmtree(os.path.join(root, ".agents"))
        shutil.rmtree(os.path.join(root, ".codex"))
        os.unlink(os.path.join(root, ".roblox"))
        os.makedirs(os.path.join(root, ".agents", "skills", "rblx-new-game"))
        write(os.path.join(root, ".agents", "skills", "rblx-new-game", "stale"), "stale\n")
        restored = run(
            [PY, os.path.join(root, SUBMODULE_NAME, "setup_project.py"), "--project", root, "--from-state"],
            cwd=root,
        )
        require(restored.returncode == 0, restored.stdout + restored.stderr)
        require(os.path.isfile(os.path.join(root, ".roblox")), "setup did not recreate .roblox")
        require(os.path.isfile(os.path.join(root, ".codex", "hooks.json")), "setup did not recreate .codex")
        require(not os.path.lexists(os.path.join(root, ".agents", "skills", "rblx-new-game")), "setup retained rblx-new-game")
        require(open(readme_path, encoding="utf-8").read() == custom_readme, "setup replaced an existing README")
        os.makedirs(os.path.join(root, ".serena"))
        write(os.path.join(root, ".serena", "project.yml"), "project_name: game\n")
        require_ignored_local_state(root)
        revalidated = run([PY, PROJECT_GATE, "--project-root", root])
        require(revalidated.returncode == 0, revalidated.stdout + revalidated.stderr)


@case("plugins directory is optional")
def _():
    with tempfile.TemporaryDirectory() as directory:
        root = os.path.join(directory, "game")
        os.makedirs(root)
        run(["git", "init"], cwd=root)
        scaffold_project(root, assets="none")
        require(not os.path.exists(os.path.join(root, "plugins")), "plugins was created")
        validated = run([PY, PROJECT_GATE, "--project-root", root])
        require(validated.returncode == 0, validated.stdout + validated.stderr)


@case("legacy plugin support migrates when the harness is declined")
def _():
    with tempfile.TemporaryDirectory() as directory:
        root = os.path.join(directory, "game")
        os.makedirs(os.path.join(root, "plugin"))
        answers = (
            ("gameplay", "Players build and publish a plugin"),
            ("places", "Workshop"),
            ("services", "none"),
            ("controllers", "none"),
            ("assets", "none"),
            ("harness", "No"),
        )
        for field, value in answers:
            result = run([PY, SCAFFOLD, "answer", field, value, "--root", root])
            require(result.returncode == 0, result.stdout + result.stderr)
        emitted = run([PY, SCAFFOLD, "emit", "--root", root])
        require(emitted.returncode == 0, emitted.stdout + emitted.stderr)
        require(os.path.isdir(os.path.join(root, "plugins")), "plugins folder was not migrated")
        require(not os.path.lexists(os.path.join(root, "plugin")), "legacy plugin folder remains")
        require(not os.path.exists(os.path.join(root, "HANDOFF.md")), "project handoff was emitted")
        require(not os.path.exists(os.path.join(root, "README.md")), "README was emitted without harness use")
        require(not os.path.exists(os.path.join(root, SUBMODULE_NAME)), "harness was installed")


@case("agent gate allows only four compact role returns")
def _():
    start_payload = json.dumps({"agent_type": "researcher", "hook_event_name": "SubagentStart"})
    started = run([PY, AGENT_GATE, "--event", "SubagentStart"], input_text=start_payload)
    require(started.returncode == 0 and "additionalContext" in started.stdout, started.stdout + started.stderr)
    rejected = run(
        [PY, AGENT_GATE, "--event", "SubagentStart"],
        input_text=json.dumps({"agent_type": "maintainer"}),
    )
    require(rejected.returncode == 2, rejected.stdout + rejected.stderr)
    stopped = run(
        [PY, AGENT_GATE, "--event", "SubagentStop"],
        input_text=json.dumps({"agent_type": "reviewer", "last_assistant_message": "reviewer: CLEAN"}),
    )
    require(stopped.returncode == 0, stopped.stdout + stopped.stderr)


@case("tool gate enforces agent data tools without gating primary sessions")
def _():
    direct = {
        "agent_type": "debugger",
        "tool_name": "apply_patch",
        "tool_input": "*** Update File: shared/src/ReplicatedStorage/Data/Player.luau",
    }
    blocked = run([PY, TOOL_GATE, "--event", "PreToolUse"], input_text=json.dumps(direct))
    require(blocked.returncode == 2 and "TOOL1" in blocked.stderr, blocked.stdout + blocked.stderr)
    primary = dict(direct)
    primary.pop("agent_type")
    allowed = run([PY, TOOL_GATE, "--event", "PreToolUse"], input_text=json.dumps(primary))
    require(allowed.returncode == 0, allowed.stdout + allowed.stderr)
    approved = {
        "agent_type": "debugger",
        "tool_name": "exec_command",
        "tool_input": {"cmd": "python3 rblx-harness/tools/type_write/type_write.py --request '{}'"},
    }
    result = run([PY, TOOL_GATE, "--event", "PreToolUse"], input_text=json.dumps(approved))
    require(result.returncode == 0, result.stdout + result.stderr)
    shell_write = {
        "agent_type": "debugger",
        "tool_name": "exec_command",
        "tool_input": {"cmd": "sed -i '' shared/src/ReplicatedStorage/Data/Player.luau"},
    }
    result = run([PY, TOOL_GATE, "--event", "PreToolUse"], input_text=json.dumps(shell_write))
    require(result.returncode == 2 and "TOOL1" in result.stderr, result.stdout + result.stderr)
    hidden_shell_write = {
        "agent_type": "debugger",
        "tool_name": "exec_command",
        "tool_input": {"cmd": "python3 -c 'open(\"shared/src/ReplicatedStorage/Data/Player.luau\", \"w\")'"},
    }
    result = run([PY, TOOL_GATE, "--event", "PreToolUse"], input_text=json.dumps(hidden_shell_write))
    require(result.returncode == 2 and "TOOL1" in result.stderr, result.stdout + result.stderr)
    data_read = {
        "agent_type": "debugger",
        "tool_name": "exec_command",
        "tool_input": {"cmd": "sed -n '1,80p' shared/src/ReplicatedStorage/Data/Player.luau"},
    }
    result = run([PY, TOOL_GATE, "--event", "PreToolUse"], input_text=json.dumps(data_read))
    require(result.returncode == 0, result.stdout + result.stderr)
    nested = {
        "agent_type": "debugger",
        "tool_name": "spawn_agent",
        "tool_input": {"agent_type": "researcher"},
    }
    result = run([PY, TOOL_GATE, "--event", "PreToolUse"], input_text=json.dumps(nested))
    require(result.returncode == 2 and "AGENT1" in result.stderr, result.stdout + result.stderr)
    invalid_dispatch = {
        "tool_name": "Agent",
        "tool_input": {"agent_type": "worker"},
    }
    result = run([PY, TOOL_GATE, "--event", "PreToolUse"], input_text=json.dumps(invalid_dispatch))
    require(result.returncode == 2 and "AGENT1" in result.stderr, result.stdout + result.stderr)
    valid_dispatch = {
        "tool_name": "Agent",
        "tool_input": {"agent_type": "researcher"},
    }
    result = run([PY, TOOL_GATE, "--event", "PreToolUse"], input_text=json.dumps(valid_dispatch))
    require(result.returncode == 0, result.stdout + result.stderr)


@case("data tools require no human schema review")
def _():
    paths = (
        os.path.join(ROOT, "shared", "CORE.md"),
        os.path.join(ROOT, "shared", "skills", "rblx-writer", "SKILL.md"),
        os.path.join(ROOT, "tools", "data_write", "data_write.py"),
        os.path.join(ROOT, "tools", "data_shape_diff", "data_shape_diff.luau"),
    )
    text = "\n".join(open(path, encoding="utf-8").read().lower() for path in paths)
    for blocker in ("human schema", "human ruling", "prior human", "data34"):
        require(blocker not in text, "stale data review blocker: %s" % blocker)


@case("token compression supports only the four retained agents")
def _():
    tool = os.path.join(ROOT, "shared", "gates", "token_shrink.py")
    source = "researcher: FOUND\n\nfact|docs|worker is required to preserve input in order to continue"
    result = run([PY, tool, "--agent", "researcher"], input_text=source)
    require(result.returncode == 0 and "must preserve input to continue" in result.stdout, result.stdout + result.stderr)
    removed = run([PY, tool, "--agent", "maintainer"], input_text="maintainer: READY")
    require(removed.returncode != 0, removed.stdout + removed.stderr)


def main():
    failures = []
    for name, function in CASES:
        try:
            function()
        except Exception as error:
            failures.append((name, error))
            print("FAIL|%s|%s" % (name, error))
        else:
            print("PASS|%s" % name)
    if failures:
        print("VERIFY|FAILED|%d/%d" % (len(failures), len(CASES)))
        return 2
    print("VERIFY|READY|%d" % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
