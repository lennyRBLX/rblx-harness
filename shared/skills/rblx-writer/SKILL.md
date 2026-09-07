---
name: rblx-writer
description: Implement non-GUI Roblox Luau features, including Studio plugin logic, through research, optimization, and review. For mixed features, use alongside rblx-gui. Route GUI-only work, bugs, and MicroProfiler-led work to their dedicated skills.
---

Resolve `<HARNESS_ROOT>` from the project's `rblx-harness` submodule; read
`<HARNESS_ROOT>/shared/CORE.md`.

Before research or implementation, inspect the request and linked plans
for GUI integration. If the feature creates, modifies, or connects GUI
behavior, load `rblx-gui` and apply both skills to their respective portions.
Retaining an existing GUI does not exclude GUI work when its controls,
settings, progress, errors, or Undo must connect to the new implementation.

1. Send `researcher` the request, relevant paths & exact Roblox/project questions; await evidence.
2. Write the feature. Use `apply_patch`; create Service/Controller frames with `tools/create_boilerplate/create_boilerplate.py`.
3. Run `optimizer` on the complete output; apply every relevant issue.
4. Run `reviewer` on the updated output; apply every issue.

Tool paths are relative to `<HARNESS_ROOT>`. Use `tools/data_write/data_write.py`
or `tools/type_write/type_write.py` for TOOL1 changes. Ask only unresolved
product choices. Bound agent prompts to affected paths & compact returned evidence.

Read only when relevant:

- Engine access/behavior: [engine.md](references/engine.md), before code, commands or tests depend on it.
- Agent role/model changes or evaluation: [models.md](references/models.md).
