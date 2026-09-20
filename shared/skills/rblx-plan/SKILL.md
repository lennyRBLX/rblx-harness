---
name: rblx-plan
description: Create or update Roblox implementation plans with owners, API contracts, dependencies, and acceptance evidence. Applies to Plan Mode and requested plan files.
---

# Roblox implementation plans

Use [PLAN.md](../../PLAN.md) as a fill-in example, not session state. Write a
project plan file only when requested or needed for durable coordination. Preserve
the user's format and required Plan Mode wrapper; omit unused template sections.
Use Codex Plan Mode for discussion and its native plan tool for execution progress
when available. Follow active project instructions.

Include the outcome and dependency-ordered, independently verifiable implementation
steps with owners, paths, status, and acceptance evidence. Keep referenced step IDs
stable. Add signatures, data flow, authority, lifecycle, and Luau types only where
implementation depends on them. Cite inspected contracts; mark proposed ones.
Inspect affected source before declaring existing contracts. For engine decisions,
read [engine evidence](../rblx-writer/references/engine.md); use `types read` through
the harness command for public project APIs.

Reuse settled product choices and verified results. Supply only context missing
from the receiving agent. Keep exact paths, symbols, values, and acceptance limits.
A written plan needs no automatic format gate or separate completion receipts.

Decisions, Unresolved, and Pre-implementation tests tables are temporary: distill
approved items into implementation steps, remove their rows, and remove empty tables.
Pre-implementation tests must only affirm new facts, test plan boundaries, identify
problems converting reference source code to Luau, or identify solutions to
discovered problems.

When delegation is requested, use `researcher` for unresolved contracts, draft
the plan, then run `optimizer` before `reviewer`. Have optimizer assess proposed
costs and performance acceptance evidence without requiring a capture. Address
its findings before reviewer checks the settled plan's contracts, dependencies,
authority, lifecycle, and acceptance evidence. Complete the plan after review.
