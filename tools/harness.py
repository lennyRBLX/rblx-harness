#!/usr/bin/env python3
"""Roblox domain tools. Native shell, search, editing, and Git remain available.

Usage: python3 tools/harness.py [--root PROJECT] FAMILY [ACTION] [ARGS...]
Use FAMILY --help for only that family's commands. Arguments and exit codes
pass through to the existing implementations; no shell command is constructed.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
HELP = {
    "api": """api access CLASS[.MEMBER] | inventory CLASS | behavior TOPIC
api batch VERB QUERY [VERB QUERY ...]
api docs QUERY | doc PATH | code PATH | find QUERY
api --sync | --emit-globals | --check-overlay
Returns sourced engine evidence; --sync refreshes the local cache over the network.
Other legacy API lookup verbs remain available.""",
    "types": """types read --type TYPE_NAME [--type OTHER_TYPE ...]
types read --service-type OWNER:TYPE | --controller-type OWNER:TYPE
types read --service NAME | --controller NAME | --project | --affected GIT_REF
types write --request-file FILE | --request JSON | --request -
types cache ensure | verify | recover
Write requests contain operations for public/service/controller types or data.
Read shared/TOOLS.md#types for fields. Writes validate the batch and roll back on
failure. Cache commands can write cache files; recover can restore source files.""",
    "check": """check source [--only correctness,replication,style,performance] PATH...
check project
check harness [--case MATCH ...] [--list]
Source checks are read-only on project source and write tool caches. Each selected
checker runs once. No Studio run or source repair is implicit. Harness checks run
the full suite unless --case selects a subset. Missing tools are failures.
Correctness includes profile/parallel pairing and literal codec advisories;
replication includes unreliable remotes. Style accepts const bindings.""",
    "inspect": """inspect read --file PATH[:FIRST:LAST] [--file PATH ...]
inspect diff --path PATH [--path PATH ...] [--base REF]
Both accept --max-chars N, --since PACK, and --no-cache. Full evidence is saved
outside the repository unless --no-cache is selected. Truncation is reported.
inspect session --project NAME --output REPORT_STEM
Session audit reads local rollouts; visible payload estimates are not billing.""",
    "profile": """profile frames CAPTURE_STEM [--downloads DIR]
profile luau --from-json FILE [FILE ...]
profile luau --emit-harness server|client|both [--seconds N] [--frequency HZ]
Analyze saved MicroProfiler exports or emit a diagnostic snippet. Emission does
not execute the snippet. Compare only equivalent captures.""",
    "studio": """studio output --studio-id ID [--since SNAPSHOT] [--contains TEXT]
studio output --input LOG [--since SNAPSHOT] [--contains TEXT]
studio boot [--project FILE] [--console-log FILE] [--play-seconds N]
studio map | census | clean [--delete]
Output reads logs. Boot starts/stops Play unless a saved log is supplied. Map
writes place mappings; census inspects instances. Clean only scans unless --delete
is supplied. Use the selected environment and existing execution authorization.
Run the underlying tool's documented options for --mcp-cmd and --session.""",
    "scaffold": """scaffold module KIND NAME [--place PLACE] [--side server|client]
scaffold module --test MODE.NAME --place PLACE [--side server|client]
scaffold module --expand NAME [--place PLACE]
scaffold project inspect | answer FIELD VALUE | status | emit
scaffold dependency status | setup --yes | init
Module writes frames; project uses recorded choices; dependency setup installs
the approved Git submodule. Read rblx-new-game for a new project.""",
}
# Backend paths and root flags are internal; help exposes task-oriented commands.
ROUTES = {
    ("api", ""): ("tools/api_dump/api_dump.py", None),
    ("types", "read"): ("tools/type_lookup/type_lookup.py", "--root"),
    ("types", "write"): ("tools/type_write/type_write.py", "--root"),
    ("types", "cache"): ("tools/type_cache/type_cache.py", "--root"),
    ("check", "project"): ("tools/project_gate/project_gate.py", "--project-root"),
    ("check", "harness"): ("tools/tests/run_verify.py", None),
    ("inspect", "read"): ("tools/context_pack.py", "--root"),
    ("inspect", "diff"): ("tools/context_pack.py", "--root"),
    ("inspect", "session"): ("tools/session_audit.py", None),
    ("profile", "frames"): ("tools/frame_census/frame_census.py", "--root"),
    ("profile", "luau"): ("tools/luau_hotspot/luau_hotspot.py", None),
    ("studio", "output"): ("tools/studio_output.py", None),
    ("studio", "boot"): ("tools/boot_smoke/boot_smoke.py", "--root"),
    ("studio", "map"): ("tools/place_map/place_map.py", "--root"),
    ("studio", "census"): ("tools/map_census/map_census.py", "--root"),
    ("studio", "clean"): ("tools/rig_clean/rig_clean.py", "--root"),
    ("scaffold", "module"): ("tools/create_boilerplate/create_boilerplate.py", "--root"),
    ("scaffold", "project"): ("shared/skills/rblx-new-game/scripts/scaffold.py", "--root"),
    ("scaffold", "dependency"): ("shared/skills/rblx-new-game/scripts/dependency.py", "--root"),
}
CHECKS = {
    "correctness": "tools/deny_scan/deny_scan.py",
    "replication": "tools/replication_audit/replication_audit.py",
    "style": "tools/style_assess/style_assess.py",
    "performance": "tools/perf_audit/perf_audit.py",
}


def command_for(family, action, args, root):
    """Resolve a fixed backend, preserving argv elements and input boundaries."""
    relative, root_flag = ROUTES[(family, action)]
    forwarded = list(args)
    if family == "inspect" and action in ("read", "diff"):
        # context_pack has global flags before its subparser.
        options, remaining = [], []
        index = 0
        while index < len(forwarded):
            token = forwarded[index]
            if token == "--no-cache":
                options.append(token)
            elif token in ("--max-chars", "--since"):
                if index + 1 == len(forwarded):
                    raise ValueError(token + " needs a value")
                options.extend(forwarded[index:index + 2])
                index += 1
            elif token.startswith(("--max-chars=", "--since=")):
                options.append(token)
            else:
                remaining.append(token)
            index += 1
        forwarded = options + [action] + remaining
    if root_flag:
        if any(arg == root_flag or arg.startswith(root_flag + "=") for arg in forwarded):
            raise ValueError("place --root before the command family")
        forwarded = [root_flag, str(root)] + forwarded
    return [sys.executable, "-B", str(ROOT / relative), *forwarded]


def source_files(root, paths):
    """Expand once, omit dependency links, and preserve deterministic order."""
    root = root.resolve()
    selected = set()
    for name in paths:
        path = Path(os.path.abspath(root / name))
        if not path.is_relative_to(root):
            raise ValueError("source path is outside --root: " + name)
        if not path.exists():
            raise ValueError("source path is absent: " + name)
        if any(p.is_symlink() for p in (path, *path.parents) if p.is_relative_to(root)):
            continue
        if path.is_file():
            candidates = [path]
        else:
            candidates = []
            for directory, dirs, files in os.walk(path):
                dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink())
                candidates.extend(Path(directory) / f for f in files)
        selected.update(p.resolve() for p in candidates
                        if p.suffix in (".luau", ".lua") and not p.is_symlink())
    if not selected:
        raise ValueError("no owned Luau source files in the selected paths")
    return sorted(selected)


def check_source(args, root):
    parser = argparse.ArgumentParser(prog="harness check source")
    parser.add_argument("--only", default="correctness,replication,style")
    parser.add_argument("paths", nargs="+")
    options = parser.parse_args(args)
    selected = list(dict.fromkeys(options.only.split(",")))
    if any(name not in CHECKS for name in selected):
        parser.error("--only accepts: " + ",".join(CHECKS))
    files = source_files(root, options.paths)
    statuses = []
    for name in selected:
        result = subprocess.run([sys.executable, "-B", str(ROOT / CHECKS[name]),
                                 "--root", str(root), *map(str, files)], cwd=root)
        statuses.append(result.returncode)
        print("check|%s|exit=%d" % (name, result.returncode), flush=True)
    return 3 if 3 in statuses else 2 if any(statuses) else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, epilog="Families: " + ", ".join(HELP))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("family", nargs="?", choices=HELP)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    options = parser.parse_args(argv)
    if options.family is None:
        parser.print_help()
        return 0
    args = options.arguments
    if not args or args == ["--help"] or args[-1:] == ["--help"]:
        print(HELP[options.family])
        return 0
    family = options.family
    action = "" if family == "api" else args.pop(0)
    root = options.root.expanduser().resolve()
    try:
        if not root.is_dir():
            raise ValueError("project root is not a directory: " + str(root))
        if family == "check" and action == "source":
            return check_source(args, root)
        if (family, action) not in ROUTES:
            raise ValueError("unknown action; use " + family + " --help")
        command = command_for(family, action, args, root)
        os.chdir(root)
        # Replace this process: one dispatch, no extra Python supervisor per tool.
        os.execv(command[0], command)
    except (OSError, ValueError) as error:
        print("harness: " + str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
