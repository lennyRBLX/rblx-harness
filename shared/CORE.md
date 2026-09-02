# rblx-harness rules

- `AGENT1` — Use only `researcher`, `optimizer`, `reviewer`, and `debugger`.
  Agents do not spawn agents.
- `TOOL1` — Agents change data defaults, generated owner types, and public
  declarations only through `data_write` or `type_write`. New data fields do
  not require a separate human review.
- `TOOL2` — Use the API dump for Roblox documentation facts and the
  MicroProfiler tools for capture analysis.
- `CODE1` — Treat Argon-resolved Luau files as code truth. Validate every
  client-supplied remote argument and verify ownership before mutation.
- `CODE2` — Disconnect events, stop tasks, and release retained instances when
  their owner ends.
- `TYPE1` — Resolve changed public project APIs with `type_lookup` before use.
- `TEST1` — A human chooses Studio or live tests and reports the result. Never
  infer a pass.
- `TOK1` — Carry forward only decision-relevant evidence. Preserve exact paths,
  API names, literals, and source spans.
