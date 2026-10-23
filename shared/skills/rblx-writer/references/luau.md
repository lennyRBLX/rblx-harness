# Luau edge cases

- `const` prevents rebinding, not mutation. Freeze nested config where required;
  clone/freeze are shallow. Handle cycles in deep traversal.
- Narrow `unknown`; casts do not validate. Preserve generic type packs; use `()`
  for no returns. Read/write type properties do not enforce runtime access.
  Verify solver rollout for type functions, attributes and complex overloads;
  an RFC is insufficient. Primitive intersections do not create runtime ID brands.
- Preserve nil-bearing packs with `table.pack`, `.n`, `table.unpack(args, 1, args.n)`.
  Only a final call/vararg expands; parentheses truncate. Raw value varargs are
  not an iterator.
- Use `#` for dense arrays; count sparse tables explicitly and use `next(t) == nil`
  for dictionary emptiness. Remove backwards, or revisit swap-removed indices.
- `table.create(n, tableValue)` aliases the fill table. `table.clear` retains
  capacity and affects aliases. Distinguish cached nil from a miss; bound pools
  and reset reused state. Use stacks/loops for unbounded traversal.
- Use plain `string.find(..., 1, true)` for literals; escape external pattern input.
  Use format for precision, interpolation for substitution, `table.concat` for bulk.
- Distinguish bytes, codepoints and graphemes. Validate external UTF-8, handle
  `utf8.len` failure, and truncate UI text at grapheme boundaries.
- Use `os.clock` for elapsed time, epoch time for stored dates, `GetServerTimeNow`
  for shared timelines. Treat client timestamps as untrusted.
- Use `error(message, 2)` for caller contract failures. Protected-call errors are
  unknown values; traceback handlers must not yield.
- When passing a colon method to `pcall`, pass its receiver explicitly. Use
  protected calls where failures have defined handling or owned state must be
  released after failure. Do not wrap cleanup calls in `pcall` solely to discard
  errors.
- Reuse project Signal/Trove/Retry packages. Keep metatable/newproxy patterns out
  of owned game code (WRIT18).

Pinned Lute/LSP supports `const`; do not lower it or suppress syntax diagnostics.
Preserve TYPE3 pragma policy; external examples do not require strict/native headers.

Sources: [syntax](https://luau.org/syntax/), [types](https://luau.org/typecheck/),
[library](https://luau.org/library/), [compatibility](https://luau.org/compatibility/).
