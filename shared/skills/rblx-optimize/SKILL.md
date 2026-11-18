---
name: rblx-optimize
description: Assess Roblox performance in source, plans, or profiler captures. Use for hot paths, frame cost, memory, storage, or transport.
---

# Roblox performance

Follow project `AGENTS.md` or fall back to [CORE.md](../../CORE.md).

For existing code, identify the workload and affected budget. Reduce work or
frequency, then batch engine calls or use an equivalent cheaper API. Tune Luau
last. Stop when the workload meets its budget.

Run `check source --only performance PATH...` when source is available. Report
locations, applicable rules, actions, behavior risks and the smallest decisive
check. Use static evidence to identify candidates. Use workload evidence for
cost or gain claims. Follow the [runtime contracts](../rblx-writer/references/runtime.md)
for service and controller lifetime or instrumentation changes.

| Work | Guidance |
|---|---|
| Per-frame work, engine calls, physics, rendering, replication, parallel work | [Engine and platform costs](references/engine-costs.md) |
| Independent parts, articulated assemblies, bones, runtime meshes | [Mesh deformation and rigid movement](references/mesh-deformation.md) |
| Hot Luau loops, allocation, strings, native code generation | [Luau hot paths](references/luau-costs.md) |
| Packed fields, numeric arrays, remote and storage formats | [Compact formats](references/formats.md) |
| Lookup keys, scans, indexes, sorting, spatial hashes | [Keys and access patterns](references/keys.md) |
| Profiler selection, benchmarks, and gain claims | [Performance evidence](references/measurement.md) |
| Engine access and behavior | [Engine evidence](../rblx-writer/references/engine.md) |
| Subagent assignments | [Delegation](../rblx-plan/references/delegation.md) |

Route edits through [implementation](../rblx-writer/SKILL.md) and independent
review through [review](../rblx-review/SKILL.md).
