---
name: rblx-debug
description: Diagnose and fix Roblox bugs from source, logs, or reproduction evidence. Use for unexplained failures and regressions.
---

# Roblox debugging

Follow project `AGENTS.md`; if it lacks Roblox guidance, read [CORE.md](../../CORE.md). Let `H` be this skill's harness checkout; use `python3 H/tools/harness.py --help` for domain commands.

1. Establish the failure from existing evidence or reproduce it before testing a proposed fix. Inspect the failure and callers. If supplied source or output does not establish the cause, choose one diagnostic that separates remaining causes.
2. For engine questions, read [engine evidence](../rblx-writer/references/engine.md). Read [probes.md](references/probes.md) only for unresolved runtime questions; obtain the selected environment's result before dependent decisions.
3. Use [test procedure](../rblx-test/references/procedure.md) and its shared decoder for diagnostics and acceptance. Fix the cause; use `types write` for data or public declarations. Review correctness, lifecycle, and affected performance. Check the reported failure if existing evidence does not resolve acceptance.
4. Remove this task's temporary diagnostics; keep existing and useful regression tests. Report cause, change, evidence, and limits.

If delegation is requested, use `debugger` while the cause is unresolved; add research only for unresolved questions. After the fix, run `optimizer` before `reviewer` and address its findings before review. Source analysis needs no capture.
