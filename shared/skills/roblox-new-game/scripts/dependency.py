#!/usr/bin/env python3
"""Consent, install, and manage the project-local rblx-harness dependency."""

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys


DEPENDENCY_PATH = ".roblox-harness"
DEFAULT_URL = "https://github.com/lennyRBLX/rblx-harness.git"
AGENT_NAMES = ("reviewer", "debugger", "optimizer", "researcher", "maintainer")
PROJECT_LOCAL_INSTALL_SCHEMA = 1


def local_integration_files():
    """Files that prove both project-local host integrations were installed."""
    files = [
        ".codex/config.toml",
        ".codex/hooks.json",
        ".agents/skills/roblox-writer/SKILL.md",
        ".agents/skills/roblox-writer/agents/openai.yaml",
        ".claude/settings.json",
        ".claude/skills/roblox-writer/SKILL.md",
    ]
    files.extend(".codex/agents/%s.toml" % name for name in AGENT_NAMES)
    files.extend(".claude/agents/%s.md" % name for name in AGENT_NAMES)
    return tuple(files)


DEPENDENCY_INTEGRATION_FILES = (
    "shared/CORE.md",
    "shared/gates/gatelib.py",
    "shared/gates/session_gate.py",
    "shared/gates/write_gate.py",
    "shared/gates/done_gate.py",
)


class DependencyError(RuntimeError):
    pass


def command(args, cwd=None, check=True):
    try:
        result = subprocess.run(
            list(args),
            cwd=cwd,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise DependencyError("%s is unavailable: %s" % (args[0], error)) from error
    if check and result.returncode != 0:
        raise DependencyError((result.stderr or result.stdout or "%s failed" % args[0]).strip()[:600])
    return result


def git(root, *args, check=True, github_auth=False):
    invocation = ["git", "-C", root]
    if github_auth:
        gh = shutil.which("gh")
        if not gh:
            raise DependencyError("GitHub CLI is unavailable")
        invocation.extend(
            (
                "-c",
                "credential.https://github.com.helper=",
                "-c",
                "credential.https://github.com.helper=!%s auth git-credential" % shlex.quote(gh),
            )
        )
    return command(invocation + list(args), check=check)


def github_slug(url):
    match = re.fullmatch(
        r"(?:https://github\.com/|git@github\.com:)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?",
        url,
    )
    return match.group(1) if match else ""


def github_auth_support(url):
    slug = github_slug(url)
    if not slug:
        raise DependencyError("dependency URL must identify a GitHub repository")
    gh = shutil.which("gh")
    if not gh:
        raise DependencyError("GitHub CLI is unavailable; install gh and authenticate before retrying")
    auth = command([gh, "auth", "status", "--hostname", "github.com"], check=False)
    if auth.returncode != 0:
        if os.environ.get("CODEX_SANDBOX"):
            raise DependencyError(
                "GitHub CLI authentication is unavailable inside the Codex sandbox; "
                "this does not mean that the user authentication is invalid. "
                "Rerun the approved setup command outside the sandbox"
            )
        raise DependencyError(
            (auth.stderr or auth.stdout or "GitHub CLI is not authenticated").strip()[:600]
        )
    visible = command([gh, "repo", "view", slug, "--json", "nameWithOwner"], check=False)
    if visible.returncode != 0:
        if os.environ.get("CODEX_SANDBOX"):
            raise DependencyError(
                "GitHub repository access is unavailable inside the Codex sandbox; "
                "this does not mean that the user authentication is invalid. "
                "Rerun the approved setup command outside the sandbox"
            )
        raise DependencyError(
            (visible.stderr or visible.stdout or "GitHub dependency repository is not accessible").strip()[:600]
        )
    print("github-auth|ready|repository=%s" % slug)
    return slug


def configure_github_credentials(root):
    key = "credential.https://github.com.helper"
    git(root, "config", "--local", "--unset-all", key, check=False)
    git(root, "config", "--local", "--add", key, "")
    git(root, "config", "--local", "--add", key, "!gh auth git-credential")
    print("github-auth|git-credential-helper=project-local")


def setup_consent(root, url, assume_yes=False):
    if assume_yes:
        return True
    question = (
        "Do you want to install rblx-harness? This will install it from %s into %s, "
        "initialize Git when needed, and install its hooks, gates, and rules. [y/N]"
        % (url, os.path.realpath(root))
    )
    if not sys.stdin.isatty():
        print("CONSENT_REQUIRED|%s" % question)
        return None
    try:
        answer = input(question + " ").strip().casefold()
    except EOFError:
        print("CONSENT_REQUIRED|%s" % question)
        return None
    if answer not in ("y", "yes"):
        print("dependency-setup|declined")
        return False
    return True


def prepare_project(root):
    root = os.path.realpath(root)
    if not os.path.isdir(root):
        raise DependencyError("project root is absent")
    if not shutil.which("git"):
        raise DependencyError("Git is unavailable")

    marker = os.path.join(root, ".roblox")
    marker_exists = os.path.lexists(marker)
    if marker_exists and (
        os.path.islink(marker) or not os.path.isfile(marker) or os.path.getsize(marker) != 0
    ):
        raise DependencyError("project root must contain an empty regular .roblox file")

    probe = git(root, "rev-parse", "--show-toplevel", check=False)
    if probe.returncode == 0:
        existing_root = os.path.realpath(probe.stdout.strip())
        if existing_root != root:
            raise DependencyError("project directory is nested inside another Git repository")
        repo_state = "existing"
    else:
        git(root, "init")
        repo_state = "initialized"

    if marker_exists:
        marker_state = "existing"
    else:
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        os.close(descriptor)
        marker_state = "created"
    print("project-preflight|git=%s|marker=%s" % (repo_state, marker_state))
    return root


def project_root(path):
    root = os.path.realpath(path)
    if not os.path.isdir(root):
        raise DependencyError("project root is absent")
    marker = os.path.join(root, ".roblox")
    if os.path.islink(marker) or not os.path.isfile(marker) or os.path.getsize(marker) != 0:
        raise DependencyError("project root must contain an empty regular .roblox file")
    result = git(root, "rev-parse", "--show-toplevel")
    if os.path.realpath(result.stdout.strip()) != root:
        raise DependencyError("--root must identify the project Git root")
    return root


def dependency_root(root):
    return os.path.join(root, DEPENDENCY_PATH)


def registered_submodule(root):
    modules = os.path.join(root, ".gitmodules")
    if not os.path.isfile(modules) or os.path.islink(modules):
        return False
    result = git(
        root,
        "config",
        "--file",
        modules,
        "--get-regexp",
        r"^submodule\..*\.path$",
        check=False,
    )
    return result.returncode == 0 and any(
        line.rsplit(None, 1)[-1] == DEPENDENCY_PATH
        for line in result.stdout.splitlines()
        if line.strip()
    )


def registered_url(root):
    modules = os.path.join(root, ".gitmodules")
    result = git(
        root,
        "config",
        "--file",
        modules,
        "--get",
        "submodule.roblox-harness.url",
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def initialized_dependency(root):
    dependency = dependency_root(root)
    required = (
        os.path.join(dependency, "shared", "CORE.md"),
        os.path.join(dependency, "shared", "gates", "gatelib.py"),
        os.path.join(dependency, "openai", "hooks", "adapter.py"),
    )
    return (
        os.path.isdir(dependency)
        and not os.path.islink(dependency)
        and git(dependency, "rev-parse", "--is-inside-work-tree", check=False).returncode == 0
        and all(os.path.isfile(path) for path in required)
    )


def require_initialized(root):
    if not registered_submodule(root):
        raise DependencyError(".roblox-harness is not registered in .gitmodules")
    if not initialized_dependency(root):
        raise DependencyError(".roblox-harness submodule is not initialized")
    return dependency_root(root)


def checkout_ref(dependency, ref, github_auth=False):
    git(dependency, "fetch", "--depth", "1", "origin", ref, github_auth=github_auth)
    git(dependency, "checkout", "--detach", "FETCH_HEAD")


def ensure_dependency_contract(dependency):
    """Reject a clone that predates the project-local installation API."""
    probe = """
import os
import sys

root = os.path.realpath(sys.argv[1])
sys.path.insert(0, os.path.join(root, "shared", "gates"))
import gatelib

missing = []
if getattr(gatelib, "PROJECT_LOCAL_INSTALL_SCHEMA", 0) < %d:
    missing.append("PROJECT_LOCAL_INSTALL_SCHEMA")
if getattr(gatelib, "PROJECT_HARNESS_DIR", "") != ".roblox-harness":
    missing.append("PROJECT_HARNESS_DIR")
if not isinstance(getattr(gatelib, "HANDOFF_RELATIVE", None), str):
    missing.append("HANDOFF_RELATIVE")
if not callable(getattr(gatelib, "project_harness_root", None)):
    missing.append("project_harness_root")
if missing:
    sys.stderr.write(", ".join(missing))
    raise SystemExit(2)
""" % PROJECT_LOCAL_INSTALL_SCHEMA
    result = command([sys.executable, "-B", "-c", probe, dependency], check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "project-local installation API").strip()[:300]
        raise DependencyError(
            "cloned .roblox-harness is incompatible with project-local installation "
            "(missing or invalid %s); update the dependency remote and retry setup" % detail
        )


def sync_existing_dependency(root, dependency, url, ref=""):
    registered = registered_url(root)
    if registered != url:
        raise DependencyError(
            ".roblox-harness is registered with %s, not %s"
            % (registered or "an unknown URL", url)
        )
    dirty = git(dependency, "status", "--porcelain").stdout.strip()
    if dirty:
        raise DependencyError(".roblox-harness has local changes; preserve or remove them before retry")
    remote = git(dependency, "remote", "get-url", "origin").stdout.strip()
    github = bool(github_slug(remote) or github_slug(url))
    checkout_ref(dependency, ref or "HEAD", github_auth=github)
    git(root, "add", ".gitmodules", DEPENDENCY_PATH)


def install(root, url, ref=""):
    root = project_root(root)
    destination = dependency_root(root)
    existed = registered_submodule(root)
    if existed:
        if not initialized_dependency(root):
            git(
                root,
                "submodule",
                "update",
                "--init",
                "--recursive",
                "--",
                DEPENDENCY_PATH,
                github_auth=bool(github_slug(url)),
            )
        dependency = require_initialized(root)
    else:
        if os.path.lexists(destination):
            raise DependencyError("canonical .roblox-harness path is occupied but is not a registered submodule")
        git(
            root,
            "submodule",
            "add",
            "--name",
            "roblox-harness",
            url,
            DEPENDENCY_PATH,
            github_auth=bool(github_slug(url)),
        )
        dependency = require_initialized(root)
    if github_slug(url):
        configure_github_credentials(root)
        configure_github_credentials(dependency)
    if existed:
        sync_existing_dependency(root, dependency, url, ref)
    elif ref:
        checkout_ref(dependency, ref, github_auth=bool(github_slug(url)))
        git(root, "add", ".gitmodules", DEPENDENCY_PATH)
    return status(root, prefix="dependency-installed")


def install_integration(root):
    dependency = require_initialized(root)
    ensure_dependency_contract(dependency)
    relinker = os.path.join(dependency, "openai", "setup", "permissions_harness.py")
    if not os.path.isfile(relinker):
        raise DependencyError("cloned dependency has no permissions_harness.py relinker")
    result = command([sys.executable, relinker, "--relink"], cwd=root, check=False)
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    if result.returncode != 0:
        raise DependencyError("harness relink failed with exit %d" % result.returncode)
    required = tuple(
        os.path.join(dependency, *relative.split("/"))
        for relative in DEPENDENCY_INTEGRATION_FILES
    ) + tuple(
        os.path.join(root, *relative.split("/"))
        for relative in local_integration_files()
    )
    missing = [path for path in required if not os.path.isfile(path)]
    if missing:
        raise DependencyError("integration output missing: %s" % os.path.relpath(missing[0], root))
    print(
        "harness-integrated|roblox-writer=installed|agents=installed|hooks=project-local|"
        "gates=.roblox-harness/shared/gates|rules=.roblox-harness/shared/CORE.md"
    )
    return 0


def setup(root, url=DEFAULT_URL, ref="", assume_yes=False):
    consent = setup_consent(root, url, assume_yes=assume_yes)
    if consent is None:
        return 1
    if not consent:
        return 0
    if github_slug(url):
        github_auth_support(url)
    root = prepare_project(root)
    install(root, url, ref)
    install_integration(root)
    print("dependency-setup|complete|path=%s" % DEPENDENCY_PATH)
    return 0


def initialize(root):
    root = project_root(root)
    url = registered_url(root)
    github = bool(github_slug(url))
    if github:
        github_auth_support(url)
        configure_github_credentials(root)
    git(
        root,
        "submodule",
        "update",
        "--init",
        "--recursive",
        "--",
        DEPENDENCY_PATH,
        github_auth=github,
    )
    dependency = require_initialized(root)
    if github:
        configure_github_credentials(dependency)
    return status(root, prefix="dependency-initialized")


def update(root, ref=""):
    root = project_root(root)
    dependency = require_initialized(root)
    remote = git(dependency, "remote", "get-url", "origin").stdout.strip()
    github = bool(github_slug(remote))
    if github:
        github_auth_support(remote)
        configure_github_credentials(root)
        configure_github_credentials(dependency)
    dirty = git(dependency, "status", "--porcelain").stdout.strip()
    if dirty:
        raise DependencyError(".roblox-harness has local changes; preserve or remove them before update")
    if ref:
        checkout_ref(dependency, ref, github_auth=github)
    else:
        git(
            root,
            "submodule",
            "update",
            "--remote",
            "--recursive",
            "--",
            DEPENDENCY_PATH,
            github_auth=github,
        )
    git(root, "add", DEPENDENCY_PATH)
    return status(root, prefix="dependency-updated")


def status(root, prefix="dependency"):
    root = project_root(root)
    dependency = require_initialized(root)
    commit = git(dependency, "rev-parse", "HEAD").stdout.strip()
    remote = git(dependency, "remote", "get-url", "origin").stdout.strip()
    dirty = bool(git(dependency, "status", "--porcelain").stdout.strip())
    staged = git(root, "diff", "--quiet", "--cached", "--", DEPENDENCY_PATH, check=False).returncode != 0
    line = "%s|path=%s|commit=%s|remote=%s|dirty=%s|staged=%s" % (
        prefix,
        DEPENDENCY_PATH,
        commit,
        remote,
        "yes" if dirty else "no",
        "yes" if staged else "no",
    )
    print(line)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("setup", "install", "init", "update", "status"))
    parser.add_argument("--root", default=os.getcwd())
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--ref", default="")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "setup":
        return setup(args.root, args.url, args.ref, assume_yes=args.yes)
    if args.command == "install":
        return install(args.root, args.url, args.ref)
    if args.command == "init":
        return initialize(args.root)
    if args.command == "update":
        return update(args.root, args.ref)
    return status(args.root)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DependencyError as error:
        sys.stderr.write("roblox-harness-dependency: ERROR %s\n" % error)
        sys.exit(2)
