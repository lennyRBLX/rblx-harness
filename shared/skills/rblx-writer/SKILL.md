---
name: rblx-writer
description: Write Roblox Luau features via research, optimization & review. Excludes bugs & MicroProfiler-led work.
---

Resolve `<HARNESS_ROOT>` from the project's `rblx-harness` submodule; read
`<HARNESS_ROOT>/shared/CORE.md`.

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
