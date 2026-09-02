---
name: rblx-optimize
description: Analyze a Roblox MicroProfiler dump, locate causes, obtain human context and approval, implement optimizations, and compare another dump. Use only for MicroProfiler-led performance work.
---

# rblx-optimize

Resolve `<HARNESS_ROOT>` from the project's `rblx-harness` submodule. Read
`<HARNESS_ROOT>/shared/CORE.md` before work.

Follow this cycle:

1. Treat a prompt involving a MicroProfiler dump as the trigger for this
   skill.
2. Run the `optimizer` agent on the supplied MicroProfiler dump.
3. Locate probable source regions for the reported problems.
4. Run the `researcher` agent on those locations and the general issues from
   the optimizer.
5. List the optimizer's problems in clear English. Attach probable source
   locations when available. Wait for the human to review the list and add
   contextual clues or corrections.
6. After human approval, run the `optimizer` agent again on the approved source
   regions and context to obtain specific changes.
7. Implement the approved changes.
8. Wait for the human to test and provide a comparable MicroProfiler dump.
   Repeat from step 2 while the problem remains.

Use `tools/frame_census`, `tools/luau_hotspot`, and `tools/perf_audit` for dump
and source analysis. Do not claim improvement without the human's comparable
before-and-after evidence.
