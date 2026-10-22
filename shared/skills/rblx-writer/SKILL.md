---
name: rblx-writer
description: Implement non-GUI Roblox Luau features and plugin logic. Use rblx-gui for GUI behavior.
---

# Roblox implementation

Follow project `AGENTS.md`; if Roblox rules are absent, read [CORE.md](../../CORE.md).

Inspect owners and callers; reuse same-side math/helpers/APIs and packages on
server and client (WRIT20). Resolve project APIs with `types read`. Use
`scaffold module` for new modules and `types write` for data/public types.
WRIT1: Name module tables `m`; use `:` for methods unless OOP (`m.new()`).
Use multiline formatting for populated `m` tables. Order declarations: configuration
constants; services and service-derived values; runtime dependencies; type
dependencies; cyclic dependency declarations and aliases; local types; module
table `m`. Preserve required dependency initialization order.

Use `const` for unreassigned bindings, `local` for mutable bindings, and `elseif`
for guards with the same return. Separate logical groups of declarations,
validation, state changes and subsequent operations with blank lines. Separate
guards/functions and final branches with a blank line; prefer no blank line between
assignments or local declarations and a following return. Place `-- privates` and
`-- functions` directly above their first declaration.

Keep simple calls, assertions, errors and multiple assignments on one line. For
multiline table arguments, keep the call prefix and opening brace together; place
following arguments after the closing brace.

For grouped multiline conditions, use `if condition and (` followed by the
multiline group and `) then`. Keep standalone `if` and `then` lines for long, flat
condition chains.

Inline single-use argument tables when an intermediate name adds no meaning.
Retain explicit typing where it provides a required static contract. Return
one-use results directly.

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
