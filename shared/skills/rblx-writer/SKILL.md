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
3. Review correctness, authority, lifecycle, and relevant performance risks.
   Use the smallest decisive check on settled changes; reuse valid evidence.

Delegate a bounded independent research or review question only when the user or
active project instructions request delegation. Pass affected paths, known results,
and unresolved questions. Keep straightforward work in the primary agent.
