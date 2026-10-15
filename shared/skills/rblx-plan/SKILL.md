---
name: rblx-plan
description: Create or update Roblox implementation plans with owners, contracts, dependencies, and acceptance evidence. Use for Plan Mode or requested plans.
---

# Roblox plans

Follow project `AGENTS.md`; if Roblox rules are absent, read [CORE.md](../../CORE.md).

Keep the user's format and required Plan Mode wrapper. Use [PLAN.md](../../PLAN.md)
as a template, not state. Write a plan file only when requested or needed for
coordination; use native planning/progress tools when available.

State the outcome and dependency-ordered, verifiable steps: stable ID, owner,
paths, change, status and acceptance evidence. Add signatures, data flow,
authority, lifecycle and Luau types only where needed. Inspect existing contracts;
cite them and mark proposals. Use `types read` for public project APIs and
[engine.md](../rblx-writer/references/engine.md) for engine decisions.

Merge settled Decisions, Unresolved and Pre-implementation tests into steps;
remove resolved rows and empty tables. Use `rblx-test` for test decisions and
its [procedure](../rblx-test/references/procedure.md) when planning execution.
For requested delegation, use [handoffs](references/delegation.md).
