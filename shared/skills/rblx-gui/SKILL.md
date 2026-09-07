---
name: rblx-gui
description: Write Roblox GUI code, native or React Lua, with human visual tests, optimization & review. Excludes unexplained bugs & dump-led work.
---

Resolve `<HARNESS_ROOT>` from the project's `rblx-harness` submodule; read
`<HARNESS_ROOT>/shared/CORE.md`. Paths are harness-relative.

1. Resolve GUI roots/owners, stack/packages, devices & behavior; preserve user/project choices. Route unexplained bugs to `rblx-debug`, MicroProfiler-led work to `rblx-optimize`.
2. Run `researcher` on affected classes, host APIs & behavior gaps. Read [engine evidence](../rblx-writer/references/engine.md); query `tools/api_dump/api_dump.py behavior` by exact API/record, plus `gui` for sizing. Check primary DevForum reports/follow-ups; reported defects remain test leads. React: read [react.md](references/react.md).
3. Write with `apply_patch`; create GUI modules with `tools/create_boilerplate/create_boilerplate.py gui`. Give each animated/layout property one owner; scope resources to GUI lifetime.
4. Stage [visual checks](references/visual-tests.md); human selects Studio/live & reports results. Fix from evidence; unrun/inconclusive checks stay open.
5. Run `optimizer` → apply issues → `reviewer` → apply issues → human recheck changed behavior. Claim gains only from comparable captures.
6. After tests, distill findings and limits into durable knowledge or constraints; delete owned research references, tests and temporary files. Preserve pre-existing files. Report evidence limits.

Bound agent prompts to affected paths, source/repro IDs & unresolved decisions.
For inventory coverage or untested boundaries, read [coverage.md](references/coverage.md).
