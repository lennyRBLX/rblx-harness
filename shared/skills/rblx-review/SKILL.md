---
name: rblx-review
description: Review Roblox changes or implementation plans for correctness, security, lifecycle, and performance risks.
---

# Roblox review

Follow project `AGENTS.md` or fall back to [CORE.md](../../CORE.md). Review changes,
affected callers or plans. Keep source and Studio read-only. Use optimizer findings
and their disposition when the [delegation order](../rblx-plan/references/delegation.md)
calls for them.

- Trace authority, replication, data, types and lifecycle across owners and
  callers. For plans, check dependencies and acceptance criteria. Distinguish
  proposals from implemented behavior.
- Use Git and scoped reads. Use `inspect --no-cache` for bounded
  [read and diff evidence](../../../TOOLS.md#evidence).
  Use [engine evidence](../rblx-writer/references/engine.md) for API behavior.
- For caching, coalescing or slower updates, verify lifetime, timing and ordering
  against the [runtime contracts](../rblx-writer/references/runtime.md). Check
  pooled resources against the [reuse rules](../rblx-writer/references/luau.md).
- Check batching and deformation against the
  [movement rules](../rblx-optimize/references/mesh-deformation.md). Check supported
  readers and input validation against the [network contracts](../rblx-writer/references/network.md).
- Check gain claims against the [measurement rules](../rblx-optimize/references/measurement.md).
  Reuse valid checks. Name the uncovered risk before requesting another.

Report findings with path and line, impact, evidence and a correction. If none
remain, say so. Report material validation gaps.
