---
name: rblx-debug
description: Diagnose and fix Roblox failures and regressions from source, logs, or reproduction evidence.
---

# Roblox debugging

Follow project `AGENTS.md`; if Roblox rules are absent, read [CORE.md](../../CORE.md).

1. Establish the failure before testing a fix. Inspect the failing path and callers;
   if the cause is unresolved, choose one diagnostic that separates likely causes.
2. Fix the cause through the applicable implementation skill. Check the reported
   failure unless existing evidence resolves acceptance.
3. Report cause, change, evidence and limits.

Load [engine.md](../rblx-writer/references/engine.md) for engine decisions,
[probes.md](references/probes.md) for unresolved runtime questions, and `rblx-test`
for diagnostics or acceptance tests. Obtain probe results before dependent work.
For requested delegation, use [handoffs](../rblx-plan/references/delegation.md).
