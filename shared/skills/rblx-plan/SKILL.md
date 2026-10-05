---
name: rblx-plan
description: Create or update Roblox implementation plans with owners, API contracts, dependencies, and acceptance evidence. Applies to Plan Mode and requested plan files.
---

# Roblox implementation plans

Follow project instructions. Use [PLAN.md](../../PLAN.md) as an example, not session state. Write a project plan only when requested or needed for durable coordination. Keep the user's format and required Plan Mode wrapper; omit unused sections. Use Codex Plan Mode for discussion and its native plan tool for progress when available.

State the outcome and dependency-ordered, independently verifiable steps with owners, paths, status, and acceptance evidence. Keep referenced step IDs stable. Add signatures, data flow, authority, lifecycle, and Luau types only when implementation needs them. Inspect affected source before calling contracts existing; cite inspected contracts and mark proposals. For engine decisions, read [engine evidence](../rblx-writer/references/engine.md); use harness `types read` for public project APIs.

Reuse settled choices and verified results. Give receiving agents only missing context, with exact paths, symbols, values, and acceptance limits. Written plans need no automatic format gate or completion receipts.

Distill approved Decisions, Unresolved, and Pre-implementation tests into steps; remove those rows and empty tables. Each test needs one decision, question, stable ID and stopping condition. Begin with the broadest useful measurement and remove prerequisites that cannot affect the decision. Reuse valid findings and documented engine facts. Permit necessary measurement repeats, reproductions and checks affected by changes. Keep authored-algorithm correctness separate. Plan human readiness, independent result/capture collection, coverage and cleanup with the [shared procedure](../rblx-test/references/procedure.md).

If delegation is requested, use `researcher` for unresolved contracts, draft the plan, then run `optimizer` before `reviewer`. Have optimizer assess proposed costs and performance acceptance evidence without requiring a capture; address its findings. Have reviewer check contracts, dependencies, authority, lifecycle, and acceptance evidence, then complete the plan.
