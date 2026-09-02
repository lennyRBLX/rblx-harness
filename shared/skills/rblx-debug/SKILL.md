---
name: rblx-debug
description: Diagnose and fix a Roblox bug through human-selected Studio or live tests, then optimize, review, verify, and remove temporary diagnostics. Use when a bug needs fixing or its cause is not yet known.
---

# rblx-debug

Resolve `<HARNESS_ROOT>` from the project's `rblx-harness` submodule. Read
`<HARNESS_ROOT>/shared/CORE.md` before work.

Follow this sequence:

1. Treat a prompt about a bug to fix or an unexplained bug as the trigger for
   this skill.
2. Run the `researcher` agent for relevant Roblox documentation and project
   facts.
3. Write a focused test or diagnostic with the `debugger` agent. Continue the
   writer-debugger exchange until the test is ready.
4. Ask the human whether to run it in Studio or live. Wait for the human to
   test and report the cause.
5. Write the solution with the `debugger` agent's evidence.
6. Wait for the human to test and confirm that the bug is fixed.
7. Run the `optimizer` agent on the fix.
8. Apply the optimizer's issues.
9. Run the `reviewer` agent on the optimized fix.
10. Apply the reviewer's issues.
11. Wait for the human to test again and confirm that the optimized result is
   still fixed.
12. Delete every temporary test and debugging change created by this session.

The human controls the Studio-or-live choice and each test result. Do not infer
a pass. Keep diagnostic code disabled by default and scoped to the selected
place. Do not delete pre-existing tests or diagnostics.

Use the data and type tools for any data-shape or public-type change. New data
fields do not require a separate human review gate.
