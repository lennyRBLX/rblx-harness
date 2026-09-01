#!/usr/bin/env python3
"""Repair BC3 and TYPE3 with a parse-verified, idempotent transform."""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
DENY_SCAN = os.path.join(TOOLS, "deny_scan", "deny_scan.py")

PRAGMA_RE = re.compile(r"^\s*--!(?:strict|nonstrict|nocheck)\b")
FINDING_RE = re.compile(r"^(\d+)\|(\d+)\|([^|]+)\|([^|]+)\|(.*)$")


def _run_scan(path, root):
    try:
        return subprocess.run(
            [sys.executable, DENY_SCAN, "--root", root, path],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as error:
        return subprocess.CompletedProcess([], 3, "", "%s: %s" % (type(error).__name__, error))


def _bc3_findings(result):
    findings = []
    for line in (result.stderr or "").splitlines():
        match = FINDING_RE.match(line)
        if match and match.group(3) == "BC3":
            findings.append((int(match.group(1)), int(match.group(2)), match.group(4)))
    return findings


def _required_failures(result):
    return [
        match.group(4)
        for line in (result.stderr or "").splitlines()
        for match in [FINDING_RE.match(line)]
        if match and match.group(3) == "GATE4"
    ]


def _scan_parsed(result):
    return result.returncode == 0 or any(
        FINDING_RE.match(line) for line in (result.stderr or "").splitlines()
    )


def _remove_pragmas(text):
    lines = text.splitlines(keepends=True)
    kept = [line for line in lines if not PRAGMA_RE.match(line)]
    return "".join(kept), len(lines) - len(kept)


def _replace_bc3(text, findings):
    lines = text.splitlines(keepends=True)
    grouped = {}
    for line, column, name in findings:
        if name not in ("wait", "spawn", "delay"):
            return None, "BC3 returned an unknown legacy global"
        grouped.setdefault(line, []).append((column, name))
    for line_number, edits in grouped.items():
        if line_number < 1 or line_number > len(lines):
            return None, "BC3 returned an invalid source line"
        source_line = lines[line_number - 1]
        for column, name in sorted(edits, reverse=True):
            offset = column - 1
            if offset < 0 or source_line[offset : offset + len(name)] != name:
                return None, "BC3 source location does not match the parsed token"
            source_line = source_line[:offset] + "task." + name + source_line[offset + len(name) :]
        lines[line_number - 1] = source_line
    return "".join(lines), ""


def fix_text(text, root):
    """Return ``(fixed_text, changed_ids, error)`` without writing the source."""
    fixed, pragma_count = _remove_pragmas(text)
    changed = {"TYPE3"} if pragma_count else set()
    with tempfile.TemporaryDirectory(prefix="source_fix_") as temporary:
        path = os.path.join(temporary, "Source.luau")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(fixed)
        first = _run_scan(path, root)
        if first.returncode == 3:
            return text, set(), (first.stdout or first.stderr or "deny_scan unavailable").strip()[:200]
        if _required_failures(first):
            return text, set(), _required_failures(first)[0][:200]
        if not _scan_parsed(first):
            return text, set(), (first.stderr or first.stdout or "source parse failed").strip()[:200]
        bc3 = _bc3_findings(first)
        if bc3:
            replaced, error = _replace_bc3(fixed, bc3)
            if error:
                return text, set(), error
            fixed = replaced
            changed.add("BC3")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(fixed)
        second = _run_scan(path, root)
        if second.returncode == 3:
            return text, set(), (second.stdout or second.stderr or "deny_scan unavailable").strip()[:200]
        if _required_failures(second):
            return text, set(), _required_failures(second)[0][:200]
        if not _scan_parsed(second):
            return text, set(), (second.stderr or second.stdout or "source parse failed").strip()[:200]
        if _bc3_findings(second):
            return text, set(), "BC3 remained after its deterministic repair"
        # Lute parsed the fixed file on the second scan. A second transform must
        # be a byte no-op.
        twice, twice_pragmas = _remove_pragmas(fixed)
        if twice_pragmas or twice != fixed:
            return text, set(), "source repair is not idempotent"
    return fixed, changed, ""


def fix_file(path, root):
    try:
        with open(path, encoding="utf-8") as handle:
            original = handle.read()
    except OSError as error:
        return set(), str(error)[:200]
    fixed, changed, error = fix_text(original, root)
    if error or not changed:
        return changed, error
    temporary = path + ".sourcefix"
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            handle.write(fixed)
        shutil.copymode(path, temporary)
        os.replace(temporary, path)
    except OSError as write_error:
        try:
            os.remove(temporary)
        except OSError:
            pass
        return set(), str(write_error)[:200]
    return changed, ""


def main(argv=None):
    parser = argparse.ArgumentParser(prog="source_fix")
    parser.add_argument("path")
    parser.add_argument("--root", default=os.getcwd())
    args = parser.parse_args(argv)
    changed, error = fix_file(os.path.realpath(args.path), os.path.realpath(args.root))
    if error:
        print("source_fix: BLOCKED|%s" % " ".join(error.split()))
        return 2
    print("source_fix:%s" % ("fixed|" + ",".join(sorted(changed)) if changed else "clean"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
