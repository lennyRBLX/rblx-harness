---
name: rblx-debug
description: Diagnose and fix Roblox bugs from source, logs, or reproduction evidence. Use for unexplained failures and regressions.
---

# Roblox debugging

Follow project `AGENTS.md`; read [CORE.md](../../CORE.md) only if its Roblox
guidance is absent. Resolve the harness containing this skill as `H`.
Use `python3 H/tools/harness.py --help` for domain commands.

1. Inspect the failure and affected callers. Supplied source or output may establish
   the cause; otherwise choose one diagnostic that separates the remaining causes.
2. For engine questions, load [engine evidence](../rblx-writer/references/engine.md).
   Read [probes.md](references/probes.md) only for an unresolved runtime question.
   Obtain the selected environment's result before a dependent decision.
3. Fix the established cause. Use `types write` for data or public declarations.
   Review correctness, lifecycle, and affected performance. Check the reported
   failure when existing evidence does not resolve acceptance.
4. Remove this task's temporary diagnostics; preserve pre-existing and useful
   regression tests. Report the cause, change, evidence, and remaining limits.

When delegation is requested, use `debugger` if the cause is unresolved. After
the fix, run `optimizer` before `reviewer`. Address optimizer findings before
handing the settled changes to reviewer; source analysis does not require a
capture. Add research only for unresolved questions.
