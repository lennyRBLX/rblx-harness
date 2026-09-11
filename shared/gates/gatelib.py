"""Small shared helpers for rblx-harness tools and Codex gates."""

import json
import os
import re
import subprocess
import time

try:
    import tomllib
except ImportError:  # Python 3.11+
    tomllib = None


HARNESS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS = os.path.join(HARNESS, "tools")
CACHE = os.path.expanduser("~/.cache/harness")
CORPUS_REFRESH = os.path.join(CACHE, "corpus-refresh.json")
CORPUS_MAX_AGE = 86400
PROJECT_HARNESS_DIR = "rblx-harness"
PROJECT_HARNESS_URL = "https://github.com/lennyRBLX/rblx-harness.git"
REQUIRED_CODEX_AGENTS = ("researcher", "optimizer", "reviewer", "debugger")
REQUIRED_SKILLS = ("rblx-writer", "rblx-gui", "rblx-debug", "rblx-optimize", "rblx-plan")


def bundled_tool_path(name, windows=None):
    windows = os.name == "nt" if windows is None else bool(windows)
    suffix = ".exe" if windows and not str(name).lower().endswith(".exe") else ""
    return os.path.join(TOOLS, "bin", str(name) + suffix)


LUTE = bundled_tool_path("lute")
LUAU_LSP = bundled_tool_path("luau-lsp")


def which(name, path=None, pathext=None, windows=None):
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


def git(cwd, *args):
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    result = subprocess.run(
        ["git", "-C", cwd] + list(args),
        capture_output=True,
        text=True,
        env=environment,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def git_mutate(cwd, *args, timeout=90):
    try:
        result = subprocess.run(
            ["git", "-C", cwd] + list(args),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return 1, "", str(error)[:240]
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def canonical_remote_branch(cwd):
    rc, output, error = git_mutate(cwd, "ls-remote", "--symref", "origin", "HEAD", timeout=60)
    if rc != 0:
        return None, (error or output or "origin HEAD could not be read")[:200]
    match = re.search(r"^ref:\s+refs/heads/([^\s]+)\s+HEAD$", output, re.MULTILINE)
    if not match:
        return None, "origin HEAD does not name a branch"
    return match.group(1), ""


def gate6_state(cwd, fetch=True):
    rc, _, _ = git(cwd, "rev-parse", "--git-dir")
    if rc != 0:
        return "not-repo", "working directory is not a git repository"
    rc, head, error = git(cwd, "rev-parse", "--verify", "HEAD^{commit}")
    if rc != 0 or not head:
        return "head-read-failed", error or "HEAD could not be read"
    rc, branch, error = git(cwd, "symbolic-ref", "--quiet", "--short", "HEAD")
    if rc != 0 or not branch:
        return "no-upstream", error or "detached HEAD"
    rc, remote, _ = git(cwd, "remote", "get-url", "origin")
    if rc != 0 or not remote:
        return "no-remote", "origin is not configured"
    canonical, error = canonical_remote_branch(cwd)
    if canonical is None:
        return "remote-head-read-failed", error
    if branch != canonical:
        return "wrong-branch", "%s is checked out; origin requires %s" % (branch, canonical)
    upstream = "origin/" + canonical
    if fetch:
        refspec = "+refs/heads/%s:refs/remotes/origin/%s" % (canonical, canonical)
        rc, output, error = git_mutate(cwd, "fetch", "--quiet", "--no-tags", "origin", refspec)
        if rc != 0:
            return "fetch-failed", (error or output or "git fetch failed")[:200]
    rc, counts, error = git(cwd, "rev-list", "--left-right", "--count", "%s...HEAD" % upstream)
    if rc != 0:
        return "ref-read-failed", error or "could not compare HEAD"
    try:
        behind, ahead = (int(value) for value in counts.split())
    except ValueError:
        return "ref-read-failed", "git returned an unreadable comparison"
    if behind and ahead:
        return "diverged", "%d behind, %d ahead" % (behind, ahead)
    if behind:
        return "behind", "%d behind" % behind
    return "ok", ""


def is_harness(cwd):
    root = os.path.realpath(cwd)
    return all(
        os.path.isfile(os.path.join(root, relative))
        for relative in ("shared/CORE.md", "setup_project.py", "openai/config/project.toml")
    )


def is_roblox_project(cwd):
    return isinstance(cwd, str) and os.path.isfile(os.path.join(os.path.realpath(cwd), ".roblox"))


def project_harness_root(cwd):
    if not isinstance(cwd, str) or not cwd:
        return ""
    root = os.path.realpath(cwd)
    rc, path, _ = git(root, "config", "-f", ".gitmodules", "--get", "submodule.%s.path" % PROJECT_HARNESS_DIR)
    if rc != 0 or path != PROJECT_HARNESS_DIR:
        return ""
    rc, url, _ = git(root, "config", "-f", ".gitmodules", "--get", "submodule.%s.url" % PROJECT_HARNESS_DIR)
    if rc != 0 or url != PROJECT_HARNESS_URL:
        return ""
    rc, indexed, _ = git(root, "ls-files", "--stage", "--", PROJECT_HARNESS_DIR)
    if rc != 0 or not any(line.startswith("160000 ") for line in indexed.splitlines()):
        return ""
    rc, modules_index, _ = git(root, "ls-files", "--stage", "--", ".gitmodules")
    if rc != 0 or not any(line.startswith("100644 ") for line in modules_index.splitlines()):
        return ""
    rc, _, _ = git(root, "diff", "--quiet", "--", ".gitmodules")
    if rc != 0:
        return ""
    candidate = os.path.join(root, PROJECT_HARNESS_DIR)
    if os.path.islink(candidate) or not os.path.exists(candidate) or not is_harness(candidate):
        return ""
    return os.path.realpath(candidate)


def project_uses_harness(cwd, harness=None):
    candidate = project_harness_root(cwd)
    if not candidate:
        return False
    return harness is None or candidate == os.path.realpath(harness)


def merge_project_codex_config(existing, canonical):
    """Insert missing scalar defaults without rewriting user TOML or preferences."""
    if tomllib is None:
        raise ValueError("Python tomllib is unavailable")
    existing = existing or ""
    try:
        configured = tomllib.loads(existing)
        defaults = tomllib.loads(canonical)
    except tomllib.TOMLDecodeError as error:
        raise ValueError("project Codex config is malformed: %s" % str(error)[:160]) from error
    additions = []
    for key, value in defaults.items():
        if not re.fullmatch(r"[A-Za-z0-9_-]+", key) or type(value) not in (str, int, bool):
            raise ValueError("harness defaults must use scalar top-level TOML keys")
        if key not in configured:
            additions.append("%s = %s" % (key, json.dumps(value, ensure_ascii=False)))
    if not additions:
        return existing
    # Prepending keeps new root keys out of the user's final table and never
    # interprets headings or assignments inside multiline TOML strings.
    merged = "\n".join(additions) + "\n\n" + existing
    tomllib.loads(merged)
    return merged


def required_codex_agents_status(root):
    if tomllib is None:
        return False, "Python tomllib is unavailable"
    agents_dir = os.path.join(os.path.realpath(root), ".codex", "agents")
    present = sorted(
        os.path.splitext(name)[0]
        for name in os.listdir(agents_dir)
        if name.endswith(".toml")
    ) if os.path.isdir(agents_dir) else []
    if not set(REQUIRED_CODEX_AGENTS).issubset(present):
        return False, "Codex agents must include: %s" % ", ".join(REQUIRED_CODEX_AGENTS)
    for name in REQUIRED_CODEX_AGENTS:
        path = os.path.join(agents_dir, name + ".toml")
        try:
            with open(path, "rb") as handle:
                definition = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as error:
            return False, "%s is invalid: %s" % (path, error)
        if definition.get("name") != name or not definition.get("description") or not definition.get("developer_instructions"):
            return False, "%s has an invalid agent definition" % path
        if definition.get("agents", {}).get("enabled") is not False:
            return False, "%s must disable nested delegation" % path
    return True, ""


def corpus_assets_error():
    dump_path = os.path.join(CACHE, "API-Dump.json")
    docs_root = os.path.join(CACHE, "creator-docs")
    engine = os.path.join(docs_root, "content", "en-us", "reference", "engine")
    index_path = os.path.join(CACHE, "docs_index.json")
    for path, label, directory in (
        (dump_path, "API-Dump.json", False),
        (os.path.join(docs_root, ".git"), "Creator Docs .git", True),
        (engine, "Creator Docs engine corpus", True),
        (index_path, "docs_index.json", False),
    ):
        if not (os.path.isdir(path) if directory else os.path.isfile(path)):
            return "%s is missing" % label
    try:
        dump = json.load(open(dump_path, encoding="utf-8"))
        index = json.load(open(index_path, encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as error:
        return "corpus is unreadable or malformed: %s" % str(error)[:160]
    if not isinstance(dump, dict) or not isinstance(dump.get("Classes"), list) or not isinstance(dump.get("Enums"), list):
        return "API-Dump.json has an invalid schema"
    if not isinstance(index, list):
        return "docs_index.json has an invalid schema"
    if not any(name.endswith((".yaml", ".yml")) for _, _, names in os.walk(engine) for name in names):
        return "Creator Docs engine corpus has no YAML records"
    return ""


def corpus_status(now=None):
    error = corpus_assets_error()
    if error:
        return ("missing" if "missing" in error else "malformed"), error
    try:
        refresh = json.load(open(CORPUS_REFRESH, encoding="utf-8"))
        refreshed_at = refresh.get("refreshed_at") if isinstance(refresh, dict) else None
        if not isinstance(refreshed_at, (int, float)) or isinstance(refreshed_at, bool):
            return "malformed", "successful-refresh timestamp is malformed"
        age = (time.time() if now is None else now) - float(refreshed_at)
    except (OSError, ValueError, UnicodeError) as error:
        return "stale", "successful-refresh timestamp is unavailable: %s" % str(error)[:120]
    if age < -300:
        return "malformed", "successful-refresh timestamp is in the future"
    if age >= CORPUS_MAX_AGE:
        return "stale", "successful refresh is at least 24 hours old"
    return "fresh", ""
