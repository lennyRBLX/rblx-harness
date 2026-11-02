# Delegated work

Prefer subagents when a concrete split improves speed or output quality with
efficient total token use. Handle small edits and settings tweaks directly unless
complexity or risk warrants delegation.

- For large tasks, maintain a small reusable team across research, implementation,
  testing, optimization and review; add agents only as needed. Give each agent a
  stable role in a coherent domain. Bound assignments by scope, owned paths and
  symbols, inputs, contracts, permissions and expected result.
- Use `researcher` for unresolved contracts and `debugger` while a failure's cause
  is unknown. `implementer` can combine scoped project research, writing and
  affected checks for one owner. Keep review independent of implementation.
- Reuse existing agents for related follow-ups. Keep role instructions stable;
  append assignments, changes and evidence to preserve useful, cacheable history.
  Start fresh when stale or unrelated context outweighs reuse benefits.
- For delegated features, GUI changes, fixes and implementation plans, run
  `optimizer` after implementation or drafting, resolve its findings, then run
  `reviewer` with that disposition. Preserve required roles, assessment order,
  read-only role limits and disabled nested delegation. Source/plan assessment
  needs no capture. For plans, assess dependencies, authority, lifecycle and
  acceptance.
- Each path has one writer per worktree. Independent scopes run in parallel;
  dependencies and conflicting writes run in sequence. The primary owns shared
  files and Git mutations. Continue useful work while agents run; wait for needed
  results. Independent chats use separate worktrees.
- Concurrent writers reserve assigned scopes once with `coord begin` and validate
  tokens with `coord check --lease` before mutation. Existing assignments supply
  scopes and owner/parent IDs. `coord end` releases completed work; native hooks
  release ended agents/sessions. Expiry stays unknown. Integration reuses a current
  `inspect diff --overlap` result until relevant inputs change. See
  [tool fields](../../../TOOLS.md#evidence).
- Share exact paths, APIs, literals, restrictions, open questions and valid
  findings/checks with their scope and revisions. Avoid duplicate work and rerun
  only affected or required checks. Return concise findings, references, check
  results and blockers; omit raw logs.
- Use permitted models and reasoning suited to task difficulty; reserve costly
  settings for demanding work. Preserve configured role profiles and inherit
  session settings where unspecified. For setting changes or comparisons, read
  [models.md](models.md).
- Judge total completion time, quality and cost across all agents, including
  retries; do not optimize cache-hit rate alone.

[Codex agents inherit parent permissions](https://learn.chatgpt.com/docs/agent-configuration/subagents).
Read-only and no-further-delegation requirements are role instructions. Local
configuration validation does not prove separate sandbox or tool isolation, and
a role file grants no additional access. The Claude `implementer` uses
[`model: inherit`](https://code.claude.com/docs/en/sub-agents#choose-a-model)
without an effort override; the four existing role profiles remain configured.
