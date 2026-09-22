---
name: rblx-writer
description: Implement non-GUI Roblox Luau features and Studio plugin logic. Use rblx-gui as well when connecting or changing GUI behavior.
---

# Roblox features

Resolve the harness containing this skill as `H`. Follow project `AGENTS.md`;
if its Roblox guidance is absent, read [CORE.md](../../CORE.md) once.
Run domain commands through `python3 H/tools/harness.py`; use `--help` for the
needed family. Use native search and editing for ordinary code work.

1. Inspect affected owners and callers. Resolve missing project contracts with
   `types read`; verify engine questions through [engine.md](references/engine.md).
   Load `rblx-gui` when controls, settings, progress, errors, or Undo need GUI changes.
2. Implement the feature. Use `scaffold module` for new module frames and
   `types write` for related data and public type changes.
   Prefer `const` for unreassigned bindings; keep mutable bindings `local`.
   For types, collections, or text, read [Luau contracts](references/luau.md).
   For codecs/remotes, read [network contracts](references/network.md).
   For startup, async services, or Actors, read [runtime contracts](references/runtime.md).
3. Review correctness, authority, lifecycle, and relevant performance risks.
   Use the smallest decisive check on settled changes; reuse valid evidence.
   Changed profile/parallel scopes require `check source --only correctness PATH...`;
   it checks path pairing. Review indirect calls and exception cleanup separately.

When the user or active project instructions request delegation, use `researcher`
for unresolved research, implement, then run `optimizer` before `reviewer`.
Address optimizer findings before handing the settled changes to reviewer.
Pass affected paths, known results, and unresolved questions. Keep straightforward
implementation in the primary agent; source analysis does not require a capture.
