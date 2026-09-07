---
name: rblx-gui
description: Create, modify, or connect Roblox GUI behavior using Instances or React Luau, including Studio plugins and existing interfaces. Use alongside rblx-writer when a feature includes GUI and non-GUI work. Includes human visual testing, optimization, and review.
---

Resolve `<HARNESS_ROOT>` from the project's `rblx-harness` submodule; read
`<HARNESS_ROOT>/shared/CORE.md`. Paths are harness-relative.

Route by required behavior, including work specified in linked plans.
Connecting controls, settings, progress, errors, or Undo to new logic is
GUI work even when the existing layout and React stack are retained.
Load `rblx-writer` for accompanying non-GUI feature code. A backend-only
change that leaves GUI code and behavior unchanged does not require this skill.

1. Resolve GUI roots/owners, stack/packages, devices & behavior; preserve user/project choices. Route unexplained bugs to `rblx-debug`, MicroProfiler-led work to `rblx-optimize`.
2. Run `researcher` on affected classes, host APIs & behavior gaps. Read [engine evidence](../rblx-writer/references/engine.md); query `tools/api_dump/api_dump.py behavior` by exact API/record, plus `gui` for sizing. Check primary DevForum reports/follow-ups; reported defects remain test leads. React: read [react.md](references/react.md).
3. Write with `apply_patch`; create GUI modules with `tools/create_boilerplate/create_boilerplate.py gui`. Give each animated/layout property one owner; scope resources to GUI lifetime.
4. Stage [visual checks](references/visual-tests.md); human selects Studio/live & reports results. Fix from evidence; unrun/inconclusive checks stay open.
5. Run `optimizer` → apply issues → `reviewer` → apply issues → human recheck changed behavior. Claim gains only from comparable captures.
6. After tests, distill findings and limits into durable knowledge or constraints; delete owned research references, tests and temporary files. Preserve pre-existing files. Report evidence limits.

Bound agent prompts to affected paths, source/repro IDs & unresolved decisions.
For inventory coverage or untested boundaries, read [coverage.md](references/coverage.md).
