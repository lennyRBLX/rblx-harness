# Luau contracts

Use for types, collections, text, or language features. Keep project conventions;
examples in external references do not override harness rules.

- `const` prevents rebinding, not mutation. Freeze config tables, including nested
  tables that must be immutable. Handle cycles if implementing deep traversal.
  Use named constants for domain limits; retain normal loop indices and sentinels.
- Narrow `unknown` at boundaries. Casts do not validate data; avoid `:: any` as a
  substitute. Use tagged unions for variants and `never` for exhaustive dispatch.
  Return no values with `()`. Preserve generic type packs in forwarding APIs.
  Read/write properties are type constraints, not runtime access control.
- Keep public aliases in `types write`. Verify solver support before type
  functions, attributes, or overload-heavy APIs; an RFC alone proves no rollout.
  Primitive intersections do not create runtime brands. Prefer validated wrappers
  when distinct ID types must be enforced without unchecked casts.
- Preserve nil-bearing packs with `table.pack`, `.n`, and
  `table.unpack(args, 1, args.n)`. A final call/vararg expands; parentheses and
  nonfinal positions truncate. Do not iterate raw value varargs as an iterator.
- Use `#` only for dense arrays; track sparse counts and test dictionary emptiness
  with `next(t) == nil`. Remove dense elements backwards, or swap-remove and
  revisit the swapped index when order is irrelevant.
- `table.create(n)` reserves array capacity; table-valued fill arguments alias.
  Clone/freeze are shallow. `table.clear` retains capacity and affects all aliases.
  Bound caches/pools; reset owned state on reuse. Avoid nil-as-cache-miss when nil
  is a valid cached result. Use loops/stacks for unbounded traversal.
- Use plain `string.find(..., 1, true)` for literal input; escape input for Lua
  patterns. Patterns are not JSON parsers. Use format for required precision,
  interpolation for readable substitution, `table.concat` for bulk assembly.
- Byte length differs from codepoints and graphemes. Validate external UTF-8;
  handle `utf8.len` failure. Truncate UI text at grapheme boundaries when needed.
- Use `os.clock` for local elapsed measurements, epoch time for stored dates,
  and `GetServerTimeNow` for shared timelines. Client timestamps remain untrusted.
- Use `error(message, 2)` for caller contract failures. Handle protected-call
  errors as unknown values; do not assume a table shape. A traceback handler
  must not yield. Pass arguments directly when a wrapper closure adds no behavior.
- Keep engine effects at the boundary and pure computation testable. Reuse project
  Signal/Trove/Retry packages; do not copy illustrative replacements. WRIT18 keeps
  metatable/newproxy patterns out of owned game code.

`check source --only style PATH...` accepts const declarations/functions;
`scaffold module` emits immutable bindings. The pinned Lute/LSP already parse
const; do not lower it to local or suppress syntax diagnostics. Source repair
retains the existing TYPE3 pragma policy; do not import mandatory strict/native
headers from an example.

Sources: [syntax](https://luau.org/syntax/),
[types](https://luau.org/typecheck/), [library](https://luau.org/library/),
[compatibility](https://luau.org/compatibility/).
