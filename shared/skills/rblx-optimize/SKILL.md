---
name: rblx-optimize
description: Analyze Roblox MicroProfiler captures, locate source costs, and compare performance changes. Use for capture-led optimization.
---

# Roblox performance

Follow project `AGENTS.md`; if it lacks Roblox guidance, read [CORE.md](../../CORE.md). Let `H` be this skill's harness checkout; use `python3 H/tools/harness.py profile --help`.

1. Inspect the capture with `profile frames` and relevant stacks with `profile luau`. Locate source regions; distinguish measured costs from candidates. For Luau allocation/CPU changes, read [cost guidance](references/luau-costs.md).
2. Resolve target workload and missing human context. Reuse scope and authorization; ask only for decisions needed before behavior changes.
3. Verify affected engine contracts through [engine evidence](../rblx-writer/references/engine.md); implement and review.
4. Compare captures from the same workload and environment. Obtain human results unless agent execution is authorized. Claim improvement only from comparable measurements; otherwise report the candidate and evidence gap. Changed instrumentation requires `check source --only correctness PATH...`.

Use an `optimizer` subagent only when delegation is requested. Get another capture only for changed input or an unresolved performance question. Stop at the agreed target.
