---
name: rblx-new-game
description: Inspect and scaffold multi-place Roblox projects with optional harness assets and plugin support. Use for setup, not features.
---

# Roblox project setup

`ROOT` is cwd; `SKILL` is this skill's resolved directory.

1. Inspect: `python3 SKILL/scripts/scaffold.py inspect --root ROOT`.
2. Resolve missing choices with [interview.md](references/interview.md).
   Record accepted fields: `python3 SKILL/scripts/scaffold.py answer FIELD VALUE --root ROOT`.
3. For authorized harness setup, run
   `python3 SKILL/scripts/dependency.py setup --root ROOT --yes`.
   This adds/stages the fixed public submodule and `.gitmodules`.
   For an existing clone missing its checkout, use `dependency.py init --root ROOT`.
4. Emit: `python3 SKILL/scripts/scaffold.py emit --root ROOT`.
   If integration fails, retain state and retry only
   `python3 ROOT/rblx-harness/setup_project.py --project ROOT --from-state`.

Keep multi-place layout, including one-place projects. Use
[layout.md](references/layout.md) for module/asset choices or setup integration.
For test scaffolding, use [test procedure](../rblx-test/references/procedure.md).
