---
name: rblx-writer
description: Implement non-GUI Roblox Luau features and plugin logic. Use rblx-gui for GUI behavior.
---

# Roblox implementation

Follow project `AGENTS.md`; if Roblox rules are absent, read [CORE.md](../../CORE.md).

Inspect owners and callers; resolve project APIs with `types read`. Use
`scaffold module` for new modules and `types write` for data/public types.
Use `const` for unreassigned bindings, `local` for mutable bindings, and `elseif`
for guards with the same return. Separate guards/functions and final branches
with a blank line; return one-use results directly.

Load only the applicable guidance:

| Change | Guidance |
|---|---|
| Engine access/behavior | [engine.md](references/engine.md) |
| Types, collections, text | [luau.md](references/luau.md) |
| Codecs, remotes, HTTP | [network.md](references/network.md) |
| Startup, async services, Actors, assets | [runtime.md](references/runtime.md) |
| GUI controls, settings, progress, errors, Undo | `rblx-gui` |
| Test selection/source | `rblx-test` |
| Requested delegation | [handoffs](../rblx-plan/references/delegation.md) |

Review authority, lifecycle and affected performance. Check settled edits with
the smallest decisive check. For changed profile/parallel scopes, run
`check source --only correctness PATH...`; review indirect calls and exception
cleanup separately.
