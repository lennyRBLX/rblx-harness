---
name: rblx-writer
description: Implement non-GUI Roblox Luau features and Studio plugin logic. Use rblx-gui as well when connecting or changing GUI behavior.
---

# Roblox features

Follow project `AGENTS.md`; if it lacks Roblox guidance, read [CORE.md](../../CORE.md) once. Let `H` be this skill's harness checkout. Run domain commands through `python3 H/tools/harness.py`; use family `--help` as needed. Search and edit code natively.

1. Inspect owners and callers. Resolve missing project contracts with `types read` and engine questions with [engine.md](references/engine.md). Load `rblx-gui` for controls, settings, progress, errors, or Undo changes.
2. Implement; use `scaffold module` for new frames and `types write` for related data and public types. Prefer `const` for unreassigned bindings, `local` for mutable ones, and `elseif` for guards sharing a return. Put a blank line after guards and functions and before final branches; return one-use results directly. Read [Luau contracts](references/luau.md) for types, collections, or text; [network contracts](references/network.md) for codecs/remotes; [runtime contracts](references/runtime.md) for startup, async services, or Actors.
3. Review correctness, authority, lifecycle, and relevant performance risks. For test source, use rblx-test and shared lifecycle/codec support. On settled changes, run the smallest decisive check and reuse valid evidence. Changed profile/parallel scopes require `check source --only correctness PATH...` for path pairing; review indirect calls and exception cleanup separately.

If delegation is requested by the user or project, use `researcher` for unresolved research, implement, then run `optimizer` before `reviewer`. Address optimizer findings before review; pass paths, known results, and open questions. Keep straightforward implementation in the primary agent. Source analysis needs no capture.
