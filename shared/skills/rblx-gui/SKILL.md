---
name: rblx-gui
description: Create or connect Roblox GUI behavior with Instances or React Luau, including Studio plugin interfaces. Use rblx-writer for accompanying non-GUI code.
---

# Roblox GUI

Follow project `AGENTS.md`; read [CORE.md](../../CORE.md) only if its Roblox
guidance is absent. Resolve the harness containing this skill as `H`.
Use `python3 H/tools/harness.py --help` for domain commands.

1. Identify GUI owners, stack, devices, and behavior. Preserve project choices.
   Connecting existing controls or Undo to new logic counts as GUI work.
2. Load [engine evidence](../rblx-writer/references/engine.md) for affected engine
   contracts; query `api behavior gui` for sizing. For React, read
   [react.md](references/react.md). Load `rblx-writer` for non-GUI feature code.
3. Implement with native editing tools; use `scaffold module gui` for new modules.
   Give each animated or layout property one owner and clean up at owner teardown.
4. Review behavior and lifecycle. Select [visual checks](references/visual-tests.md)
   for unresolved appearance or interaction risks; inspect simple text or spacing
   edits directly. Logs alone do not establish visual acceptance.

Use bounded agents when delegation is requested. For research coverage or an
untested class boundary, read [coverage.md](references/coverage.md). Preserve
source and runtime evidence limits; remove only owned temporary files.
