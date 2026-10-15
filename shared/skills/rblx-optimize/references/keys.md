# Keys, indexes and order

- Compare dense bounded integer IDs with array indexing; include unused slots.
  Sparse numeric keys may use hash storage. Require range, density and lifetime.
- Compare scans with indexed access for small/few-query workloads, including build
  and updates. No universal crossover. Specialized guaranteed-hit paths need a
  proved invariant and preserved miss behavior where misses remain possible.
- Existing interned strings retain hashes; creating keys may hash/compare/copy and
  allocate. Constant fields can cache slots; numeric keys are not universally faster.
  Compare cached keys/IDs/hashes on the target runtime.
- Include index insertion/deletion, invalidation, duplicates and ownership. For costly
  sort keys, compare precomputation including refresh/mapping; compare maintained
  order when update/query frequency warrants it.
- For top-k, compare bounded heap O(n log k)/O(k) space or quickselect expected O(n)
  with full sort. Include final O(k log k) ordering, worst cases, ties and stability.

## Numeric and spatial identity

Require widths, deterministic encoding, identity and lifetime. Prove intermediate
products/sums, not only final keys: integers are exact through 2^53 in doubles;
f32 loses some integers above 2^24. Use lossless strings/bytes for wider identities,
never one double for a wide digest. Security uses suitable cryptographic constructions.

Define cells as floor(position/cellSize), with positive cellSize and consistent
negative/boundary handling. Compare collision-safe mixing with reversible mixed-radix
packing for bounded coordinates; prove packing ranges/exact arithmetic. Treat
`x*p1 + y*p2 + z*p3` and prime-multiply/XOR/modulo as hashes unless uniqueness is
proved. Primes guarantee neither uniqueness nor distribution; hashing is not
reversible compression. Specify width, wrap/truncation and bucket reduction.

Retain colliding entries and verify original keys for exact lookup, geometry for
broad phases. Hashes do not preserve spatial order. Measure occupancy, bucket
collisions and candidate checks on clustered, axis-aligned and negative coordinates;
random inputs can hide collisions. Include cell-size/capacity effects.

## Sources and limits

Upstream Luau `8387cfb461b38ce09e37c1e4c2811538ef1bf5cb`:
[table storage](https://github.com/luau-lang/luau/blob/8387cfb461b38ce09e37c1e4c2811538ef1bf5cb/VM/src/ltable.cpp),
[string hashes](https://github.com/luau-lang/luau/blob/8387cfb461b38ce09e37c1e4c2811538ef1bf5cb/VM/src/lstring.cpp),
[field/array paths](https://github.com/luau-lang/luau/blob/8387cfb461b38ce09e37c1e4c2811538ef1bf5cb/VM/src/lvmexecute.cpp),
[performance](https://luau.org/performance/). Hybrid array/hash growth may reallocate/
rehash; upstream is not a fixed Roblox build. Recheck changed implementations.

Algorithm references: [search](https://github.com/kevin-wayne/algs4/tree/master/src/main/java/edu/princeton/cs/algs4),
[top-k](https://github.com/kevin-wayne/algs4/blob/master/src/main/java/edu/princeton/cs/algs4/TopM.java),
[quickselect](https://github.com/kevin-wayne/algs4/blob/master/src/main/java/edu/princeton/cs/algs4/Quick.java).
Linear search O(n); sorted lookup O(log n), insertion O(n); hash expected O(1)
assumes suitable distribution and excludes key/hash/equality/resize costs.
[Teschner §§3–4](https://cg.informatik.uni-freiburg.de/publications/2003_VMV_collisionDetectionHashing.pdf)
uses prime-multiply/XOR/modulo, not the additive expression. Its constants/timings
are workload-specific; do not transfer Java/native timings to Luau.
