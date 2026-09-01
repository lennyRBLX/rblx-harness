#!/usr/bin/env python3
"""Install and verify the user-scope math-tool integration."""

import argparse
import hashlib
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import venv


HARNESS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SHARED_SKILL = os.path.join(HARNESS, "shared", "skills", "math-tool")
CODEX_METADATA = os.path.join(HARNESS, "openai", "skills", "math-tool", "agents", "openai.yaml")
CODEX_HOOK_TEMPLATE = os.path.join(HARNESS, "openai", "hooks", "math-bootstrap.json")
CLAUDE_HOOK_TEMPLATE = os.path.join(HARNESS, "claude", "settings", "math-user.json")
LOCK_PATH = os.path.join(SHARED_SKILL, "scripts", "runtime.lock.json")
MAX_WHEEL_BYTES = 32 * 1024 * 1024
OWNED_EVENTS = {
    "codex": ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "PreCompact", "SessionEnd"),
    "claude": (
        "SessionStart",
        "UserPromptSubmit",
        "PreToolUse",
        "PostToolUse",
        "PostToolUseFailure",
        "Stop",
        "PreCompact",
        "SessionEnd",
    ),
}


def _json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def _atomic_bytes(path, data, mode=0o600):
    try:
        with open(path, "rb") as handle:
            if handle.read() == data:
                return False
    except FileNotFoundError:
        pass
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    temporary = os.path.join(directory, ".%s.%d.tmp" % (os.path.basename(path), os.getpid()))
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        os.chmod(path, mode)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return True


def _atomic_json(path, value, mode=0o600):
    return _atomic_bytes(path, _json_text(value).encode("utf-8"), mode=mode)


def _load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError:
        return {} if default is None else default
    except (OSError, ValueError, UnicodeError) as error:
        raise RuntimeError("%s is unreadable or malformed: %s" % (path, str(error)[:160]))
    if not isinstance(value, dict):
        raise RuntimeError("%s must contain one JSON object" % path)
    return value


def _lock_data():
    with open(LOCK_PATH, "rb") as handle:
        raw = handle.read()
    try:
        value = json.loads(raw)
    except ValueError:
        raise RuntimeError("runtime lock is malformed")
    packages = value.get("packages") if isinstance(value, dict) else None
    if value.get("v") != 1 or not isinstance(packages, list) or len(packages) != 2:
        raise RuntimeError("runtime lock does not contain the required packages")
    expected = {"sympy": "1.14.0", "mpmath": "1.3.0"}
    observed = {}
    for package in packages:
        if not isinstance(package, dict):
            raise RuntimeError("runtime package entry is malformed")
        required = {"name", "version", "filename", "url", "sha256", "platforms"}
        if set(package) != required or package.get("platforms") != ["any"]:
            raise RuntimeError("runtime package entry does not match the portable wheel schema")
        if not isinstance(package.get("sha256"), str) or len(package["sha256"]) != 64:
            raise RuntimeError("runtime package hash is malformed")
        observed[package["name"]] = package["version"]
    if observed != expected:
        raise RuntimeError("runtime package versions do not match the tool pin")
    return value, hashlib.sha256(raw).hexdigest()


def _runtime_python(venv_path):
    return os.path.join(venv_path, "Scripts", "python.exe") if os.name == "nt" else os.path.join(venv_path, "bin", "python")


def _probe_runtime(python_path):
    if not os.path.isfile(python_path):
        return None
    result = subprocess.run(
        [python_path, "-B", "-c", "import json,mpmath,sympy;print(json.dumps([sympy.__version__,mpmath.__version__]))"],
        capture_output=True,
        text=True,
        timeout=30,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PIP_DISABLE_PIP_VERSION_CHECK="1"),
    )
    if result.returncode != 0:
        return None
    try:
        value = json.loads(result.stdout)
    except ValueError:
        return None
    return value if value == ["1.14.0", "1.3.0"] else None


def _runtime_exact(runtime_root, lock_digest):
    venv_path = os.path.join(runtime_root, "venv")
    python_path = _runtime_python(venv_path)
    try:
        stamp = _load_json(os.path.join(runtime_root, "runtime.json"))
    except RuntimeError:
        return False
    return (
        stamp.get("v") == 1
        and stamp.get("lock_digest") == lock_digest
        and os.path.realpath(stamp.get("venv", "")) == os.path.realpath(venv_path)
        and os.path.realpath(stamp.get("python", "")) == os.path.realpath(python_path)
        and stamp.get("sympy") == "1.14.0"
        and stamp.get("mpmath") == "1.3.0"
        and _probe_runtime(python_path) is not None
    )


def _download_wheel(package, destination, opener=None):
    response = (opener or urllib.request.urlopen)(package["url"])
    try:
        data = response.read(MAX_WHEEL_BYTES + 1)
    finally:
        close = getattr(response, "close", None)
        if close:
            close()
    if len(data) > MAX_WHEEL_BYTES:
        raise RuntimeError("%s wheel exceeds the download limit" % package["name"])
    if hashlib.sha256(data).hexdigest() != package["sha256"]:
        raise RuntimeError("%s wheel sha256 mismatch" % package["name"])
    _atomic_bytes(destination, data, mode=0o600)


def install_runtime(runtime_root=None, opener=None):
    """Install the two locked universal wheels into the owned virtual environment."""
    runtime_root = os.path.realpath(runtime_root or os.path.join(os.path.expanduser("~"), ".cache", "harness", "math-tool"))
    lock, lock_digest = _lock_data()
    if _runtime_exact(runtime_root, lock_digest):
        return False
    os.makedirs(runtime_root, mode=0o700, exist_ok=True)
    stage = tempfile.mkdtemp(prefix=".venv-install-", dir=runtime_root)
    wheel_dir = tempfile.mkdtemp(prefix=".wheels-", dir=runtime_root)
    venv_path = os.path.join(runtime_root, "venv")
    previous = os.path.join(runtime_root, ".venv-previous")
    moved_previous = False
    try:
        venv.EnvBuilder(with_pip=True, clear=True).create(stage)
        wheel_paths = []
        for package in lock["packages"]:
            wheel_path = os.path.join(wheel_dir, package["filename"])
            _download_wheel(package, wheel_path, opener=opener)
            wheel_paths.append(wheel_path)
        stage_python = _runtime_python(stage)
        install = subprocess.run(
            [
                stage_python,
                "-B",
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                "--disable-pip-version-check",
            ]
            + wheel_paths,
            capture_output=True,
            text=True,
            timeout=180,
            env=dict(os.environ, PIP_NO_INPUT="1", PIP_DISABLE_PIP_VERSION_CHECK="1", PYTHONDONTWRITEBYTECODE="1"),
        )
        if install.returncode != 0 or _probe_runtime(stage_python) is None:
            raise RuntimeError("pinned runtime installation failed")
        if os.path.lexists(previous):
            shutil.rmtree(previous) if os.path.isdir(previous) and not os.path.islink(previous) else os.unlink(previous)
        if os.path.lexists(venv_path):
            os.replace(venv_path, previous)
            moved_previous = True
        os.replace(stage, venv_path)
        final_python = _runtime_python(venv_path)
        if _probe_runtime(final_python) is None:
            raise RuntimeError("installed runtime verification failed")
        stamp = {
            "v": 1,
            "lock_digest": lock_digest,
            "venv": os.path.realpath(venv_path),
            "python": os.path.realpath(final_python),
            "sympy": "1.14.0",
            "mpmath": "1.3.0",
            "installed": time.time(),
        }
        _atomic_json(os.path.join(runtime_root, "runtime.json"), stamp, mode=0o600)
        if moved_previous and os.path.lexists(previous):
            shutil.rmtree(previous)
        return True
    except BaseException:
        if moved_previous and not os.path.lexists(venv_path) and os.path.lexists(previous):
            os.replace(previous, venv_path)
        raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        shutil.rmtree(wheel_dir, ignore_errors=True)


def _source_files(host):
    files = {}
    for directory, names, filenames in os.walk(SHARED_SKILL):
        names[:] = [name for name in names if name != "__pycache__"]
        for filename in filenames:
            if filename.endswith((".pyc", ".pyo")):
                continue
            source = os.path.join(directory, filename)
            relative = os.path.relpath(source, SHARED_SKILL)
            files[relative] = source
    if host == "codex":
        files[os.path.join("agents", "openai.yaml")] = CODEX_METADATA
    return files


def _skill_exact(target, files):
    if not os.path.isdir(target) or os.path.islink(target):
        return False
    observed = set()
    for directory, names, filenames in os.walk(target):
        names[:] = [name for name in names if name != "__pycache__"]
        for filename in filenames:
            if filename.endswith((".pyc", ".pyo")):
                continue
            observed.add(os.path.relpath(os.path.join(directory, filename), target))
    if observed != set(files):
        return False
    for relative, source in files.items():
        try:
            with open(source, "rb") as left, open(os.path.join(target, relative), "rb") as right:
                if left.read() != right.read():
                    return False
        except OSError:
            return False
    return True


def install_skill(target, host):
    files = _source_files(host)
    target = os.path.abspath(target)
    if _skill_exact(target, files):
        return False
    parent = os.path.dirname(target)
    os.makedirs(parent, exist_ok=True)
    stage = tempfile.mkdtemp(prefix=".math-tool-skill-", dir=parent)
    previous = target + ".previous"
    moved_previous = False
    try:
        for relative, source in files.items():
            destination = os.path.join(stage, relative)
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            shutil.copy2(source, destination)
        if os.path.lexists(previous):
            shutil.rmtree(previous) if os.path.isdir(previous) and not os.path.islink(previous) else os.unlink(previous)
        if os.path.lexists(target):
            os.replace(target, previous)
            moved_previous = True
        os.replace(stage, target)
        for relative in files:
            if relative.endswith(".py"):
                os.chmod(os.path.join(target, relative), 0o755)
        if moved_previous and os.path.lexists(previous):
            shutil.rmtree(previous) if os.path.isdir(previous) and not os.path.islink(previous) else os.unlink(previous)
        return True
    except BaseException:
        if moved_previous and not os.path.lexists(target) and os.path.lexists(previous):
            os.replace(previous, target)
        raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def _handler_text(handler):
    if not isinstance(handler, dict):
        return ""
    values = [str(handler.get("command", ""))]
    if isinstance(handler.get("args"), list):
        values.extend(str(value) for value in handler["args"])
    windows = handler.get("commandWindows", handler.get("command_windows"))
    if isinstance(windows, str):
        values.append(windows)
    return " ".join(values)


def _owned_handler(handler, gate_path):
    text = _handler_text(handler).replace("\\", "/")
    target = os.path.realpath(gate_path).replace("\\", "/")
    return target.casefold() in text.casefold()


def command_line(arguments, windows=None):
    """Render one exact argv vector for the current or requested host shell."""
    windows = os.name == "nt" if windows is None else bool(windows)
    return subprocess.list2cmdline(arguments) if windows else shlex.join(arguments)


def _render_hooks(template_path, host, gate_path, python_executable, windows=None):
    document = _load_json(template_path)
    hooks = document.get("hooks")
    if not isinstance(hooks, dict) or tuple(hooks) != OWNED_EVENTS[host]:
        raise RuntimeError("%s math hook template event set is not exact" % host)
    for event, entries in hooks.items():
        for entry in entries:
            for handler in entry.get("hooks", []):
                if host == "codex":
                    arguments = [python_executable, "-B", gate_path, "--host", host, "--event", event]
                    handler["command"] = command_line(arguments, windows=windows)
                else:
                    handler["command"] = python_executable
                    handler["args"] = [
                        gate_path if value == "{{MATH_GATE}}" else value
                        for value in handler.get("args", [])
                    ]
    return document


def merge_owned_hooks(path, template_path, gate_path, host, python_executable=None):
    """Replace only handlers that contain the exact installed math gate path."""
    python_executable = os.path.realpath(python_executable or sys.executable)
    rendered = _render_hooks(template_path, host, os.path.realpath(gate_path), python_executable)
    existing = _load_json(path)
    hooks = existing.get("hooks")
    if hooks is None:
        hooks = {}
    if not isinstance(hooks, dict):
        raise RuntimeError("%s hooks must be one JSON object" % path)
    for event in OWNED_EVENTS[host]:
        preserved = []
        entries = hooks.get(event, [])
        if entries is not None and not isinstance(entries, list):
            raise RuntimeError("%s %s hooks must be a list" % (path, event))
        for entry in entries or []:
            if not isinstance(entry, dict):
                preserved.append(entry)
                continue
            value = dict(entry)
            handlers = value.get("hooks", [])
            if not isinstance(handlers, list):
                preserved.append(entry)
                continue
            value["hooks"] = [handler for handler in handlers if not _owned_handler(handler, gate_path)]
            if value["hooks"]:
                preserved.append(value)
        preserved.extend(rendered["hooks"][event])
        hooks[event] = preserved
    existing["hooks"] = hooks
    return _atomic_json(path, existing, mode=0o600)


def _owned_event_status(path, gate_path, host):
    document = _load_json(path)
    hooks = document.get("hooks")
    if not isinstance(hooks, dict):
        return False, "hooks object is absent"
    for event in OWNED_EVENTS[host]:
        matches = []
        for entry in hooks.get(event, []) if isinstance(hooks.get(event), list) else []:
            for handler in entry.get("hooks", []) if isinstance(entry, dict) else []:
                if _owned_handler(handler, gate_path):
                    matches.append((entry, handler))
        if len(matches) != 1:
            return False, "%s owned %s hook count is %d" % (host, event, len(matches))
        text = _handler_text(matches[0][1])
        if "--host %s" % host not in text or "--event %s" % event not in text or " -B " not in (" " + text + " "):
            return False, "%s owned %s command is malformed" % (host, event)
    if host == "codex":
        for entry in hooks.get("PostToolUseFailure", []) if isinstance(hooks.get("PostToolUseFailure"), list) else []:
            handlers = entry.get("hooks", []) if isinstance(entry, dict) else []
            if any(_owned_handler(handler, gate_path) for handler in handlers):
                return False, "Codex must not register owned PostToolUseFailure"
    return True, ""


def verify_install(home=None, codex_home=None, claude_home=None, runtime_root=None):
    home = os.path.realpath(home or os.path.expanduser("~"))
    codex_home = os.path.realpath(codex_home or os.environ.get("CODEX_HOME") or os.path.join(home, ".codex"))
    claude_home = os.path.realpath(claude_home or os.path.join(home, ".claude"))
    runtime_root = os.path.realpath(runtime_root or os.path.join(home, ".cache", "harness", "math-tool"))
    _, lock_digest = _lock_data()
    if not _runtime_exact(runtime_root, lock_digest):
        return False, "pinned runtime is not exact"
    codex_skill = os.path.join(home, ".agents", "skills", "math-tool")
    claude_skill = os.path.join(claude_home, "skills", "math-tool")
    if not _skill_exact(codex_skill, _source_files("codex")):
        return False, "Codex skill bytes are not exact"
    if not _skill_exact(claude_skill, _source_files("claude")):
        return False, "Claude skill bytes are not exact"
    ok, detail = _owned_event_status(os.path.join(codex_home, "hooks.json"), os.path.join(codex_skill, "scripts", "math_gate.py"), "codex")
    if not ok:
        return False, detail
    ok, detail = _owned_event_status(os.path.join(claude_home, "settings.json"), os.path.join(claude_skill, "scripts", "math_gate.py"), "claude")
    if not ok:
        return False, detail
    return True, "math-tool|READY"


def install(home=None, codex_home=None, claude_home=None, runtime_root=None):
    home = os.path.realpath(home or os.path.expanduser("~"))
    codex_home = os.path.realpath(codex_home or os.environ.get("CODEX_HOME") or os.path.join(home, ".codex"))
    claude_home = os.path.realpath(claude_home or os.path.join(home, ".claude"))
    runtime_root = os.path.realpath(runtime_root or os.path.join(home, ".cache", "harness", "math-tool"))
    runtime_changed = install_runtime(runtime_root)
    codex_skill = os.path.join(home, ".agents", "skills", "math-tool")
    claude_skill = os.path.join(claude_home, "skills", "math-tool")
    codex_skill_changed = install_skill(codex_skill, "codex")
    claude_skill_changed = install_skill(claude_skill, "claude")
    codex_hooks_changed = merge_owned_hooks(
        os.path.join(codex_home, "hooks.json"),
        CODEX_HOOK_TEMPLATE,
        os.path.join(codex_skill, "scripts", "math_gate.py"),
        "codex",
    )
    claude_hooks_changed = merge_owned_hooks(
        os.path.join(claude_home, "settings.json"),
        CLAUDE_HOOK_TEMPLATE,
        os.path.join(claude_skill, "scripts", "math_gate.py"),
        "claude",
    )
    ok, detail = verify_install(home, codex_home, claude_home, runtime_root)
    if not ok:
        raise RuntimeError(detail)
    return {
        "runtime": "installed" if runtime_changed else "exact",
        "skills": "installed" if codex_skill_changed or claude_skill_changed else "exact",
        "codex_hooks": "changed" if codex_hooks_changed else "exact",
        "claude_hooks": "changed" if claude_hooks_changed else "exact",
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--install", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--home")
    parser.add_argument("--codex-home")
    parser.add_argument("--claude-home")
    parser.add_argument("--runtime-root")
    args = parser.parse_args(argv)
    if args.install:
        result = install(args.home, args.codex_home, args.claude_home, args.runtime_root)
        print("math-tool|runtime=%s|skills=%s|codex-hooks=%s|claude-hooks=%s" % (
            result["runtime"], result["skills"], result["codex_hooks"], result["claude_hooks"]
        ))
        if result["codex_hooks"] == "changed":
            print("math-tool|review changed Codex hooks with /hooks; hooks do not self-approve")
        if result["claude_hooks"] == "changed":
            print("math-tool|review the changed Claude user settings under normal settings trust")
        return 0
    ok, detail = verify_install(args.home, args.codex_home, args.claude_home, args.runtime_root)
    print(detail)
    return 0 if ok else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        sys.stderr.write("math-tool setup: ERROR %s\n" % str(error)[:240])
        sys.exit(2)
