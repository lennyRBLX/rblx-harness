---
name: rblx-optimize
description: Analyze Roblox MicroProfiler captures, locate source costs, and compare performance changes. Use for capture-led optimization.
---

# Roblox performance

Follow project `AGENTS.md`; read [CORE.md](../../CORE.md) only if its Roblox
guidance is absent. Resolve the harness containing this skill as `H`.
Run `python3 H/tools/harness.py profile --help` for capture analysis.

1. Inspect the supplied capture with `profile frames` and relevant stacks with
   `profile luau`. Locate source regions and separate measured costs from candidates.
   For Luau allocation/CPU changes, read [cost guidance](references/luau-costs.md).
2. Resolve the target workload and any missing human context. Use existing scope
   and authorization; ask only for decisions needed before changing behavior.
3. Verify affected engine contracts through
   [engine evidence](../rblx-writer/references/engine.md), then implement and review.
4. Compare captures with the same workload and environment. Obtain human results
   unless agent execution is authorized. Claim improvement only from comparable
   measurements; otherwise report the candidate change and missing evidence.
   Changed instrumentation requires `check source --only correctness PATH...`.

Use an `optimizer` subagent when delegation is requested. Another capture needs
a changed input or an unresolved performance question. Stop at the agreed target.
