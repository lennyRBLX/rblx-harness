# Rules

- `TOOL1`: Use `data_write`/`type_write` for data defaults, generated owner types & public declarations. New fields need no extra approval.
- `TOOL2`: Use API dump for Roblox facts; MicroProfiler tools for captures.
- `CODE1`: Argon-resolved Luau is code truth. Validate every remote client arg & ownership before mutation.
- `CODE2`: At owner teardown, disconnect events, stop tasks & release retained instances.
- `TYPE1`: Resolve changed public project APIs with `type_lookup` before use.
- `TEST1`: Human selects Studio/live & reports results; never infer a pass.
- `TOK1`: Pass only decision-relevant evidence; preserve exact paths, APIs, literals & spans.
- `API1`: Before engine access/behavior decisions, read [engine evidence](skills/rblx-writer/references/engine.md); preserve its context through review.
