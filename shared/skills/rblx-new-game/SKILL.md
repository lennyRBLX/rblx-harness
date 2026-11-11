---
name: rblx-new-game
description: Inspect and scaffold multi-place Roblox projects with optional harness assets and plugin support. Use for setup, not features.
---

# Roblox project setup

`ROOT` is cwd; `SKILL` is this skill's resolved directory.

1. Inspect: `harness scaffold project inspect --root ROOT`.
2. Resolve missing choices with [interview.md](references/interview.md).
   Record accepted fields: `harness scaffold project answer FIELD VALUE --root ROOT`.
3. For authorized harness setup, run
   `harness scaffold dependency setup --root ROOT --yes`.
   This adds/stages the fixed public submodule and `.gitmodules`.
   For an existing clone missing its checkout, use `harness scaffold dependency init --root ROOT`.
4. Emit: `harness scaffold project emit --root ROOT`.
   If integration fails, retain state and retry only
   `harness setup --project ROOT --from-state`.

Keep multi-place layout, including one-place projects. Use
[layout.md](references/layout.md) for module/asset choices or setup integration.
For test scaffolding, use [test procedure](../rblx-test/references/procedure.md).
