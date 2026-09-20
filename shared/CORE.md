## Roblox work

- Use Argon-resolved source for project behavior. Validate remote arguments and
  ownership before mutation; release connections, tasks, and instances at teardown.
- Use `python3 rblx-harness/tools/harness.py types write` for data defaults,
  generated owner types, and public declarations. It validates and commits related
  files together. Resolve changed public APIs with `types read`.
- Before relying on engine access or behavior, use current scoped engine evidence;
  query `api` only for missing or invalidated answers. Keep caller, phase,
  restrictions, and source revision; use the selected skill's engine reference.
- Run commands only for missing evidence or required changes. Use scoped `rg`,
  bounded reads, native edits, and Git. Batch independent operations; sequence
  dependencies. Inspect every result; preserve failures and required output.
  Use non-login shells unless initialization requires otherwise. Use harness
  helpers for domain validation or batched evidence; read only needed
  `rblx-harness/shared/TOOLS.md` sections and unfamiliar command help.
- For Studio checks, use the user's selected environment and existing execution
  authorization. Otherwise obtain the human result. Keep authored source changes
  in stopped Edit mode; report passed, failed, reused, unrun, and skipped checks accurately.
- Checks require a request, unresolved acceptance condition, or material risk;
  results must affect a decision and evidence must be missing or invalid.
  Record the need, decision, and gap in task context. Required checks remain
  required. After edits settle, run the smallest decisive check. Add tests
  only for unresolved behavior, not prose or implementation-mirroring assertions.
  Skip duplicate checks and covered parsing; preserve required repeats.
  Use full suites only for broad changes or explicit requests.
- Pass exact paths, APIs, literals, restrictions, and open questions. Retain
  evidence revisions, scope, inputs, and environment in existing context or
  requested artifacts. Reuse until relevant dependencies, fixtures, options,
  or environment change; rerun only affected checks. Compaction, review, and
  completion do not invalidate evidence. Create no receipts.
