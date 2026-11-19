---
name: rblx-writer
description: Write or change Roblox Luau gameplay, services, controllers, and plugin logic. Route GUI behavior to rblx-gui.
---

# Roblox implementation

Follow project `AGENTS.md` and use the [shared rules](../../CORE.md) when it lacks Roblox guidance.

Inspect owners and callers. Reuse same-side math, helpers, APIs and packages (WRIT20). Use the [source style](references/style.md) for Luau edits. Resolve APIs with `types read` and use `scaffold module` for new modules. Use `types write` for data and public types.

| Change | Guidance |
|---|---|
| Engine access and behavior | [Engine evidence](references/engine.md) |
| Rig pose, scale or hierarchy, clothing, materials, highlights, editable visuals | [FastCluster authoring](../rblx-optimize/references/fast-clusters.md#author-rendered-rigs) |
| Hot paths, high-volume data, performance | [Optimization](../rblx-optimize/SKILL.md) |
| Types, collections, text | [Luau](references/luau.md) |
| Codecs, remotes, HTTP | [Network](references/network.md) |
| Lifecycle, tasks, Signals, PlayerData, Actors, profiling, assets | [Runtime](references/runtime.md) |
| GUI behavior | [GUI](../rblx-gui/SKILL.md) |
| Test selection or source | [Testing](../rblx-test/SKILL.md) |
| Subagent assignments | [Delegation](../rblx-plan/references/delegation.md) |
| Independent review | [Review](../rblx-review/SKILL.md) |

Check authority, lifecycle and affected performance before handing off. Run applicable [source checks](../../../TOOLS.md#checks) on changed paths.
