---
name: rblx-optimize
description: Analyze Roblox MicroProfiler captures, locate source costs, and compare performance changes. Use for capture-led optimization.
---

# Roblox performance

Follow project `AGENTS.md`; if it lacks Roblox guidance, read [CORE.md](../../CORE.md). Let `H` be this skill's harness checkout; use `python3 H/tools/harness.py profile --help`.

1. Establish whether the representative workload has a material problem, using an existing valid capture or the broadest useful measurement and a predeclared threshold. Stop when no material problem remains. Investigate individual mechanisms only when that result requires it. Inspect the capture with `profile frames` and relevant stacks with `profile luau`. Locate source regions; distinguish measured costs from candidates. For Luau allocation/CPU changes, read [cost guidance](references/luau-costs.md).
2. Use [shared testing procedure](../rblx-test/references/procedure.md) for readiness, capture coverage, averages, spikes, independent collection and cleanup. Serialized measurements use the same buffer decoder as tests and debugging. Resolve target workload and missing human context. Reuse scope and authorization; ask only for decisions needed before behavior changes.
3. Verify affected engine contracts through [engine evidence](../rblx-writer/references/engine.md); implement and review.
4. Compare captures from the same workload and environment. Obtain human results unless agent execution is authorized. Claim improvement only from comparable measurements; otherwise report the candidate and evidence gap. Changed instrumentation requires `check source --only correctness PATH...`.

Use an `optimizer` subagent only when delegation is requested. Permit necessary measurement repeats and captures affected by source, workload or environment changes. Stop at the agreed target.
