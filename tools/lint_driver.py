"""Shared lute-lint driver for the CST checker wrappers (replication_audit,
perf_audit). Handles the seam facts measured on the vendored 1.0.0 binary:
JSON mode exits 0 with findings present (count items, never read the code),
and the JSON range is 0-indexed (+1 both)."""

import json
import os
import subprocess
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(HARNESS, "shared", "gates"))
import gatelib  # noqa: E402
import houseout  # noqa: E402
import rule_policy  # noqa: E402

CACHE = os.path.expanduser("~/.cache/harness")
GLOBALS_PATH = os.path.join(CACHE, "api_globals.luau")
LUTE = gatelib.bundled_tool_path("lute")
SOURCE_SUFFIXES = (".lua", ".luau")


def gen_config(tool):
    os.makedirs(CACHE, exist_ok=True)
    globals_line = 'require("./api_globals")' if os.path.exists(GLOBALS_PATH) else "{}"
    path = os.path.join(CACHE, tool + ".config.luau")
    with open(path, "w", encoding="utf-8") as f:
        f.write("return {\n\tlute = {\n\t\tlint = {\n\t\t\tglobals = %s,\n\t\t},\n\t},\n}\n" % globals_line)
    return path


def scan(tool, rules_dir, argv, fails_open=False):
    root = os.getcwd()
    files = []
    i = 0
    while i < len(argv):
        if argv[i] == "--root" and i + 1 < len(argv):
            root = argv[i + 1]
            i += 2
        else:
            files.append(argv[i])
            i += 1
    if not files:
        print("usage: %s [--root DIR] <file...>" % tool)
        return 0
    if not os.path.exists(LUTE):
        print("%s: BLOCKED (ENV)\n\nENV|lute-absent|tools/get_toolchain.sh" % tool)
        return 3

    scannable = []
    for f in files:
        if os.path.islink(f):
            continue  # museum links are never read, linted, or reported on
        real = os.path.realpath(f)
        if os.path.isdir(real):
            for dirpath, dirnames, filenames in os.walk(real):
                dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
                for fn in sorted(filenames):
                    fp = os.path.join(dirpath, fn)
                    if fn.endswith(SOURCE_SUFFIXES) and not os.path.islink(fp):
                        scannable.append(fp)
        elif os.path.exists(real):
            if f.endswith(SOURCE_SUFFIXES):
                scannable.append(f)
        else:
            sys.stderr.write("%s: BLOCKED\n\n0|0|GATE4|%s absent|nothing was scanned\n" % (tool, f))
            return 2
    if not scannable:
        return 0

    cfg = gen_config(tool)
    r = subprocess.run(
        [LUTE, "lint", "--no-default-lints", "-r", rules_dir, "-c", cfg, "-j"] + scannable,
        capture_output=True,
        text=True,
    )
    stdout = r.stdout
    brace = stdout.find("{")
    try:
        report = json.loads(stdout[brace:] if brace >= 0 else stdout)
    except ValueError:
        sys.stderr.write("%s: BLOCKED\n\nlint output unparseable: %s\n" % (tool, (r.stderr or stdout)[:200]))
        return 2
    for line in stdout[: brace if brace >= 0 else 0].splitlines():
        if line.strip():
            sys.stderr.write("%s: %s\n" % (tool, line.strip()))

    known_rules = {
        os.path.splitext(name)[0]
        for name in os.listdir(rules_dir)
        if name.endswith(".luau")
    }
    findings = []
    for doc in report.get("items", []):
        uri = doc.get("uri", "")
        for item in doc.get("items", []):
            line = item["range"]["start"]["line"] + 1
            col = item["range"]["start"]["character"] + 1
            code = item.get("code", "void")
            subject, _, remedy = item.get("message", "").partition("|")
            if code not in known_rules:
                subject = "%s: %s" % (code, subject or "source diagnostic")
                remedy = "fix the source syntax or required checker"
                code = "GATE4"
            findings.append((uri, line, col, code, subject or "void", remedy or "void"))

    grouped = rule_policy.split_findings(findings)
    findings = grouped["hard"] + grouped["auto-fix"] + grouped["advisory"]
    if not findings:
        return 0
    if fails_open:
        # performance findings are recoverable by revert and the thresholds
        # advisory: warn, never block
        body = houseout.render_findings(tool, findings, root, blocked=False)
        sys.stdout.write("%s: NOTED\n\n%s" % (tool, body))
        return 0
    blocking = grouped["hard"] + grouped["auto-fix"]
    if grouped["advisory"]:
        body = houseout.render_findings(tool, grouped["advisory"], root, blocked=False)
        sys.stdout.write("%s: NOTED\n\n%s" % (tool, body))
    if blocking:
        sys.stderr.write(houseout.render_findings(tool, blocking, root))
        return 2
    return 0
