#!/usr/bin/env python3
"""data_write — atomic paired write to both data modules. Separate --default
and --dev, dev required: shape pairs and values never do, so supplying one
would mean inventing the other. No --owner: DATA1 mandates the same-named
key, so ownership is derivable.

  data_write <Key.Path> --default <lit> --dev <lit> [--root DIR]

Process — refuse first, write last:
  1  read both modules, apply the edit to each in memory
  2  data_check --load over both resulting modules (in the core)
  3  type parity across the pair, every key
  4  data_shape_diff — refuse configured hard boundaries and report schema
     compatibility notes without requiring human approval
  5  generate the export type in Default.luau from the validated shape
  6  only then write: both temps, verify parse, rename Default then
     Development; if the second rename fails, restore the first; if the
     restore also fails, exit 2 naming both files and the key.
"""

import os
import re
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

LUTE = gatelib.bundled_tool_path("lute")
CORE = os.path.join(HERE, "data_write_core.luau")
SHAPE_DIFF = os.path.join(TOOLS, "data_shape_diff", "data_shape_diff.luau")


def main(argv):
    root = os.getcwd()
    keypath = None
    default_lit = None
    dev_lit = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--default" and i + 1 < len(argv):
            default_lit = argv[i + 1]
            i += 2
        elif a == "--dev" and i + 1 < len(argv):
            dev_lit = argv[i + 1]
            i += 2
        elif a == "--root" and i + 1 < len(argv):
            root = argv[i + 1]
            i += 2
        elif keypath is None:
            keypath = a
            i += 1
        else:
            i += 1
    if not keypath or default_lit is None or dev_lit is None:
        # --dev is required: shape pairs across the two modules and values
        # never do
        print(__doc__.strip())
        return 2
    if not os.path.exists(LUTE):
        print("data_write: REFUSED\n\n0|0|GATE4|lute absent|tools/get_toolchain.sh")
        return 3

    pd_dir = os.path.join(root, "shared", "src", "ServerScriptService", "Services", "PlayerData")
    default_path = os.path.join(pd_dir, "Default.luau")
    dev_path = os.path.join(pd_dir, "Development.luau")
    services_dir = os.path.join(root, "shared", "src", "ServerScriptService", "Services")
    os.makedirs(pd_dir, exist_ok=True)

    tmp_dir = tempfile.mkdtemp(prefix="data_write_")
    try:
        out_default = os.path.join(tmp_dir, "Default.luau")
        out_dev = os.path.join(tmp_dir, "Development.luau")
        r = subprocess.run(
            [
                LUTE,
                "run",
                CORE,
                keypath,
                default_lit,
                dev_lit,
                default_path if os.path.exists(default_path) else "NEW",
                dev_path if os.path.exists(dev_path) else "NEW",
                out_default,
                out_dev,
            ],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0 or not r.stdout.startswith("OK"):
            print("data_write: REFUSED\n")
            print(houseout.elide(default_path, root) + ":")
            print()
            body = (r.stdout + r.stderr).strip()
            for line in body.split("\n"):
                if line and line != "OK":
                    print(line)
            return 2

        # data_shape_diff over the baseline and the proposed default. Schema
        # notes are informational and never require a separate approval.
        if os.path.exists(default_path):
            d = subprocess.run(
                [LUTE, "run", SHAPE_DIFF, default_path, out_default, "--migrations", services_dir],
                capture_output=True,
                text=True,
            )
            if d.returncode != 0 or not d.stdout.startswith("ALLOW"):
                print("data_write: REFUSED\n")
                print(houseout.elide(default_path, root) + ":")
                print()
                lines = d.stdout.strip().split("\n")[1:]
                if not lines:
                    lines = ["shape diff required checker failed [GATE4]"]
                for line in lines:
                    match = re.search(r"\[(GATE[1-7]|DATA\d+|TYPE\d+)\]", line)
                    rule = match.group(1) if match else "GATE4"
                    print("0|0|%s|%s|see data_shape_diff" % (rule, line.replace("|", "/")))
                return 2

        # the rename dance: POSIX offers no way to commit both or neither
        typed_tmp = out_default[: -len("Default.luau")] + "Typed.luau"
        typed_path = os.path.join(pd_dir, "Typed.luau")
        retained = None
        if os.path.exists(default_path):
            retained = default_path + ".orig"
            shutil.copy2(default_path, retained)
        try:
            os.replace(out_default, default_path)
            if os.path.exists(typed_tmp):
                os.replace(typed_tmp, typed_path)
            try:
                os.replace(out_dev, dev_path)
            except OSError as e:
                if retained is not None:
                    try:
                        os.replace(retained, default_path)
                        retained = None
                    except OSError:
                        print(
                            "data_write: FAILED\n\n0|0|GATE3|%s and %s disagree on %s|reconcile by hand - the pair is split"
                            % (default_path, dev_path, keypath)
                        )
                        return 2
                print("data_write: REFUSED\n\n0|0|GATE3|%s|second rename failed: %s - Default restored" % (keypath, e))
                return 2
        finally:
            if retained is not None and os.path.exists(retained):
                os.remove(retained)

        print("data_write: WRITTEN\n")
        print(houseout.elide(default_path, root) + ":")
        print()
        print("%s|%s" % (keypath, default_lit))
        print()
        print(houseout.elide(dev_path, root) + ":")
        print()
        print("%s|%s" % (keypath, dev_lit))
        return 0
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as e:
        sys.stderr.write("data_write: CRASH %s: %s - nothing was written\n" % (type(e).__name__, e))
        sys.exit(2)
