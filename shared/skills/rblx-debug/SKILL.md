---
name: rblx-debug
description: Diagnose/fix Roblox bugs with human tests, then optimize, review & clean up. Use for unexplained bugs or fixes.
---

Resolve `<HARNESS_ROOT>` from the project's `rblx-harness` submodule; read
`<HARNESS_ROOT>/shared/CORE.md`.

1. Run `researcher` for relevant Roblox docs & project facts.
2. Iterate with `debugger` until a focused test/diagnostic is ready.
3. Ask the human to select Studio/live; wait for their test & cause report.
4. Write the fix from debugger evidence; wait for human confirmation it works.
5. Run `optimizer`; apply its issues. Run `reviewer`; apply its issues.
6. Wait for human confirmation the optimized fix still works.
7. Remove this session's temporary tests & diagnostics; preserve pre-existing ones.

Keep diagnostics disabled by default & scoped to the selected place. Use
`tools/data_write/data_write.py`/`tools/type_write/type_write.py` under
`<HARNESS_ROOT>` for TOOL1 changes.

For engine access, timing, modules or lifecycle questions, read
[engine evidence](../rblx-writer/references/engine.md) before selecting probes.
Classify gaps: missing source, lost output, retrieval failure or ambiguous
behavior. Prefer engine docs, engineer-confirmed fixes or reproduction;
community reports are leads. Test only unresolved questions using
[probes.md](references/probes.md).
