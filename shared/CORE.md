# CORE — project working rules

Apply each rule at its configured disposition. This summary does not elevate
guidance or reviewer-only findings into hard blockers.

- `TOK1` — Reuse valid ev.; repeat reads/checks after target change.
- `TOK3` — Min tokens; preserve meaning, exact literals, and Luau spans; never
  write minimized output to `.lua` or `.luau`.
- `SPD1` — Batch indep. reads/tool calls.
- `BC2` — Replicate global state with Folders + ValueObjects, per-player state
  with `Exclusive`, and events with remotes.
- `BC6` — Argon-resolved files are code truth. Type truth is replicated
  feature types, generated Default types, and local provider declarations;
  `type_cache` is derived. Ask `type_lookup` for types, Serena for other code,
  and Studio for DataModel facts.
- `TYPE7` — In the same diff, use `type_write` for a public Service,
  Controller, child-module, event, or owner-data shape change.
- `TYPE8` — Use `type_write` for every named type change. It owns public
  `ReplicatedStorage/Types/<Feature>.luau`, generated owner `Default.luau`, and
  private declarations in their provider.
- `TYPE9` — Cross-feature dependencies use exported Service, Controller, or
  child-module types and declared literal members.
- `WRIT33` — Before writing a changed external project-API member use, obtain
  its current declaration from `type_lookup` or the same-turn `type_write`.
- `DATA37` — Use generated `Typed.<Owner>` for owner data when available.
