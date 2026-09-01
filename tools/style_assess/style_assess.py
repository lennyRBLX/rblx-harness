#!/usr/bin/env python3
"""style_assess — the style lint and the formatter.

  style_assess [--root DIR] [--fix] [--now EPOCH] [--ignore GLOB]... <path...>

Lint: 20 rules under lute lint, findings as house records, exit 2.
--fix: repairs style in place rather than reporting it — the fix_pass
transform (WRIT14, WRIT12, BC5 tabs), then --auto-fix (WRIT15, WRIT22), then
a re-check that reports only what --fix could not repair. The write is
atomic: temp file, parse-verify (inside fix_pass), rename.

Roots are shared/src/ and places/<Place>/src/; tests/ is outside both, so
diagnostic code is never linted. Required lint and repair failures fail closed
for the source operation that invoked them.
"""

import fnmatch
import json
import os
import shutil
import subprocess
import sys
import tempfile

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
AUTOFIX = os.path.join(HERE, "autofix")
FIX_PASS = os.path.join(HERE, "fix_pass.luau")

GLOBALS_FED = ["WRIT25", "WRIT29", "WRIT30", "WRIT23", "WRIT31"]
SOURCE_SUFFIXES = (".lua", ".luau")


def gen_config(now=None, updates_dir=None):
    os.makedirs(CACHE, exist_ok=True)
    globals_line = 'require("./api_globals")' if os.path.exists(GLOBALS_PATH) else "{}"
    entries = [
        'WRIT29 = { options = { except = { "GetService", "FindFirstChild", "FindFirstChildOfClass", "FindFirstChildWhichIsA", "FindFirstAncestor", "FindFirstDescendant" } } },'
    ]
    if now is not None:
        entries.append("DES5 = { options = { now = %d } }," % int(now))
    rulecfg = "\t\t\truleconfigs = {\n" + "".join("\t\t\t\t%s\n" % e for e in entries) + "\t\t\t},\n"
    cfg = (
        "return {\n"
        "\tlute = {\n"
        "\t\tlint = {\n"
        "\t\t\tglobals = %s,\n"
        "%s"
        "\t\t},\n"
        "\t},\n"
        "}\n" % (globals_line, rulecfg)
    )
    path = os.path.join(CACHE, "style_assess.config.luau")
    with open(path, "w", encoding="utf-8") as f:
        f.write(cfg)
    return path


def run_lint(rules_dir, cfg, files, auto_fix=False):
    cmd = [LUTE, "lint", "--no-default-lints", "-r", rules_dir, "-c", cfg, "-j"]
    if auto_fix:
        cmd.append("--auto-fix")
    r = subprocess.run(cmd + files, capture_output=True, text=True)
    # a rule that errors prints "Error applying lint rule ..." before the
    # JSON; the report is still whole, so parse from the first brace
    stdout = r.stdout
    brace = stdout.find("{")
    try:
        report = json.loads(stdout[brace:] if brace >= 0 else stdout)
    except ValueError:
        return None, r.stdout + r.stderr
    for line in stdout[:brace if brace >= 0 else 0].splitlines():
        if line.strip():
            sys.stderr.write("style_assess: " + line.strip() + "\n")
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
    return findings, None


def style_scoped(path):
    """tests/ sits outside the style roots — diagnostic code is never linted."""
    norm = os.path.abspath(path).replace(os.sep, "/")
    return "/tests/" not in norm + "/"


def collect_files(paths, root, ignores):
    out = []
    for p in paths:
        full = p if os.path.isabs(p) else os.path.join(root, p)
        if os.path.islink(full):
            continue
        if os.path.isdir(full):
            for dirpath, dirnames, filenames in os.walk(full):
                dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
                for fn in sorted(filenames):
                    fp = os.path.join(dirpath, fn)
                    if fn.endswith(SOURCE_SUFFIXES) and not os.path.islink(fp):
                        out.append(fp)
        elif full.endswith(SOURCE_SUFFIXES) and os.path.exists(full):
            out.append(full)
    kept = []
    for f in out:
        rel = os.path.relpath(f, root).replace(os.sep, "/")
        if any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch("/" + rel, g) for g in ignores):
            continue
        if not style_scoped(f):
            continue
        kept.append(f)
    return kept


def fix_file(path, cfg):
    """fix_pass transform -> --auto-fix -> atomic rename. Returns (ids, error)."""
    fired = set()
    tmp_dir = tempfile.mkdtemp(prefix="style_fix_")
    tmp = os.path.join(tmp_dir, os.path.basename(path))
    try:
        shutil.copy2(path, tmp)
        r = subprocess.run([LUTE, "run", FIX_PASS, tmp, tmp], capture_output=True, text=True)
        if r.returncode != 0:
            return None, (r.stderr.strip() or r.stdout.strip())[:200]
        line = r.stdout.strip().split("\n")[-1] if r.stdout.strip() else "clean"
        if line.startswith("changed|"):
            fired.update(line.split("|", 1)[1].split(","))
        pre, err = run_lint(AUTOFIX, cfg, [tmp])
        if err is not None:
            return None, err[:200]
        auto_ids = {f[3] for f in pre if f[3] in ("WRIT15", "WRIT22")}
        if auto_ids:
            _, err = run_lint(AUTOFIX, cfg, [tmp], auto_fix=True)
            if err is not None:
                return None, err[:200]
            fired.update(auto_ids)
            # parse-verify the auto-fixed bytes before they replace the original
            r2 = subprocess.run([LUTE, "run", FIX_PASS, tmp, tmp], capture_output=True, text=True)
            if r2.returncode != 0:
                return None, "auto-fix broke the parse: " + (r2.stderr.strip())[:150]
            # Lute's --auto-fix report is not a repair postcondition: it may
            # describe the pre-fix diagnostics, and a suggestion can be
            # unavailable.  Re-run both required rules against the bytes that
            # would actually replace the source.
            remaining, err = run_lint(AUTOFIX, cfg, [tmp])
            if err is not None:
                return None, err[:200]
            remaining_ids = sorted({f[3] for f in remaining if f[3] in ("WRIT15", "WRIT22")})
            if remaining_ids:
                return None, "required repair remained: " + ", ".join(remaining_ids)
        with open(tmp, "rb") as f:
            new = f.read()
        with open(path, "rb") as f:
            old = f.read()
        if new != old:
            final = path + ".stylefix"
            shutil.copy2(tmp, final)
            os.replace(final, path)
        else:
            fired = set()
        return sorted(fired), None
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main(argv):
    root = os.getcwd()
    fix = False
    now = None
    ignores = []
    paths = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--root" and i + 1 < len(argv):
            root = argv[i + 1]
            i += 2
        elif a == "--fix":
            fix = True
            i += 1
        elif a == "--now" and i + 1 < len(argv):
            now = argv[i + 1]
            i += 2
        elif a == "--ignore" and i + 1 < len(argv):
            ignores.append(argv[i + 1])
            i += 2
        else:
            paths.append(a)
            i += 1
    if not paths:
        print(__doc__.strip())
        return 0
    if not os.path.exists(LUTE):
        print("style_assess: BLOCKED (ENV)\n\nENV|lute-absent|tools/get_toolchain.sh")
        return 3

    files = collect_files(paths, root, ignores)
    if not files:
        return 0
    if not os.path.exists(GLOBALS_PATH):
        sys.stderr.write(
            "style_assess: BLOCKED\n\n"
            "0|0|GATE4|required API globals unavailable for %s|"
            "run api_dump --emit-globals, then retry\n"
            % " ".join(GLOBALS_FED)
        )
        return 3
    cfg = gen_config(now)
    pre_lines = []

    fix_errors = []
    if fix:
        formatted = 0
        for f in files:
            ids, err = fix_file(f, cfg)
            if err is not None:
                fix_errors.append("%s - %s" % (houseout.elide(f, root), err))
            elif ids:
                formatted += 1
                print("%s: formatted (%s)" % (houseout.elide(f, root), ", ".join(ids)))
        if formatted:
            print("style_assess: formatted %d files" % formatted)

    findings, err = run_lint(RULES, cfg, files)
    if findings is None:
        sys.stderr.write("style_assess: BLOCKED\n\nlint output unparseable: %s\n" % (err or "")[:200])
        return 2
    grouped = rule_policy.split_findings(findings)
    blocking = list(grouped["hard"])
    if grouped["auto-fix"]:
        # In --fix mode these records mean the bounded repair did not establish
        # its postcondition. Lint-only callers receive the same actionable
        # result without an implicit write.
        blocking.extend(grouped["auto-fix"])
    if grouped["advisory"]:
        noted = houseout.render_findings(
            "style_assess",
            grouped["advisory"],
            root,
            blocked=False,
            pre_lines=pre_lines,
        )
        sys.stdout.write("style_assess: NOTED\n\n" + noted)
        pre_lines = []
    if blocking:
        sys.stderr.write(
            houseout.render_findings(
                "style_assess",
                blocking,
                root,
                pre_lines=pre_lines,
            )
        )
        return 2
    if fix_errors:
        sys.stderr.write(
            "style_assess: BLOCKED\n\n0|0|GATE4|required style repair failed|%s\n"
            % " / ".join(fix_errors)[:300].replace("|", "/")
        )
        return 3
    if pre_lines:
        sys.stdout.write("\n".join(pre_lines) + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as e:
        sys.stderr.write("style_assess: CRASH %s: %s - nothing was scanned\n" % (type(e).__name__, e))
        sys.exit(2)
