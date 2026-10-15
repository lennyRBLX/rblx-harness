---
name: rblx-optimize
description: Assess Roblox source, plans, and MicroProfiler captures for material CPU, memory, representation, storage, and transport costs.
---

# Roblox performance

Follow project `AGENTS.md`; if it lacks Roblox guidance, read [CORE.md](../../CORE.md). Let `H` be this skill's harness checkout; use `python3 H/tools/harness.py profile --help`.

1. For source or plan assessments, use [cost guidance](references/luau-costs.md) when CPU, allocation, representation, search, sorting, serialization, storage, or transport can be material. Use `check source --only performance PATH...` on affected source. Return locations, candidates, required actions, missing workload inputs, and the smallest decisive comparison. No capture prerequisite or static performance claims.
2. Before mechanism benchmarks, require a material problem in the representative workload and separate CPU, latency, retained/peak memory, and byte budgets. Use valid evidence or the broadest useful measurement; state phase, frequency, and reuse. Stop when no material problem remains. For captures, use `profile frames` and `profile luau` to locate measured costs.
3. Use [shared testing procedure](../rblx-test/references/procedure.md) for readiness, coverage, averages, spikes, independent collection, and cleanup. Use `profile results` for serialized measurements; add `--compare BASE CANDIDATE` for paired timing arithmetic. Reuse valid evidence, scope, and execution authorization; require human results when agent execution is not authorized.
4. For engine-dependent decisions, use [engine evidence](../rblx-writer/references/engine.md). Route edits through the applicable implementation skill, then reviewer. Require comparable workload/environment and equivalent results or accepted error bounds before claiming gains. Changed instrumentation requires `check source --only correctness PATH...`.

Use an `optimizer` subagent only when delegation is requested. Permit necessary measurement repeats and captures affected by source, workload or environment changes. Stop at the agreed target.
