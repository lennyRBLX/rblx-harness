---
name: rblx-optimize
description: Analyze Roblox MicroProfiler dumps, obtain human context/approval, optimize & compare captures. Use only for dump-led performance work.
---

Resolve `<HARNESS_ROOT>` from the project's `rblx-harness` submodule; read
`<HARNESS_ROOT>/shared/CORE.md`.

Use [tool routes](../../TOOLS.md) for source/review packs, API batches and
console deltas. Reuse evidence already in context at unchanged revisions.

1. Run `optimizer` on the supplied dump; locate probable source regions.
2. Run `researcher` on those regions & reported issues.
3. List problems in plain English with probable source paths. Wait for human context, corrections & approval.
4. Rerun `optimizer` on approved regions/context for specific changes; implement them.
5. Obtain a human test & comparable dump for the settled change. Stop when the agreed target is met. Further runs need a relevant change or an unresolved performance question (TEST2–TEST3); investigate an unchanged result before repeating it.

Use `<HARNESS_ROOT>/tools/{frame_census,luau_hotspot,perf_audit}` for capture/source
analysis. Claim improvement only with human-supplied comparable before/after evidence.

For optimizations involving engine access, scheduling, replication, physics,
modules, persistence or asset readiness, read
[engine evidence](../rblx-writer/references/engine.md) before decisions.
