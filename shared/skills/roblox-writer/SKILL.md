---
name: roblox-writer
description: Runs the gated Roblox Luau write chain with researcher, optimizer, debugger, reviewer, and maintainer agents. Use when creating or changing game code in a harness-managed Roblox project; do not use for general Lua or non-Roblox work.
---

# roblox-writer — the write chain

Run this skill in-session so the gates see every write. Resolve
`<HARNESS_ROOT>` as three directories above the real directory that contains
this `SKILL.md`; follow symlinks before resolving it. The gates run themselves.

## Project rules outside mechanical checks

Follow these rules at their configured disposition. This summary does not
turn guidance or reviewer-only findings into hard blockers.

- `TYPE1` — types are documentation plus a definite-error gate, never a
  runtime contract.
- `TYPE2` — an annotation enforces nothing; the runtime guard is what
  enforces. A typed parameter still gets its `type()` check at a remote
  boundary.
- `DATA6` — `PlayerData:fix` backfills missing keys and resets any key whose
  stored `typeof` differs. A migration registers pre-`fix` through
  `PlayerData:AddSetup("Pre", callback, "Service.migration")`; an update
  registers post-`fix` through `AddSetup("Post", …)`.
- One template serves every place, so a single `type_write` data operation reaches all of
  them.

## Method

Parent handles quick/mech work; route only req'd roles. Reuse accepted role
results while scope, target, and ev. stay valid. Overlap indep. work; lease
overlapping write paths; settle before review. Keep parent active; join at the
first dep.

1. **Research only unresolved facts.** Dispatch `researcher` when the change
   depends on Roblox API or Creator Docs, current project behavior, Studio
   state, or another unresolved fact. Supply the bounded goal, affected paths,
   intended behavior, and exact questions. Do not dispatch it for a verified
   mechanical edit. It searches `api_dump.json` and Creator Docs internally
   and returns compact records; never copy raw lookup context into this
   session. Join and acknowledge it before consuming the result. `MISS` names
   an evidence action and `ENV` names an environment gap; never fill either
   from memory.
2. **Skeletons come from the emitter.**
   `python3 <HARNESS_ROOT>/tools/create_boilerplate/create_boilerplate.py <kind> <Name>`
   — service · controller · gui · update · data-module · tool-handler.
   `--expand <Name>` converts a flat module to the folder form. Client frames
   arrive with `local Player = Players.LocalPlayer` bound at top of script; an
   existing client file that needs LocalPlayer gains that line rather than
   reading the property inline [R WRIT32].
3. **Resolve project types before their use.** Batch existing API questions
   through
   `python3 <HARNESS_ROOT>/tools/type_lookup/type_lookup.py --request '<JSON>'`;
   batch named declaration and owner-data changes through
   `python3 <HARNESS_ROOT>/tools/type_write/type_write.py --request '<JSON>'`,
   and use each successful returned declaration as current context [R WRIT33,
   TYPE7, TYPE8, TYPE9, DATA37]. A private named type outside the canonical
   provider roots uses `--parent <project-relative-directory>` to force the
   destination directory; the operation's `module`, or `owner` when omitted,
   selects the file below it.
4. **Write implementation code through the host's native file-edit tool.** Use Edit/Write in
   Claude Code or `apply_patch` in Codex. write-gate runs the deny table, the
   replication audit, and the bespoke checks per write; a `BLOCKED (ENV)`
   verdict is environment, not code — stop and surface it, never edit
   correct code to appease it. At the first source mutation, `GATE6`
   automatically runs one exact `git_sync.py repair` for a behind/diverged
   repository, verifies the result, and retries the original write once. The tool
   stashes indexed, tracked, and
   untracked work, fetches, rebases local commits, and restores the stash; it
   never pushes. Any fetch, rebase, or stash-restore failure halts the write
   chain and is surfaced without another repair attempt.
   A stale corpus, absent generated globals, or broken type cache receives one
   exact automatic repair and postcondition check before the source mutation.
   If a remaining `GATE4` names an allowed exact recovery command, dispatch
   `maintainer` once, join and acknowledge it, then re-check. A degraded
   SessionStart cannot dispatch a child; the primary agent runs that one exact
   recovery command before it retries any other tool.
5. **Data fields go through the ruling.** To add a field:
   `lute run <HARNESS_ROOT>/tools/data_check/data_check.luau --static <file>` on the
   proposed value, then **present the field and a filled example to the
   developer for a ruling**, then
   `python3 <HARNESS_ROOT>/tools/type_write/type_write.py --request '<JSON data operation>'`
   once permitted or restructured.
6. **Route only required roles.** Use debugger before a defect fix only when
   its cause is not already reproduced and evidenced. Use optimizer for
   performance-sensitive code, frame work, replication volume,
   allocation/lifecycle changes, or a reported performance symptom. Give it
   an immutable output or diff plus any relevant researcher constraint,
   capture, or symptom. Every changed Luau target still requires reviewer.
   Any later write invalidates optimization and review; re-run only the
   conditional roles required by the changed target, then review again.
7. **Review target.** After all required evidence roles finish, settle the
   tracked Luau change set, then run
   `python3 <HARNESS_ROOT>/shared/gates/turn_stamp.py --target` and include
   its one-line base and digest plus every exact changed source path in each
   reviewer dispatch, then run
   `python3 <HARNESS_ROOT>/tools/type_lookup/type_lookup.py --affected <base>`
   and include its sorted paths. The reviewer inspects
   `git diff <base> -- '*.lua' '*.luau'`, reads supplied new-untracked paths
   directly, and uses any researcher or optimizer results that were required.
   The receipt hashes that target at dispatch, return, and
   done-gate; any intervening change invalidates it.
8. **Bound concurrency.** Keep delegation depth at one. Researchers may
   overlap; keep one debugger, optimizer, maintainer, and reviewer. Debugger
   leases assigned tests plus named originating source paths; parent work on
   independent paths may overlap. Keep one reviewer per immutable target and
   settle before review. A reviewer completion returns directly through the
   host mechanism; resume it once after its correction writes and begin a new
   cycle only for a new approved scope. Join every other agent
   and run
   `python3 <HARNESS_ROOT>/shared/gates/agent_ack.py <agent_id>` before advancing.
9. **Validate before output.** After the tree and all required receipts are
   settled, run the exact pre-final validation command supplied by
   `UserPromptSubmit` as the last tool. Emit the final response only after it
   prints `FINALIZED`; any later workspace change invalidates that receipt.
   `Stop` verifies the receipt and performs no expensive validation.

## Returns

An unparseable subagent return is not a result: re-dispatch once; if the
second return is also unparseable, halt to the developer. Never proceed on a
partial parse, never treat absence as an answer — every agent always emits,
so *no output* is never a legal state to interpret.

A typed `ENV` is never consumed as evidence. When it names one listed,
deterministic recovery, route that exact command through maintainer once and
re-check. Otherwise surface it and halt.

Researcher `MISS`, optimizer `WAITING` or `MISS`, and debugger `WAITING` are
typed incomplete states. Perform the named test, capture, or human gate
before advancing.

A reviewer that fails, times out, or returns malformed output leaves no valid
receipt and creates no project-global precondition. REV4 remains unsatisfied
for this session. A valid receipt expires after one hour and is removed at the
next prompt in the same session.
