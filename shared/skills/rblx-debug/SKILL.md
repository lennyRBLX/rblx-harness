---
name: rblx-debug
description: Diagnose and fix Roblox failures and regressions from source, logs, or reproduction evidence.
---

# Roblox debugging

Follow project `AGENTS.md` and use the [shared rules](../../CORE.md) when it lacks Roblox guidance.

1. Reuse valid failure evidence or reproduce the failure before testing a fix. Inspect the path and callers. If the cause remains open, choose the smallest diagnostic that separates likely causes.
2. Fix the cause through the applicable implementation skill. Check the reported failure unless existing evidence resolves acceptance.
3. Report cause, change, evidence and limits.

Load [engine evidence](../rblx-writer/references/engine.md) for engine decisions, [probes](references/probes.md) for unresolved runtime questions and [testing](../rblx-test/SKILL.md) for diagnostics or acceptance tests. In an authorized active playtest, check [hot reload](../rblx-test/references/hot-reload.md) before restarting. Obtain probe results before dependent work. For task splits that benefit from subagents, use [handoffs](../rblx-plan/references/delegation.md).
