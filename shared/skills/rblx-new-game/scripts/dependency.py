#!/usr/bin/env python3
"""Install or initialize the project-local rblx-harness Git submodule."""

import argparse
import os
import subprocess
import sys


DEPENDENCY_NAME = "rblx-harness"
REPOSITORY_URL = "https://github.com/lennyRBLX/rblx-harness.git"


class DependencyError(RuntimeError):
    pass


def run(args, cwd, check=True):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise DependencyError((result.stderr or result.stdout or "command failed").strip()[:500])
    return result


def valid_harness(path):
    return all(
        os.path.isfile(os.path.join(path, relative))
        for relative in ("setup_project.py", "shared/CORE.md", "shared/skills/rblx-new-game/SKILL.md")
    )


def ensure_project(root):
    root = os.path.realpath(root)
    if not os.path.isdir(root):
        raise DependencyError("project directory is absent: %s" % root)
    top = run(["git", "rev-parse", "--show-toplevel"], root, check=False)
    if top.returncode != 0 or os.path.realpath(top.stdout.strip()) != root:
        run(["git", "init"], root)
    marker = os.path.join(root, ".roblox")
    if os.path.lexists(marker) and (os.path.islink(marker) or not os.path.isfile(marker)):
        raise DependencyError(".roblox must be a regular file")
    if not os.path.exists(marker):
        open(marker, "a", encoding="utf-8").close()
    return root


def configured_path(root):
    result = run(
        ["git", "config", "-f", ".gitmodules", "--get", "submodule.%s.path" % DEPENDENCY_NAME],
        root,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def configured_url(root):
    result = run(
        ["git", "config", "-f", ".gitmodules", "--get", "submodule.%s.url" % DEPENDENCY_NAME],
        root,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def indexed_submodule(root):
    result = run(["git", "ls-files", "--stage", "--", DEPENDENCY_NAME], root, check=False)
    for line in result.stdout.splitlines():
        metadata, separator, path = line.partition("\t")
        fields = metadata.split()
        if separator and path == DEPENDENCY_NAME and fields and fields[0] == "160000":
            return True
    return False


def modules_file_tracked(root):
    indexed = run(["git", "ls-files", "--stage", "--", ".gitmodules"], root, check=False)
    if indexed.returncode != 0 or not any(
        line.startswith("100644 ") for line in indexed.stdout.splitlines()
    ):
        return False
    unchanged = run(["git", "diff", "--quiet", "--", ".gitmodules"], root, check=False)
    return unchanged.returncode == 0


def registered_submodule(root):
    return (
        configured_path(root) == DEPENDENCY_NAME
        and configured_url(root) == REPOSITORY_URL
        and indexed_submodule(root)
        and modules_file_tracked(root)
    )


def update_submodule(root):
    run(["git", "submodule", "sync", "--", DEPENDENCY_NAME], root)
    run(["git", "submodule", "update", "--init", "--recursive", "--", DEPENDENCY_NAME], root)


def install_submodule(root):
    destination = os.path.join(root, DEPENDENCY_NAME)
    configured = bool(configured_path(root) or configured_url(root))
    indexed = indexed_submodule(root)
    if configured or indexed:
        if not registered_submodule(root):
            raise DependencyError(
                "rblx-harness submodule must use path %s and URL %s"
                % (DEPENDENCY_NAME, REPOSITORY_URL)
            )
        if os.path.islink(destination):
            raise DependencyError("rblx-harness submodule path must not be a symlink")
        if valid_harness(destination):
            return "submodule-ready"
        update_submodule(root)
        if not valid_harness(destination):
            raise DependencyError("initialized rblx-harness submodule is invalid")
        return "submodule-initialized"
    if os.path.lexists(destination):
        raise DependencyError("rblx-harness exists but is not a registered Git submodule")
    legacy = os.path.join(root, "." + DEPENDENCY_NAME)
    if os.path.lexists(legacy):
        raise DependencyError("legacy hidden harness dependency exists; remove it before setup")
    run(["git", "submodule", "add", "--", REPOSITORY_URL], root)
    if not registered_submodule(root):
        raise DependencyError("rblx-harness Git submodule registration failed")
    if not valid_harness(destination):
        raise DependencyError("installed rblx-harness submodule is invalid")
    return "submodule-installed"


def setup(root, yes=False):
    if not yes:
        print(
            "CONSENT_REQUIRED|rblx-harness adds Codex skills, four agents, lean hooks, "
            "rules, tools, templates, and selected shared assets."
        )
        return 3
    root = ensure_project(root)
    state = install_submodule(root)
    print("dependency-setup|READY|mode=%s|path=%s" % (state, DEPENDENCY_NAME))
    return 0


def initialize(root):
    root = os.path.realpath(root)
    dependency = os.path.join(root, DEPENDENCY_NAME)
    if not registered_submodule(root):
        raise DependencyError("rblx-harness is not registered as the required Git submodule")
    if os.path.islink(dependency):
        raise DependencyError("rblx-harness submodule path must not be a symlink")
    update_submodule(root)
    if not valid_harness(dependency):
        raise DependencyError("initialized submodule is invalid")
    print("dependency-init|READY|submodule")
    return 0


def status(root):
    root = os.path.realpath(root)
    dependency = os.path.join(root, DEPENDENCY_NAME)
    legacy = os.path.join(root, "." + DEPENDENCY_NAME)
    if registered_submodule(root) and not os.path.islink(dependency) and valid_harness(dependency):
        print("dependency-status|READY|submodule")
        return 0
    if (
        configured_path(root)
        or configured_url(root)
        or indexed_submodule(root)
        or os.path.lexists(dependency)
        or os.path.lexists(legacy)
    ):
        print("dependency-status|INVALID|submodule")
        return 2
    print("dependency-status|ABSENT")
    return 2


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("setup", "init", "status"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "setup":
        return setup(args.root, args.yes)
    if args.command == "init":
        return initialize(args.root)
    return status(args.root)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (DependencyError, OSError) as error:
        sys.stderr.write("dependency: ERROR %s\n" % error)
        sys.exit(2)
