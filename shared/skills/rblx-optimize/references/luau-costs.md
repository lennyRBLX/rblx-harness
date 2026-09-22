# Luau costs

Use for capture-backed CPU/allocation changes.

- Measure target workloads/builds; warm benchmarks and keep results observable.
  Use `os.clock` deltas. Heap totals include live and uncollected objects; one
  sample does not prove a leak. Own/reset memory categories in shared threads.
- Consider preallocation, reuse, bounded pools/caches, table.concat, swap-remove,
  stable query params, batched packets, and direct callback arguments only where
  the capture identifies their cost. Preserve alias, order, lifetime, and precision.
- Numeric `for` bounds evaluate once. Do not hoist `#t` for that claimed saving.
  Builtin imports/fastcalls often remove global lookup cost; do not localize math
  functions without evidence. Closure reuse depends on captured values and compiler
  choices; do not promise allocation-free callbacks or stable function identity.
- Vectors are value types; Vector3.new is not evidence of heap allocation. Use
  constants for intent. Prefer typed engine boundaries over vector casts through any.
- Native compilation targets measured computation, not waits or UI plumbing.
  Verify deployment support; Studio speed does not establish client speed.
  Query current codegen limits when generated code approaches compiler limits.
- Preserve query geometry/filter semantics and bound result counts only when
  truncation is acceptable. Do not replace exact queries with bounds silently.

Use `check source --only correctness,performance PATH...` for paired profiles,
explicit parallel scopes, standing labels, and allocation candidates. Static
findings are not measured gains. See [scope limits](../../rblx-writer/references/runtime.md).

Source: [Luau performance](https://luau.org/performance/).
