---
name: rblx-gui
description: Create or connect Roblox GUI behavior with Instances or React Luau, including Studio plugin interfaces. Use rblx-writer for accompanying non-GUI code.
---

# Roblox GUI

Follow project `AGENTS.md`; if it lacks Roblox guidance, read [CORE.md](../../CORE.md). Let `H` be this skill's harness checkout; use `python3 H/tools/harness.py --help` for domain commands.

1. Identify GUI owners, stack, devices, and behavior; preserve project choices. Connecting controls or Undo to new logic is GUI work.
2. Read [engine evidence](../rblx-writer/references/engine.md) for affected contracts; query `api behavior gui` for sizing. Read [react.md](references/react.md) for React and [text contracts](../rblx-writer/references/luau.md) for Unicode slicing. Load `rblx-writer` for non-GUI code.
3. Edit natively; use `scaffold module gui` for new modules. Give each animated or layout property one owner; clean up at teardown.
4. Review behavior and lifecycle. Use [visual checks](references/visual-tests.md) for unresolved appearance or interaction risks; inspect simple text or spacing edits directly. Logs do not prove visual acceptance.

If delegation is requested, use `researcher` for unresolved research, then `optimizer` before `reviewer`; address optimizer findings first. Source analysis needs no capture. For research coverage or an untested class boundary, read [coverage.md](references/coverage.md). Preserve source and runtime evidence limits; remove only owned temporary files.
