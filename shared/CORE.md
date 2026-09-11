# Rules

- `TOOL1`: Use `data_write`/`type_write` for data defaults, generated owner types & public declarations. New fields need no extra approval.
- `TOOL2`: Use API dump for Roblox facts; batch known access/inventory/behavior queries. Use MicroProfiler tools for captures.
- `TOOL3`: Use `context_pack` for whole Luau reads & scoped review diffs; `studio_output` for repeat console retrieval. Read [tool routes](TOOLS.md) on first use. Narrow `rg`/`sed` reads & Git summaries remain valid. State a tool limitation for a direct fallback; no extra approval.
- `CODE1`: Argon-resolved Luau is code truth. Validate every remote client arg & ownership before mutation.
- `CODE2`: At owner teardown, disconnect events, stop tasks & release retained instances.
- `TYPE1`: Resolve changed public project APIs with `type_lookup` before use.
- `TEST1`: For necessary Studio/live checks, human selects the environment & reports results unless the user authorizes agent execution. Report observed results only; distinguish passed, failed, unrun & skipped checks.
- `TEST2`: Test only an unresolved acceptance condition or plausible failure whose impact warrants the check cost. Use the smallest decisive check after related edits settle. Inspect simple, reversible text, spacing & constant edits directly; add tests only for a concrete behavior risk. Reuse documented behavior, source evidence & successful operation results within their scope. Fix an established cause before rerunning; reproducing a known failure needs a distinct diagnostic question.
- `TEST3`: Reuse a conclusive result for the same behavior, relevant source/dependencies, input/fixture & environment. Rerun only affected cases after relevant changes, failure, inconclusive evidence or an explicit repeat requirement; state what changed or remains unknown. Review, handoff, compaction, cleanup & final response alone do not invalidate evidence. Retrieve missing results before rerunning. Skip duplicate build/source-readback checks, unchanged post-review confirmations & broader suites without a distinct uncovered risk. Preserve required checks; skipped checks are not pending acceptance work.
- `TOK1`: Pass only decision-relevant evidence; preserve exact paths, APIs, literals & spans. Use `$rblx-plan` for Plan Mode and plan documents.
- `TOK2`: Reuse rules, API evidence & source spans already in this context at unchanged revisions. After compaction, load missing evidence. Pass agents scoped packs and existing check scope/results; wait for agent events instead of repeated status polls. Apply TEST2–TEST3 to verification.
- `API1`: Before engine access/behavior decisions, read [engine evidence](skills/rblx-writer/references/engine.md); preserve its context through review.
