---
name: rblx-gui
description: Build or connect native and React Luau GUI, including Studio plugin interfaces. Use rblx-writer for non-GUI code.
---

# Roblox GUI

Follow project `AGENTS.md`; if Roblox rules are absent, read [CORE.md](../../CORE.md).

Inspect GUI owners, stack, devices and behavior. Give each layout/animated
property one owner; release it at teardown. Use `scaffold module gui` for new
modules and `rblx-writer` for non-GUI logic.

| Decision | Load/action |
|---|---|
| Engine contracts | [engine.md](../rblx-writer/references/engine.md) |
| Size, AutomaticSize, CanvasSize, AutomaticCanvasSize | `api behavior gui`; retain scale/offset, constraints and padding; separate minimum size, content, canvas and viewport |
| React/animation | [react.md](references/react.md) |
| Unicode slicing | [luau.md](../rblx-writer/references/luau.md) |
| Unresolved appearance/input | [visual-tests.md](references/visual-tests.md) |
| Prior research scope | [coverage.md](references/coverage.md) |
| Requested delegation | [handoffs](../rblx-plan/references/delegation.md) |

Inspect simple text/spacing edits directly. Logs cannot prove visual acceptance.
