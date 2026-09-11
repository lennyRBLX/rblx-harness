---
name: rblx-plan
description: Create, review and update Plan Mode responses and written implementation plans, including plans with arbitrary filenames. Applies to plan content, not progress updates or planning advice.
---

Use the harness containing this skill as `<HARNESS>` and the project root as `<ROOT>`.
Read [PLAN.md](../../PLAN.md) for the shared format and [CORE.md](../../CORE.md) for active rules.

1. Combine human behavior and acceptance decisions with agent source inspection.
   Reuse settled decisions; resolve missing product choices with the human.
2. Define owners, write paths, authority, data flow and lifecycle. List required
   engine/project APIs with caller, phase and evidence; declare exact shared records
   and public signatures in Luau. Apply `API1` and `TYPE1` when their scope applies.
3. Write concise affirmative commands. Merge related actions; retain exact paths,
   symbols, values and acceptance limits. State shared instructions once.
4. Supply only context missing from each receiving agent, references it must review,
   and necessary tool instructions beyond active rules. Resolve source references
   to exact symbols and lines; pin external code references to inspected revisions.
5. Use the shared format for the complete plan. Assign stable milestone IDs,
   prerequisites, owned paths, concrete outputs and verifiable completion evidence
   with human/agent responsibility. Apply TEST2–TEST3: reuse evidence or direct
   inspection when sufficient; a Verify action does not require a new test.
   Preserve required Plan Mode wrappers.
6. Use the installed Stop gate for format validation. If unavailable, or a
   preflight is specifically needed, validate a written plan with
   `python3 <HARNESS>/shared/gates/plan_gate.py --root <ROOT> --file <plan-path>`.
   Validate response text through the same command with `--stdin` in place of `--file`.
   Use stdin in Plan Mode. Reuse a successful format result for unchanged content;
   avoid a manual duplicate of the gate. Correct findings and review relevance,
   affirmative meaning, API/type accuracy and acceptance coverage before presenting.
7. After implementation and acceptance, archive each completed milestone
   as specified in PLAN.md, then remove its block. Preserve remaining dependencies
   and shared contracts. Record the implemented revision and actual evidence;
   an existing result needs only its reference, scope and continued applicability.

The gate checks format and completion receipt structure. Source correctness,
context relevance and proof of completion require review against inspected evidence.
