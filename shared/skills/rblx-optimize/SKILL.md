---
name: rblx-optimize
description: Assess Roblox source, plans, and MicroProfiler captures for CPU, memory, storage, and transport costs.
---

# Roblox performance

Follow project `AGENTS.md`; if Roblox rules are absent, read [CORE.md](../../CORE.md).

For source/plans, run `check source --only performance PATH...`. Return locations,
candidates, required actions, missing workload inputs and a decisive comparison.
Static findings establish neither material cost nor gains; no capture is required.

Before mechanism benchmarks, establish a material workload problem and separate
CPU, latency, retained/peak memory and byte budgets. Stop when the target is met
or no material problem remains. Claim gains only for comparable workloads and
environments with equivalent results or accepted error bounds.

| Work | Guidance/tool |
|---|---|
| Cost candidates | [luau-costs.md](references/luau-costs.md) |
| Benchmarks/comparisons | [measurement.md](references/measurement.md), `rblx-test` |
| Captures | `profile frames`, `profile luau`; [capture procedure](../rblx-test/references/captures.md) |
| Engine decisions | [engine.md](../rblx-writer/references/engine.md) |
| Requested delegation | [handoffs](../rblx-plan/references/delegation.md) |

Route edits through the implementation skill, then review. Changed instrumentation
requires `check source --only correctness PATH...`.
