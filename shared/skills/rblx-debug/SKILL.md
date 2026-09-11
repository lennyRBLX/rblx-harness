---
name: rblx-debug
description: Diagnose/fix Roblox bugs from evidence, use focused tests when needed, then optimize, review & clean up. Use for unexplained bugs or fixes.
---

Resolve `<HARNESS_ROOT>` from the project's `rblx-harness` submodule; read
`<HARNESS_ROOT>/shared/CORE.md`.

Use [tool routes](../../TOOLS.md) for source/review packs, API batches and
console deltas. Reuse evidence already in context at unchanged revisions.

1. Run `researcher` for missing relevant Roblox docs & project facts; pass existing evidence.
2. Use `debugger` to resolve the cause. When supplied output/source establishes it, proceed to the fix. Otherwise select the smallest diagnostic that separates remaining causes (TEST2).
3. For a necessary runtime diagnostic, use the selected environment and execution authority (TEST1); obtain the result before making a dependent decision.
4. Write the fix from evidence. Run `optimizer`; apply its issues. Run `reviewer`; apply its issues.
5. Check the settled fix against the reported failure when TEST2 requires it. Reuse an earlier valid result; recheck after review only when an applied change affects that result (TEST3). Stop when required acceptance is met.
6. Remove this session's temporary tests & diagnostics; preserve pre-existing ones.

Keep diagnostics disabled by default & scoped to the selected place. Use
`tools/data_write/data_write.py`/`tools/type_write/type_write.py` under
`<HARNESS_ROOT>` for TOOL1 changes.

For engine access, timing, modules or lifecycle questions, read
[engine evidence](../rblx-writer/references/engine.md) before selecting probes.
Classify gaps: missing source, lost output, retrieval failure or ambiguous
behavior. Prefer engine docs, engineer-confirmed fixes or reproduction;
community reports are leads. Test only unresolved questions using
[probes.md](references/probes.md).
