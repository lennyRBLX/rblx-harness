"""Shared StudioMCP seam for the Python Studio tools.

Every standalone tool must spawn its own StudioMCP instance over stdio —
measured: a spawned instance answers initialize, returns all
tools, and reaches every open Studio; a second TCP client on the singleton's
port cannot be used. Selection is explicit: the proxy manages several Studios
and picks one by heuristic unless told, so every Studio-touching tool runs
list_roblox_studios -> set_active_studio -> verify game.PlaceId before
anything else.

Also owns the per-place lock: boot_smoke, map_census and rig_clean serialize
per open place through ~/.cache/harness/studio-<PlaceId>.lock.
"""

import json
import os
import queue
import shlex
import subprocess
import threading
import time

from studio_mcp_launcher import find_studio_mcp

DEFAULT_MCP_CMD = find_studio_mcp() or "/Applications/RobloxStudio.app/Contents/MacOS/StudioMCP"
CACHE = os.path.expanduser("~/.cache/harness")
LOCK_MAX_AGE = 3600  # no run of the three lock holders lasts an hour
STUDIO_DISCOVERY_TIMEOUT = 5


class EnvError(Exception):
    def __init__(self, cause, remedy):
        super().__init__("%s: %s" % (cause, remedy))
        self.cause = cause
        self.remedy = remedy


class StudioRPC:
    def __init__(self, mcp_cmd=None, timeout=30):
        self.cmd = mcp_cmd or DEFAULT_MCP_CMD
        self.timeout = timeout
        self.proc = None
        self.next_id = 0
        self._stdout_lines = queue.Queue()
        self._stdout_reader = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def start(self):
        if isinstance(self.cmd, (list, tuple)):
            command = list(self.cmd)
        elif os.path.exists(self.cmd):
            command = [self.cmd]
        else:
            command = shlex.split(self.cmd, posix=os.name != "nt")
            command = [part.strip('"') for part in command]
        if not command or not os.path.exists(command[0]):
            raise EnvError("studiomcp-absent", "Install or repair Roblox Studio, then retry.")
        try:
            self.proc = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except OSError as e:
            raise EnvError("studiomcp-spawn-failed", "Install or repair Roblox Studio, then retry.")
        self._stdout_lines = queue.Queue()
        self._stdout_reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._stdout_reader.start()
        self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "harness", "version": "1.0"},
            },
        )
        self._notify("notifications/initialized")

    def close(self):
        if self.proc:
            try:
                self.proc.stdin.close()
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()
            self.proc = None

    def _read_stdout(self):
        """Move blocking pipe reads off the deadline-bearing request thread."""
        try:
            while self.proc and self.proc.stdout:
                line = self.proc.stdout.readline()
                if line == "":
                    break
                self._stdout_lines.put(line)
        finally:
            self._stdout_lines.put(None)

    def _notify(self, method, params=None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def _request(self, method, params=None):
        self.next_id += 1
        rid = self.next_id
        msg = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        try:
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            raise EnvError("studiomcp-unreachable", "Restart Roblox Studio, open the project place, enable MCP, then retry.")
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            try:
                line = self._stdout_lines.get(timeout=max(0, remaining))
            except queue.Empty:
                break
            if line is None:
                raise EnvError("studiomcp-unreachable", "Restart Roblox Studio, open the project place, enable MCP, then retry.")
            line = line.strip()
            if not line:
                continue
            try:
                resp = json.loads(line)
            except ValueError:
                continue
            if resp.get("id") == rid:
                if "error" in resp:
                    raise EnvError("studiomcp-error", str(resp["error"].get("message", resp["error"])))
                return resp.get("result")
        raise EnvError(
            "studiomcp-timeout",
            "Restart Roblox Studio, open the project place, enable MCP, then retry.",
        )

    def tools_list(self):
        result = self._request("tools/list") or {}
        return [t.get("name", "") for t in result.get("tools", [])]

    def call(self, name, arguments=None):
        result = self._request("tools/call", {"name": name, "arguments": arguments or {}})
        texts = []
        for item in (result or {}).get("content", []):
            if item.get("type") == "text":
                texts.append(item.get("text", ""))
        return "\n".join(texts)

    # -------------------------------------------------------- studio pick --

    def list_studios(self):
        raw = self.call("list_roblox_studios")
        studios = []
        try:
            data = json.loads(raw)
            records = data.get("studios", []) if isinstance(data, dict) else data
            if isinstance(records, list):
                for s in records:
                    studios.append({"id": str(s.get("id")), "name": s.get("name", ""), "active": bool(s.get("active"))})
        except ValueError:
            pass
        if not studios:
            for m in __import__("re").finditer(r"(\d{6,})\s+(\S[^\n]*)", raw):
                studios.append({"id": m.group(1), "name": m.group(2).strip(), "active": False})
        return studios

    def read_place_id(self):
        out = self.call("execute_luau", {"code": "return game.PlaceId", "datamodel_type": "Edit"}).strip()
        if not out.isdigit():
            raise EnvError("no-place", "Open the project place in Roblox Studio, then retry.")
        return int(out)

    def select_studio(self, wanted_place_ids):
        """list -> per id set_active_studio + read game.PlaceId -> keep the id
        whose PlaceId matches this project's places map. No match -> refuse.
        game.Name is useless as a discriminator (measured: "Place1" on both).
        Returns (studio_id, place_id)."""
        deadline = time.time() + min(self.timeout, STUDIO_DISCOVERY_TIMEOUT)
        studios = []
        while not studios and time.time() < deadline:
            studios = self.list_studios()
            if not studios:
                time.sleep(min(0.1, max(0, deadline - time.time())))
        if not studios:
            raise EnvError(
                "no-studio",
                "Open the project place and enable MCP in Roblox Studio Assistant Settings, then retry.",
            )
        seen = {}
        matches = []
        for s in studios:
            self.call("set_active_studio", {"studio_id": s["id"]})
            try:
                pid = self.read_place_id()
            except EnvError:
                continue
            seen[s["id"]] = pid
            if pid == 0:
                continue  # unpublished; nothing to key on
            if not wanted_place_ids or pid in wanted_place_ids:
                matches.append((s["id"], pid))
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise EnvError("ambiguous-studio", "Close other Roblox Studio places, keep the project place open, then retry.")
        if seen and all(place_id == 0 for place_id in seen.values()):
            raise EnvError("unpublished-place", "Publish the project place in Roblox Studio, then retry.")
        detail = ", ".join("%s=%s" % kv for kv in seen.items()) or "none readable"
        raise EnvError("wrong-place", "Open the project place in Roblox Studio, then retry.")


# ------------------------------------------------------------------- locks --


def lock_path(place_id):
    return os.path.join(CACHE, "studio-%d.lock" % place_id)


def acquire_lock(place_id, session_id, tool):
    """Fail fast, never wait. Stale locks reclaim two ways: pid gone, or older
    than an hour — age is the only signal that survives a reboot."""
    os.makedirs(CACHE, exist_ok=True)
    path = lock_path(place_id)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                held = json.load(f)
        except (OSError, ValueError):
            held = {}
        age = time.time() - held.get("timestamp", 0)
        pid = held.get("pid", -1)
        pid_alive = False
        if isinstance(pid, int) and pid > 0:
            try:
                os.kill(pid, 0)
                pid_alive = True
            except OSError:
                pid_alive = False
        if pid_alive and age < LOCK_MAX_AGE:
            raise EnvError(
                "studio-busy",
                "%s holds the lock on place %d - rerun after it finishes" % (held.get("session_id", "unknown"), place_id),
            )
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"session_id": session_id, "pid": os.getpid(), "tool": tool, "timestamp": time.time()}, f)
    return path


def release_lock(place_id):
    try:
        os.remove(lock_path(place_id))
    except OSError:
        pass
