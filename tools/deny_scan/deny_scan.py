#!/usr/bin/env python3
"""deny_scan — a CLI over eight lint rules, one per rule id, sharing one entry
table. Content-level absolutes, blocked at write-gate with a deny's finality.

  deny_scan [--root DIR] <file...>
    -> lute lint --no-default-lints --rules <deny_rules/> -j <files>
    -> parse JSON, +1 line/col, sort by line/col/id
    -> exit 2 on any finding, unparseable file, or missing/malformed table
    -> exit 0 clean, silent

--no-default-lints is load-bearing: without it lute's built-ins run alongside
and unused_variable starts blocking writes under deny_scan's exit 2.
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
HARNESS = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(HARNESS, "shared", "gates"))
import gatelib  # noqa: E402
import houseout  # noqa: E402
import rule_policy  # noqa: E402

CACHE = os.path.expanduser("~/.cache/harness")
GLOBALS_PATH = os.path.join(CACHE, "api_globals.luau")
LUTE = gatelib.bundled_tool_path("lute")
RULES = os.path.join(HERE, "rules")
RULE_IDS = ["BC3", "WRIT18", "DATA29", "OPT11", "WRIT11", "BC1", "OPT12", "BC7"]


def gen_config():
    """Generate the lint config beside api_globals.luau so `require` stays
    same-directory for the globals and repo-relative for the table (absolute
    requires are rejected by Luau's require-by-string)."""
    os.makedirs(CACHE, exist_ok=True)
    rel_table = os.path.relpath(os.path.join(HERE, "deny_table"), CACHE).replace(os.sep, "/")
    if not rel_table.startswith("."):
        rel_table = "./" + rel_table
    globals_line = 'require("./api_globals")' if os.path.exists(GLOBALS_PATH) else "{}"
    rule_lines = "\n".join('\t\t\t\t%s = { options = deny.%s },' % (rid, rid) for rid in RULE_IDS)
    cfg = (
        'local deny = require("%s")\n'
        "return {\n"
        "\tlute = {\n"
        "\t\tlint = {\n"
        "\t\t\tglobals = %s,\n"
        "\t\t\truleconfigs = {\n"
        "%s\n"
        "\t\t\t},\n"
        "\t\t},\n"
        "\t},\n"
        "}\n" % (rel_table, globals_line, rule_lines)
    )
    path = os.path.join(CACHE, "deny_scan.config.luau")
    with open(path, "w", encoding="utf-8") as f:
        f.write(cfg)
    return path


def main(argv):
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
        print(__doc__.strip())
        return 0

    if not os.path.exists(LUTE):
        print("Install the harness toolchain, verify it, and retry: %s" % os.path.join(TOOLS, "get_toolchain.sh"))
        return 3

    # the table must parse and every entry carry its fields — a silently-empty
    # options table would degrade every rule to matching nothing
    r = subprocess.run([LUTE, "run", os.path.join(HERE, "check_table.luau")], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.startswith("ok "):
        sys.stderr.write("Fix %s → retry.\n" % os.path.join(HERE, "deny_table.luau"))
        return 2

    # symlink filter — museum links are never read, linted, or reported on;
    # project-made files beside them are. Only resolving the path tells them
    # apart, which is why there is no Packages/ glob anywhere.
    scannable = []
    for f in files:
        if os.path.islink(f):
            continue
        real = os.path.realpath(f)
        if os.path.isdir(real):
            continue
        if not os.path.exists(real):
            sys.stderr.write("Restore %s → retry.\n" % f)
            return 2
        scannable.append(f)
    if not scannable:
        return 0

    cfg = gen_config()
    r = subprocess.run(
        [LUTE, "lint", "--no-default-lints", "-r", RULES, "-c", cfg, "-j"] + scannable,
        capture_output=True,
        text=True,
    )
    # JSON mode exits 0 with findings present — count items, never read the code
    try:
        report = json.loads(r.stdout)
    except ValueError:
        sys.stderr.write("Fix deny_scan output parsing → retry.\n")
        return 2

    findings = []
    for doc in report.get("items", []):
        uri = doc.get("uri", "")
        for item in doc.get("items", []):
            line = item["range"]["start"]["line"] + 1
            col = item["range"]["start"]["character"] + 1
            code = item.get("code", "void")
            msg = item.get("message", "")
            subject, _, remedy = msg.partition("|")
            if code not in RULE_IDS:
                subject = "%s: %s" % (code, subject or msg or "source diagnostic")
                remedy = "fix the source syntax or required checker"
                code = "GATE4"
            findings.append((uri, line, col, code, subject or "void", remedy or "void"))

    if not os.path.exists(GLOBALS_PATH):
        sys.stderr.write(
            "Generate API globals, verify them, and retry: python3 %s --emit-globals\n"
            % os.path.join(TOOLS, "api_dump", "api_dump.py")
        )
        return 3
    grouped = rule_policy.split_findings(findings)
    blocking = grouped["hard"] + grouped["auto-fix"]
    advisory = grouped["advisory"]
    if advisory:
        sys.stdout.write(
            "deny_scan: NOTED\n\n"
            + houseout.render_findings("deny_scan", advisory, root, blocked=False)
        )
    if blocking:
        sys.stderr.write(houseout.render_findings("deny_scan", blocking, root))
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as e:
        sys.stderr.write("Run deny_scan; fix the err; retry.\n")
        sys.exit(2)
