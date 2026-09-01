# Harness gate and token-efficiency plan

Status: agent-efficiency rules, scoped leases, reusable role results,
same-task recovery, conditional validation, and the human-approved Claude Opus
route promotion are implemented. Authenticated Claude telemetry remains pending.

Revision: `3.0-agent-efficiency`, 2026-08-28.

## 1. Goal

Minimize total tokens per accepted task (TPA) while preserving harness behavior,
safety, hooks, gates, skills, agents, tools, APIs, configuration compatibility,
and output quality.

Keep a hard block only when it protects authorization, source ownership,
irreversible action, data safety, or a high-confidence correctness condition.
Auto-fix deterministic defects. Make heuristic and presentation rules advisory.

```text
TPA = sum(input_tokens + output_tokens for calls, agents, retries, and repairs)
      / accepted_tasks
```

Optimize TPA first, then cost, latency, steps, retries, and invalid calls. Count
cached input in logical tokens and separately in cached-input tokens.

## 2. Non-goals

- Preserve Roblox source conventions, generated project layout, public CLI
  arguments, hook event order, permission profiles, tool approval rules, and
  typed agent-result schemas.
- Do not skip the current researcher, optimizer, or reviewer route without an
  acceptance eval proving equal quality and a matching gate migration.
- Do not infer model economics from names. No route ranking changes without
  measured acceptance, token, latency, and cost data.
- Do not estimate tokens from characters. Byte limits are safety bounds, not
  token measurements.
- Do not add a telemetry dependency until the host exposes per-call usage and
  acceptance data to this repository.

## 3. Preserved invariants

- `shared/CORE.md` rules `BC2`, `BC6`, `TYPE7`, `TYPE8`, `TYPE9`, `WRIT33`, and
  `DATA37` retain their meaning.
- `roblox-new-game` keeps a gameplay-loop-first blocking interview, explicit
  post-interview harness-install consent, Git and GitHub-auth preflight, the
  pinned `.roblox-harness` submodule, deterministic scaffold, post-scaffold
  hook authorization prerequisite, `.roblox` sentinel, source-of-truth rule,
  and repair boundary.
- `roblox-writer` keeps conditional evidence roles, type/data gates, native
  file edits, exact recovery commands, dependency joins, settled review-target
  hashing, one malformed-return repair, and typed incomplete states.
- Hook order remains `SessionStart -> UserPromptSubmit -> PreToolUse ->
  SubagentStart -> SubagentStop -> Stop`, with `PreCompact` independent.
  Expensive completion validation runs through `finalize.py` as the last tool
  before visible output; `Stop` only verifies its settled-state receipt.
- `write_gate.py`, `record_check.py`, and `done_gate.py` remain fail-closed in
  their current directions. Review receipts remain session-, turn-, agent-,
  target-digest-, and TTL-bound.
- The five agent verdict sets and record arities in
  `shared/gates/record_check.py` do not change.
- Permissions, authorization identity, destructive-action, Studio-source,
  persistent-data, Git, symlink, and recovery boundaries remain hard. Trust,
  permission-profile, hook, discovery, and repaired local prerequisites
  revalidate in the same task.
- Codex and Claude agent instruction bodies remain behaviorally identical.

## 4. Current token costs

Measured 2026-08-28 with `tiktoken==0.9.0`, encoding `o200k_base`, over the
complete UTF-8 file payload. This is a deployed-family tokenizer measurement,
not an end-to-end TPA measurement.

| Payload | Before | Current | Change |
|---|---:|---:|---:|
| `shared/CORE.md` | 326 | 361 | +35 (+10.7%) |
| `shared/skills/roblox-writer/SKILL.md` | 1,512 | 1,762 | +250 (+16.5%) |
| `shared/skills/roblox-new-game/SKILL.md` | 1,564 | 1,885 | +321 (+20.5%) |
| `openai/AGENTS.template.md` | 175 | 181 | +6 (+3.4%) |
| `shared/handoff.md` | 305 | 17 | -288 (-94.4%) |
| five `openai/agents/*.toml` files | 2,745 | 2,594 | -151 (-5.5%) |
| five `claude/agents/*.md` files | 2,843 | 2,689 | -154 (-5.4%) |

`CORE.md` measured 293 tokens immediately before `TOK3`; the source-safe rule
is 35 tokens in its complete Markdown lines. It is always in both host contexts,
so evaluate it against all output it shapes and all later parent reconsumption,
not against one short response only.

Token-shortening eval, 2026-08-28:

| Candidate | o200k result | Disposition |
|---|---:|---|
| `with` -> `w/` | 1 -> 2 | reject |
| `without` -> `w/o` | 1 -> 2 | reject |
| `for example` -> `e.g.` | 2 -> 3 | reject |
| `and` -> `&`; `one` -> `1` | no reliable saving | reject |
| `input and output` -> `I/O` | 3 -> 2 | reject; also valid Luau |
| `is required to` -> `must` | 3 -> 1 | accept |
| `is not allowed to` -> `must not` | 4 -> 2 | accept |
| `is able to` -> `can` | 3 -> 1 | accept |
| `in order to` -> `to` | 3 -> 1 | accept |

The fixed five-role corpus saves 16 tokens: researcher 4, debugger 6,
optimizer 6, maintainer 0, reviewer 0. Exact maintainer and direct reviewer
records intentionally remain unchanged. One-shot Codex prompt trials with
`Min tokens; preserve meaning and exact literals.` retained the fixture facts
and produced 92 tokens on Luna, 92 on Terra XHigh, and 99 on Sol XHigh;
matching short-rule baselines were 98, 93, and 109. A Luna Max baseline was
not sent because the execution approval reviewer rejected the synthetic
command/path payload. These generations are directional evidence, not an
acceptance claim; the deterministic normalizer supplies cross-host behavior.

Baseline finding and remaining gaps:

- Before this revision, `record_check.parse_return` accepted unlimited bytes,
  lines, records, and field sizes. It now applies the P1 bounds.
- `api_dump` intentionally exposes full class, property, document-section,
  and code results. The researcher contract must select narrow verbs and
  return only consumed facts.
- No repository component receives `input_tokens`, `output_tokens`,
  `cached_input_tokens`, model cost, or an accepted-task event. Therefore
  current TPA, route cost, and cost per accepted task are not measurable.

## 5. Prioritized changes

### P1 - Bound agent returns

```yaml
location: shared/gates/record_check.py::parse_return; all five agent definitions
problem: Valid agent returns have no size or record-count ceiling, so one call can add unbounded parent context.
change: Enforce 8,192 UTF-8 bytes, 96 lines, 1,024 bytes per field, and role-specific record caps; state the caps in each agent contract.
token_effect: Worst-case model-visible agent return changes from unbounded to at most 8,192 byte-derived tokens; normal output schemas are unchanged.
risk: A legitimate large evidence set can require selection instead of bulk return.
validation: Existing round-trip fixtures pass; new byte, line, field, and per-role record overflow fixtures fail closed once and retain retry-once behavior.
rollback: Remove the four bounds and cap clauses; keep existing schema validation.
```

Role record caps: reviewer 24, researcher 24, optimizer 16, debugger 12,
maintainer 2. The agent must rank and return the facts needed for the current
decision; it must not split one logical result into extra calls merely to evade
a cap.

### P2 - Compress agent contracts

```yaml
location: openai/agents/*.toml::description/developer_instructions; claude/agents/*.md::frontmatter/body
problem: Agent prompts repeat role, no-write, evidence, empty-field, and no-prose rules in long forms.
change: State each invariant once, keep exact tools, thresholds, authority, verdicts, record shapes, and failure states, and delete examples already covered by validators.
token_effect: Measure full before/after host definitions with o200k_base; acceptance requires a reduction for every host total.
risk: Over-compression can weaken source authority, safety, or output conformance.
validation: Native-definition parity, model/effort/sandbox tests, every record-shape fixture, gate failure-direction tests, and the full verify suite.
rollback: Restore the previous prose; no state or schema migration is required.
```

### P3 - Compress always-shared context and handoff instructions

```yaml
location: shared/CORE.md; openai/AGENTS.template.md; shared/handoff.md
problem: Model-visible global and compaction text contains explanatory wording that does not add an invariant.
change: Use direct rules and a fixed three-section handoff contract while retaining every rule id, startup check, human gate, and disk-reference requirement.
token_effect: Measure each complete file before/after with o200k_base; all three must decrease.
risk: A shortened instruction could become ambiguous.
validation: Scaffold rendering and relink fixtures, CORE references, compact-gate session binding, and full verification.
rollback: Restore text only; generated files repair through the existing relink path.
```

### P4 - Shorten validated agent records

```yaml
location: shared/CORE.md; shared/gates/token_shrink.py; shared/gates/record_check.py; tools/tests/token_shrink_corpus.json
problem: Short output guidance is nondeterministic, and visual shorthand can increase tokenizer cost or lose facts.
change: Add one always-in instruction, validate the original schema first, then contract only allowlisted prose fields with measured replacements before mailbox storage.
token_effect: CORE adds 35 complete-file tokens; the fixed mailbox corpus saves 16 downstream tokens per pass, with further savings whenever the parent reconsumes those records.
risk: A rewrite could change a literal, condition, accessibility, or spoken clarity.
validation: Preserve required meaning. Compress in this order: DELETE → SIMPLIFY → CONTRACT → PROTECT-LUAU. Reject any edit that changes facts, scope, negation, conditions, numbers/units, names/code, tone, accessibility, or TTS clarity, or has more than one plausible meaning. Use no glyph or slash substitutions.
rollback: Remove TOK3, the record_check normalization call, token_shrink.py, and its fixtures; record schemas and persisted state need no migration.
```

The runtime allowlist changes only summaries, observed behavior, causes,
hypotheses, evidence, and candidates. It protects backtick, quoted, and
conservatively detected Luau spans and refuses `.lua` or `.luau` output.
Signatures, return types, guards, code, commands, paths, rule IDs, document
passages, enum items, repair records, and direct reviewer findings remain
exact. Ambiguous glyph and slash shorthand is disabled. `tiktoken` is
eval-only; runtime uses stdlib.

### P5 - Reuse evidence and overlap independent work

```yaml
location: shared/gates/agent_dispatch.py; agent_start.py; write_gate.py; record_check.py; done_gate.py; turn_stamp.py
problem: Duplicate role calls, global writer serialization, and repeated unchanged Stop checks add avoidable calls and latency.
change: Fingerprint role work by session/turn/role/normalized prompt/target digest; reuse accepted results; cap one repair; lease debugger paths; keep one debugger/optimizer/maintainer/reviewer; permit multiple researchers and independent paths; cache successful settled Stop checks.
token_effect: Exact duplicates consume the accepted typed record instead of another model call. Token impact depends on avoided calls and is recorded as TPA only when host usage is available.
risk: Stale reuse or a broad path lease could suppress required work.
validation: Turn-bound fingerprints, changed-target misses, schema-1 migration, repair cap, concurrent reservation, overlapping/independent lease, and Stop-cache invalidation fixtures.
rollback: Disable accepted-result reuse and scoped leases; schema-1 ledgers remain readable and turn cleanup removes schema-2 state.
```

### P6 - Promote Claude Opus routes with a recorded acceptance decision

```yaml
location: tools/tests/agent_route_corpus.json; tools/tests/agent_route_eval.py; claude/agents/*.md frontmatter
problem: DeepSWE identifies lower-effort Opus candidates, but aggregate benchmark rank does not prove role-schema acceptance or route economics.
change: Compare each production route and candidate on identical fixed role inputs. Default to schema, verdict, required-fact, and efficiency acceptance; permit an explicit human promotion override recorded in §10.
token_effect: Production uses lower-effort Opus routes; measured TPA remains pending authenticated telemetry.
risk: An unauthenticated or transient eval could be mistaken for evidence.
validation: Persist raw exit, schema, facts, tokens, latency, cost, and output; failed transport/auth never promotes.
rollback: Restore retained baseline frontmatter.
```

## 6. File/symbol map

| Area | File or symbol | Role |
|---|---|---|
| Global law | `shared/CORE.md` | Every-turn Roblox invariants |
| Parent route | `shared/skills/roblox-writer/SKILL.md` | Write, agent, retry, and escalation order |
| New project | `shared/skills/roblox-new-game/SKILL.md` | Interview and scaffold contract |
| Parent startup | `openai/AGENTS.template.md`, `claude/CLAUDE.template.md` | Generated project instructions |
| Agent prompts | `openai/agents/*.toml`, `claude/agents/*.md` | Role tools, authority, evidence, output |
| Agent lifecycle | `agent_dispatch`, `agent_start.main`, `record_check.main`, `agent_ack.main` | Fingerprint, claim, accept/repair, reuse, and acknowledgement |
| Output normalization | `token_shrink.normalize_schema`, `token_shrink.shrink_return` | Safe schema repair and measured prose contraction |
| Write leases | `write_gate.handle_agent_dispatch`, `source_writer_conflict` | Role caps, depth one, debugger path ownership, reviewer settlement |
| Completion | `finalize.main`, `done_gate.main`, `gatelib.stop_cache_*`, review receipts | Pre-final settled machine floor and fast Stop receipt verification |
| Context transfer | `shared/handoff.md`, `compact_gate.main` | Session-bound compaction context |
| Recovery | `gatelib.recovery_prompt_context`, `gatelib.recovery_invocation` | Exact bounded repair surface |
| Route eval | `tools/tests/agent_route_corpus.json`, `agent_route_eval.py` | Fixed Claude baseline/candidate acceptance and usage |
| Validation | `tools/tests/run_verify.py`, `tools/project_gate/project_gate.py` | Fixtures and repository gate |

## 7. Context loading

- Load `CORE.md` once through generated host instructions. `TOK3` applies to
  every model-visible response: minimize tokens while preserving meaning,
  exact literals, and Luau spans; never write minimized output to Luau source.
- Always-in (`CORE.md`): `TOK1` reuses valid evidence, `TOK3` minimizes tokens
  without changing meaning/literals, and `SPD1` batches independent tool work.
- Skill (`roblox-writer`): `TOK2` routes only required roles, `TOK4` reuses
  accepted results, `SPD2` overlaps independent work with path leases, and
  `SPD3` keeps the parent active until the first dependency join.
- Agent: researcher keeps short decision-complete evidence; debugger follows
  test deletion notes and its source lease; optimizer binds scope/paths/evidence;
  reviewer issues one settled-digest receipt; maintainer runs one exact repair.
- Load `roblox-new-game` only for project creation, adoption, relink, or
  backfill.
- Load `roblox-writer` only for managed-project Roblox code changes.
- Agent dispatches pass the bounded goal, refs, required paths, unresolved
  questions, target digest, and compact evidence. Accepted fingerprints are
  reused while turn, prompt, scope, target, and evidence remain valid.
- Research uses `type_lookup` for types, Serena for project code, Studio for
  DataModel/runtime state, and `api_dump` for Roblox API/docs. Use the narrowest
  query and document heading that can answer the question.
- Handoffs contain only session-bound facts that disk cannot supply.

## 8. Tool surface

- Preserve the explicit Claude tool lists and Codex sandbox modes.
- Researcher: read-only file/search shell sufficient for `api_dump`.
- Optimizer: read-only source/search and performance analyzers.
- Reviewer: read-only source/search; Studio read tools only for live facts.
- Debugger: read/search, assigned-test and named-originating-source writes, and
  controlled Studio Luau.
- Maintainer: shell only; `gatelib.recovery_invocation` admits one exact repair
  and the existing optional read-only `api_dump` query.
- Do not add tools or repeat tool schemas in prompts.

## 9. Delegation

- The parent coordinates source ownership and handles quick/mechanical work.
- Delegation depth is one. Researchers may overlap for independent questions.
  Keep one active debugger, optimizer, maintainer, and reviewer per writer
  session.
- Debugger owns assigned tests and named originating source paths. Serialize
  overlapping leases; parent and agents continue on independent paths.
- Maintainer owns one exact recovery command and optional supplied read-only
  API query; it consumes no project-source writer slot.
- Bind one optimizer and one reviewer to a feature/service/fix cycle. Settle
  source before review; resume that reviewer once after correction writes.
  Start a new cycle only for a new user-approved scope.
- Fingerprint normalized dispatch context. Reuse an accepted result for the
  same immutable target; changed prompt/target evidence creates new work.

## 10. Model routing

Production routes follow the human-approved Opus override:

| Role | Codex baseline | Claude production | DeepSWE basis |
|---|---|---|---|
| researcher | Terra Max | Opus Medium | 69.6% / 68.9% |
| maintainer | Luna High | Opus Low | 44.2% / 58.1%; nearest tested Opus |
| optimizer | Sol Extra High | Opus Medium | 70.7% / 68.9% |
| debugger | Sol Max | Opus Medium | 72.7% / 68.9% |
| reviewer | Sol Medium | Opus Low | 61.1% / 58.1% |

DeepSWE basis: v1.1 live snapshot referenced 2026-08-28. The 2026-08-28 run
used Claude Code 2.1.251; all ten calls returned `Not logged in` with zero API
tokens and zero cost. Human approval on 2026-08-28 overrides the default eval
gate and promotes the table routes. Retain the raw result and re-run after
`claude /login` to confirm or revise the decision:

```text
python3 tools/tests/agent_route_eval.py --command "npx -y @anthropic-ai/claude-code" --output <raw-json>
```

## 11. Retry/escalation

- Agent output repair cap: one matching fingerprint retry. Safe delimiter
  padding and empty fields normalize first; a second non-reviewer defect
  becomes typed `ENV`, while reviewer identity/schema remains hard.
- Git repair cap: one exact `git_sync.py repair` followed by one retry of the
  original write.
- Other recoveries: one exact command selected from `RECOVERY_KINDS`; resume
  only after its postcondition passes.
- Review correction: a write invalidates the receipt. Reuse the cycle's one
  optimizer result where its scope/evidence remains valid; settle a new digest
  and resume the same reviewer once for verification.
- Stop on accepted output, sufficient evidence, `ENV`, `MISS`, `WAITING`, an
  unresolved contradiction, a human ruling, or an exhausted retry.
- Never escalate past missing authorization, destructive-action approval,
  data-field approval, Studio mismatch, or unavailable evidence.

## 12. I/O contracts

Agent output remains the existing first-line verdict plus pipe-delimited fixed
records. `record_check.TOKEN_ARITY`, `VERDICTS`, and `AGENT_RECORDS` are the
canonical schema. `token_shrink.normalize_schema` removes delimiter padding
and represents an empty field as `void` before parsing. No reasoning, work log,
request restatement, raw search log, or redundant summary is returned.

Handoff remains:

```yaml
session: <session_id>
tried: <failed path and reason only>
where: <path and unfinished state only>
open: <human decision only>
```

Public CLI stdout and exit codes remain unchanged except that oversized agent
returns are rejected through the existing `record_check: BLOCKED` repair path.

## 13. Telemetry

Required future per-task record:

```text
task_class route reasoning agents tool_calls retries steps
input_tokens output_tokens cached_input_tokens total_tokens
accepted failure latency cost TPA cost_per_accepted
```

Count system/developer prompts, agent definitions, tool schemas, retrieved
context, files, handoffs, retries, and repairs. Cached tokens reduce billed
cost and latency, not logical token volume.

Current blocker: hooks receive lifecycle payloads but no model usage, price,
or acceptance event. Do not synthesize these values. Integrate telemetry only
when the host provides trusted per-call usage and the project defines an
accepted-task event.

The route runner records CLI-provided input/output/cache tokens, latency, cost,
schema, verdict, required facts, retries, and raw output. Transport/auth errors
are non-acceptance and cannot promote a route. The 2026-08-28 raw result is
ephemeral at `/tmp/harness-agent-route-eval.json`; its durable result is the
zero-token authentication failure recorded in §10.

## 14. Validation

Run:

```text
python3 tools/tests/run_verify.py
<isolated-python-with-tiktoken-0.9.0> tools/tests/token_shrink_eval.py
python3 tools/tests/agent_route_eval.py --command <authenticated-claude-command> --output <raw-json>
python3 tools/project_gate/project_gate.py --project-root <harness-root>
```

Coverage must include hook/gate order, public API/config compatibility, tool
schemas, agent return bounds, retry caps, review digest, output schemas,
missing-context recovery, fingerprint migration/reuse, repair allowance, path
leases, Stop-cache invalidation, safety/auth boundaries, scaffold rendering,
route-corpus shape, and Codex/Claude prompt parity.

Measure complete changed prompt files before and after with `o200k_base`.
For token shortening, require the fixed five-role output total to decrease,
every shortened return to retain schema and expected facts, every exact field
to remain byte-equal, every Humanoid/arena Luau span and identifier casing to
remain byte-equal, every Luau output destination to fail closed, and spoken
mode to avoid slash shorthand. Count the
always-in rule cost against cumulative shaped output plus downstream
reconsumption. TPA and acceptance pass criteria are deferred because their
instrumentation is absent; do not report prompt-token reduction as TPA
improvement.

## 15. Rollout/rollback

- Roll out the shared prompt rule and post-validation mailbox normalizer
  together.
- Generated project agent files update through existing relink behavior; Claude
  agent symlinks update immediately.
- Dispatch ledger schema 1 is accepted and rewritten as schema 2 on the next
  reservation. Turn stamp removes completed/abandoned entries at the next
  turn; no project data, API, hook, or receipt migration is required.
- Roll back prompt files and `record_check` caps together if record overflow
  causes accepted-task regression. Existing state remains readable.

## 16. Completion checklist

- [x] Compress `CORE.md`, `AGENTS.template.md`, and `shared/handoff.md`.
- [x] Compress both runtime definitions for all five agents.
- [x] Preserve identical agent bodies across runtimes.
- [x] Add byte, line, field, and role-record bounds to `parse_return`.
- [x] Add overflow and existing-schema fixtures.
- [x] Run focused record, agent, scaffold, and compact tests.
- [x] Full verification: 198/198 pass.
- [x] Harness project-gate: `PROJECT_GATE|READY`.
- [x] Measure full before/after prompt tokens with `o200k_base`.
- [x] Test literal shorthand, phrase contraction, and minimal prompt variants.
- [x] Add the five-role corpus and reproducible `o200k_base` eval.
- [x] Normalize only allowlisted non-reviewer prose after schema validation.
- [x] Preserve exact fields, quoted/code spans, reviewer output, repair output,
  and spoken slash clarity.
- [x] Report TPA as unavailable until host usage and acceptance events exist.
- [x] Add `TOK1`, `TOK3`, and `SPD1` to always-in context; add bounded routing,
  reuse, overlap, and join rules to `roblox-writer`.
- [x] Add normalized fingerprint ledger schema 2, accepted-result reuse, one
  repair identity, schema-1 migration, and next-turn cleanup.
- [x] Add debugger path leases, independent-path concurrency, maintainer
  recovery lease, serial specialist caps, and depth-one Claude config.
- [x] Add same-task trust/profile/hook/discovery/local-repair recovery while
  retaining hard host/session/project identity checks.
- [x] Add settled Stop cache and digest invalidation fixtures.
- [x] Add fixed five-role Claude corpus and route runner.
- [x] Apply the human-approved Opus promotion override; retain the
  unauthenticated result and runner for later telemetry.
- [x] Re-run full verification (198/198) and project gate
  (`PROJECT_GATE|READY`) after final plan sync.

## 17. Final control policy

Sections 17–23 supersede any preservation clause above that conflicts with a
listed disposition.

Human review: approved. Hooks, named gates, rule blockers, auto-fixes,
advisory/reviewer-only rules, workflow blockers, human-only blockers, and
new-project blockers are accepted as listed. All cuts are accepted except
`WRIT31`, which remains hard.

| Disposition | Meaning |
|---|---|
| Remain hard | Deny the affected mutation, agent result, compaction, or completion. |
| Auto-fix | Run one bounded, idempotent repair, re-check, then deny only if repair fails. |
| Soften | Warn or defer to the final reviewer; do not deny the current operation. |
| Cut | Remove the control from the default path. |

No unlisted rule remains a hard blocker. A crash may fail closed only for the
operation whose safety depends on that check. A read-only operation does not
fail because a write-only check, Studio check, network check, or formatter did
not run.

## 18. Hook disposition

### Managed Roblox projects

| Hook | Current function | Final disposition |
|---|---|---|
| Project `SessionStart` (Codex) | Verify trust, permission profile, project hooks, and generated integration; create authorization. | Remain hard for host/session/project identity. Auto-relink static project integration, refresh trust/profile/hook bytes, report changed project hooks as a maintenance advisory, and continue the same task. |
| Project `SessionStart` | Verify project hooks and payload; prepare corpus, globals, type cache, toolchain, Git, Studio, links, agents, and place map; create authorization. | Remain hard for hook/session identity and mutation prerequisites. Auto-fix deterministic local state. Make Studio, place-map, corpus, and toolchain checks conditional on the requested operation. |
| `UserPromptSubmit` | Bind a turn baseline; clear stale receipts, type records, and veto state. | Remain. Auto-fix stale per-turn state. Deny only when a source-changing turn cannot obtain a baseline. |
| Project `PreToolUse` | Authorize all tools; fetch origin; check environment; parse and scan writes; format full writes. | Remain hard for source mutations, exact maintenance commands, and Studio `execute_luau`. Read-only tools receive authorization validation only. Run the remote check once at the first mutation, not before every tool. |
| `SubagentStart` | Add context, claim dispatch identity, lease paths, and reserve reviewer state. | Keep one debugger/optimizer/maintainer/reviewer; permit multiple researchers and independent leases; bind reviewer to one settled digest. |
| `SubagentStop` | Validate fixed verdict/record schemas and create mailbox or review receipts. | Normalize safe schema syntax; remain hard for reviewer identity, verdict, live rule IDs, target digest, and size bounds. Mark valid fingerprints accepted; allow one matching repair; then return typed non-reviewer `ENV`. |
| `PreCompact` | Require a session-bound `shared/handoff.md`. | Auto-fix. Write/update the bounded handoff from session and turn state. Deny only when session identity is absent or the handoff cannot be written. |
| `Stop` | Deliver mailbox returns; run type, style, replication, LSP, review, boot, structure, and performance checks. | Remain hard once per changed settled input for Luau correctness and review receipt. Cache success by turn/target/checker/auth digest; invalidate on input change. Auto-format; optional analyzers remain advisory. |

Claude uses the same project-hook dispositions. Its `fork` SessionStart source
remains valid. Codex and Claude project hooks perform source and environment
enforcement; user-scope harness hooks are not part of project installation.

### Harness repository

| Hook | Final disposition |
|---|---|
| `SessionStart` | Remain hard for harness hook digest, host, session, trust, and Codex permission-profile identity. |
| `UserPromptSubmit` | Remain for an explicit absolute `project-root:` binding. No project selection means harness-local validation only. |
| `Stop` | Remain for deterministic harness-local verification. Run a live managed-project gate only when the user explicitly supplied `project-root:`. |

## 19. Named hard gates

| Gate | Current scope | Final disposition |
|---|---|---|
| `GATE1` | Reject non-serializable persistent data. | Remain hard on the affected data write. |
| `GATE2` | Restrict write roots; reject symlink/museum writes and service-level `init*` scripts. | Remain hard. Keep the Stop tree sweep for files created outside host edit tools. |
| `GATE3` | Prevent direct writes to generated PlayerData modules. | Remain hard; `type_write` stays the single writer. |
| `GATE4` | Aggregate authorization, cache, corpus, toolchain, generated globals, type cache, hook, Studio, place-map, and checker failures. | Split it. Remain hard for authorization, cache-write ability needed by the operation, required checker crashes, and missing required inputs. Auto-fix corpus, globals, type cache, toolchain, links, and relink. Soften unrelated or optional environment failures. Cut the aggregate rule that any report or skip blocks all work. |
| `GATE5` | Prevent Studio `execute_luau` from creating scripts or assigning `Source`. | Remain hard. Studio is for tests and DataModel operations, not source writes. |
| `GATE6` | Fetch and compare the canonical branch before every supported tool. | Soften to the first source mutation and final project validation. Keep unmerged state, invalid repository, unreadable refs, and wrong branch hard for mutation. Auto-run one exact `git_sync` repair for behind/diverged state. Do not fetch for reads or every tool call. |
| `GATE7` | Deny compaction without a session-bound handoff. | Auto-fix the handoff. Keep only missing session identity or an unwritable handoff as hard. |

## 20. Rule blocker disposition

### Remain hard

These checks have a direct safety, data-integrity, runtime-correctness, source-
ownership, or review-integrity effect:

| Area | Rule IDs and retained condition |
|---|---|
| Security and runtime boundary | `BC1`, `BC7`, `WRIT18` |
| Persistent data and payments | `DATA1`, `DATA5`, `DATA8`, `DATA17`, `DATA21`, `DATA23`, `DATA29`, `DATA30`, `DATA31`, `DATA32`, `DATA33`, `DATA35`, `DATA36`, `DATA37` |
| Debug containment and executable proof | `DEBUG2`; `DEBUG11` when the changed task requires a connected Studio run |
| Marketplace ownership | `DES2` |
| Streaming/runtime correctness | `OPT8`, `OPT12`, `OPT16`, `OPT17` |
| House physics form | `WRIT31` |
| Type and API correctness | `TYPE1`, `TYPE7`, `TYPE8`, `TYPE9`, `WRIT23`, `WRIT25`, `WRIT29`, `WRIT30`, `WRIT33` |
| Remote declaration | `WRIT8` |
| Review integrity | `REV4`; reviewer `OUT1`/`REV10` schema, live-ID, receipt, digest, and TTL checks |

Apply these checks to the resulting file or settled change set. Do not run an
expensive full scan twice for one unchanged result.

### Auto-fix

| Rule or blocker | Required repair |
|---|---|
| `BC3` | Replace legacy `wait`, `spawn`, and `delay` with the matching `task.*` form through a verified syntax transform. |
| `TYPE3` | Remove file-level checking pragmas when the checked-in `.luaurc` supplies the mode. |
| `BC5` tabs; `WRIT12`, `WRIT14`, `WRIT15`, `WRIT22` | Keep the existing parse-verified, idempotent style pass. These never remain as hard findings after a successful repair. |
| Stale/missing corpus | Run one `api_dump --sync`, then re-check freshness. |
| Missing API globals | Run one `api_dump --emit-globals`, then re-check. |
| Stale/missing type cache | Run one exact type-cache ensure/recover command, then re-check. |
| Missing toolchain | Run one exact toolchain installer when network and tool-root permissions are available. |
| Generated hooks, agents, skills, links, and config | Relink once, report changed hook bytes as maintenance advisory, revalidate discovery, and continue the same task. |
| Behind/diverged Git state | Run one exact `git_sync.py repair`, restore local work, then retry the original mutation once. |
| Missing/stale handoff | Generate the four-field, session-bound handoff before compaction. |

### Soften to advisory or reviewer-only

| Area | Rule IDs or blocker |
|---|---|
| Boilerplate and naming | `BC4`, the naming clause of `BC5`, `WRIT1`, `WRIT4`, `WRIT10`, `WRIT11`, `WRIT19`, `WRIT32` |
| Diagnostics and release housekeeping | `DEBUG8`, `DES5` |
| Heuristic architecture/replication | `REV6`, `WRIT20`, `WRIT26` |
| Performance evidence and placement | `OPT1`, `OPT11`; all `perf_audit` findings (`OPT15`, `OPT18`, `OPT19`, `OPT20`) remain advisory |
| Agent output formatting | Non-reviewer `OUT1`/`REV10` problems get one automatic repair request, then typed `ENV` without a project-wide block. |
| Optional environment | Studio connection, place mapping, live corpus freshness, and optional analyzer availability when the current operation does not consume them. |

### Cut

| Rule or blocker | Removal |
|---|---|
| `TYPE10` | Remove the ban on return types and annotated locals. The type checker decides correctness. |
| Universal read blocking | Remove Git, Studio, corpus, toolchain, formatter, and source-scan prerequisites from read-only tools. |
| Duplicate Codex enforcement | Remove full source/environment enforcement from the user-scope `PreToolUse`; keep it at project scope. |
| Per-tool remote fetch | Remove GATE6 fetches after the first unchanged mutation check in a turn. |
| Durable malformed-agent precondition | Do not append `GATE4` after a non-reviewer fails schema repair twice. |
| Hard missing-handoff veto | Replace with automatic handoff generation. |
| Default live-project verification | Remove the two live `arena` cases from `tools/tests/run_verify.py` default execution. Keep them in an explicit live-integration suite. |
| Skip-equals-failure | A skipped conditional check is not a project-gate failure. A required check that cannot run is a named failure, not `SKIP`. |
| Unrequested live project gate | Do not validate a managed game from a harness Stop unless `project-root:` selected it. |
| Completion noise | Remove the commit prompt from the Stop hook. Commit, push, and release remain user decisions. |

## 21. Workflow blockers

| Workflow control | Final disposition |
|---|---|
| Research before every Roblox write | Soften. Require research when the change depends on Roblox API/docs, current project behavior, Studio state, or an unresolved fact. Do not require it for verified mechanical edits. |
| Optimizer after every write | Soften. Require it for performance-sensitive code, frame work, replication volume, allocation/lifecycle changes, or a reported performance symptom. |
| Reviewer on changed Luau | Remain hard. The settled digest, affected paths, session, turn, verdict, and TTL must match. |
| Debugger before a defect fix | Soften. Require it when the defect cause is not already reproduced and evidenced. |
| Maintainer authority | Remain hard. Permit only the exact listed recovery command and allowed read-only API queries. |
| Agent capacity | Permit multiple researchers. Keep one debugger, optimizer, maintainer, and reviewer; serialize overlapping debugger/parent paths. |
| Delegation depth one | Remain until nested receipt and authorization binding exist. |
| One malformed-return retry | Remain. Do not retry indefinitely. |
| `MISS`, `WAITING`, `ENV`, contradiction, or missing evidence | Remain hard before the parent consumes the result. The parent may perform the named evidence action or stop. |
| Any write after optimization/review | Invalidate the receipt. Reuse the cycle optimizer while scope/evidence remains valid; settle the corrected digest and resume its reviewer once. |

## 22. Human-only blockers

The harness must not auto-approve these conditions:

- Trust a project and select an active permission profile. Changed loaded hook
  bytes are advisory for later integration maintenance.
- Approve a destructive action, deletion, commit, push, release, or persistent
  data-field/schema change.
- Publish a place; choose between ambiguous Studio places; resolve a wrong
  project/place decision; approve GUI ownership or other product decisions.
- Resolve or abort an existing merge/rebase; choose a different branch;
  configure a missing remote or upstream.
- Supply missing file-shaping or product decisions that cannot be derived from
  repository state.

Require a new task only when authorization identity names another host,
session/task, or project. Retry host discovery after developer repair and
continue when it succeeds. Trust/profile, hooks, agents, skills, config, local
cache, globals, type cache, formatting, Studio/place availability, and Git
drift continue in the same task after their postconditions pass. A missing or
ambiguous place decision still waits for the developer.

## 23. New-project blockers

Keep the following scaffold blockers:

- Initial place names, scoped keystone Services, and scoped keystone
  Controllers.
- Explicit harness-install consent after the interview, an owned Git root,
  authenticated GitHub access to `lennyRBLX/rblx-harness`, and successful
  project-local relink.
- Valid managed-session authorization, project trust, approved hooks, and the
  `.roblox` sentinel before interview answers are written.
- Deterministic output, source-of-truth layout, service-entry naming, and
  generated integration ownership.

Questions may be batched when the user already supplied several answers.
Re-ask only missing or contradictory fields. Gameplay-loop context may guide
keystone proposals but is not recorded or treated as a future constraint.
Every file-shaping question includes a concrete example derived from that
gameplay loop. The gameplay loop is asked first; installation consent is asked
only after every interview answer is complete.
Routine features and playtests do not require a stage, milestone, final-build
path, or new-game re-interview.
