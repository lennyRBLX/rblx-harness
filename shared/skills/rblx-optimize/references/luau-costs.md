# Luau costs

Use for source/plan candidates and measured CPU, allocation, or representation decisions.

## Decision and measurement

- For a candidate, require source location, consuming path, collection size/key
  distribution, hit/miss ratio, update rate, required results, precision, and
  lifetime. Return missing inputs and the smallest comparison that can change
  the decision. No automatic representation rewrite or static speed claim.
- For each affected operation, use build, load, active runtime, save, or transfer
  as its phase; state frequency and reuse. Include hashing, key creation,
  extraction, encoding, and decoding only where performed. Data never decoded in
  active runtime has no active-runtime decompression cost.
- For selection, require separate CPU, latency, retained memory, peak memory,
  and byte budgets plus a material-problem threshold. Compare lifetime costs
  (one-time work plus frequency times per-operation work) and amortized costs.
  Prefer extra CPU when material memory/transfer/storage savings fit that phase's
  latency budget. No requirement to select the lowest CPU time.
- For benchmarks, match production representations and access patterns; keep
  datasets, seeds, hit/miss distributions, updates, semantics, precision, and
  environment comparable. Separate representation changes from algorithm changes.
  Measure index construction, insertion/update, lookup, extraction, and sorting
  independently when affected; report setup/conversion separately from steady
  state and include both in lifetime conclusions.
- Before claiming gains, require equivalent results or verified declared error
  bounds. Measure affected latency/throughput, retained/peak memory, allocations/GC,
  encoded/transmitted bytes, and codec costs. Label estimates separately. Include
  retained original strings, ID/dictionary mappings, indexes, metadata, copies,
  decoded tables, and temporary allocations; buffer length alone is not heap use.
- For source candidates, use `check source --only performance PATH...`; OPT21
  reports direct scans, sorts, computed keys, and codecs. Require human inspection
  for aliases, helper effects, cardinality, frequency, and phase. DATA38 in
  `--only correctness` checks literal codec widths/ranges; computed schemas remain
  a review obligation.
- For paired HTB1 timing groups, use `profile results LOG --side SIDE --script NAME
  --run RUN --compare BASE CANDIDATE`. Use workload names for phase/operation and
  method names for alternatives. The tool rejects missing/mismatched groups and
  reports candidate-minus-base timing and a conditional timing crossover for paired
  setup/script/teardown groups. Require production reuse and comparable batching
  before applying it; require non-yielding timed regions for CPU claims.
  Timing records cannot establish memory, byte savings,
  semantic equivalence, environment equality, or platform storage reduction.

## Keys, search, and order

Stable algorithm facts below assume the stated data structure and comparison
cost. Runtime details below describe upstream Luau, not a fixed Roblox build.

- For dense bounded IDs, prefer direct array indexing. Require integer range,
  density, identity, and lifetime; account for unused slots. Sparse numeric keys
  may occupy hash storage. No conversion of sparse/content keys to a large array
  without a measured space benefit.
- For small collections or few queries, compare a scan with indexed access,
  including index construction and updates. Linear search is O(n); a sorted
  array supports O(log n) comparisons but O(n) insertion/movement. Hash lookup is
  expected O(1) under suitable distribution, with hashing/equality, collisions,
  resizing, and key creation outside that shorthand. No universal size crossover.
- For guaranteed hits, use specialized paths only when the invariant is
  established; preserve failure behavior where misses remain possible.
- For repeated key creation or expensive comparison, compare cached keys,
  numeric IDs, and collision-safe hashes. Luau stores interned string hashes;
  lookup of an existing string does not rehash its bytes. Creating a string can
  hash/compare/copy bytes and allocate; content hashing adds its own cost.
  Constant-field access can use cached slots; no blanket claim that numeric keys
  beat constant string fields. Require target-runtime evidence for those rankings.
- For indexes, require construction, insertion/deletion, invalidation, duplicate
  handling, and ownership/lifetime costs. For repeated sorts with costly key
  extraction, precompute sort keys and include refresh/mapping costs. Compare
  full sort with maintained order when update/query frequency justifies it.
- For partial results, compare bounded selection with full sorting. A bounded
  heap can use O(n log k) work and O(k) space; quickselect has expected O(n) work
  with algorithm-dependent worst cases and does not order the selected results.
  Include any final O(k log k) sort, tie rules, and stable-order requirements.
- For numeric IDs or hashes, require field width, exact representability,
  deterministic byte encoding, identity, and lifetime. Luau number integers are
  exact through 2^53; f32 cannot represent every integer above 2^24. Use lossless
  strings/byte fields for wider identities. No packing a wide digest into one
  double or assuming hash uniqueness/order preservation. Require collision
  buckets and original-key verification when a hash substitutes for equality.
  Separate performance hashes from security hashes; security decisions require
  a suitable cryptographic construction, not an internal table hash.

Runtime evidence: [Luau performance](https://luau.org/performance/) and upstream
Luau revision `8387cfb461b38ce09e37c1e4c2811538ef1bf5cb`:
[table layout/lookup/rehash](https://github.com/luau-lang/luau/blob/8387cfb461b38ce09e37c1e4c2811538ef1bf5cb/VM/src/ltable.cpp),
[string interning/hashes](https://github.com/luau-lang/luau/blob/8387cfb461b38ce09e37c1e4c2811538ef1bf5cb/VM/src/lstring.cpp),
[constant-field and array paths](https://github.com/luau-lang/luau/blob/8387cfb461b38ce09e37c1e4c2811538ef1bf5cb/VM/src/lvmexecute.cpp).
Tables use hybrid array/hash storage; growth can reallocate and rehash. Require
new scoped source evidence only when a relevant implementation changes.

Algorithm sources: Sedgewick/Wayne's [search implementations](https://github.com/kevin-wayne/algs4/tree/master/src/main/java/edu/princeton/cs/algs4)
(`SequentialSearchST`, `BinarySearchST`, `LinearProbingHashST`) and
[bounded selection](https://github.com/kevin-wayne/algs4/blob/master/src/main/java/edu/princeton/cs/algs4/TopM.java),
[quickselect](https://github.com/kevin-wayne/algs4/blob/master/src/main/java/edu/princeton/cs/algs4/Quick.java).
No transfer of Java timing constants to Luau.

## Compact formats

- For large machine-processed datasets, compare compact schemas, packed buffers,
  narrow fields, dictionary encoding, bit packing, quantization, delta encoding,
  and compression through the actual consuming path. Large player-created maps
  are candidates; frequently inspected PlayerData often favors readable fields.
  Require workload, precision, inspection, recovery, and migration requirements;
  no fixed exclusion for either category.
- For fixed-width packing, require field ranges, signedness, offsets, endianness,
  bounds, and overflow behavior. Packing changes layout; it is not compression.
  Dictionary encoding replaces repeated values with IDs; require dictionary
  bytes/lifetime, update behavior, and decoding costs. Bit packing stores fields
  in fewer bits; require masks, cross-byte access, and independently bounded reads.
- For quantization, require range, resolution, rounding, overflow behavior, and
  accepted error. Quantization maps values to a finite grid and may lose accuracy;
  e.g. nearest-grid reconstruction at step s has error at most s/2 within range,
  excluding overflow and floating-point error. Require verification at boundaries
  and on the consuming operation. Fixed-width quantized values can support random
  access and independent updates; changed scale/range may require re-encoding.
- For delta encoding, require bases, reset/checkpoint rules, dependency limits,
  update behavior, and bounded reconstruction. Deltas store differences from a
  base or previous value; they are lossless only with exact arithmetic and no
  overflow. Smaller magnitudes can aid packing/compression but do not by themselves
  reduce a fixed-width field. Chained deltas require prefix reconstruction;
  checkpoints trade bytes for random access. Updates can affect adjacent deltas
  or a dependent suffix. Require error propagation bounds if combined with
  quantization; no assumption that each reconstructed value has only one-step error.
- For application compression, measure encode/decode, scratch/copies, output size,
  and random-access/update requirements; blocks/checkpoints may be needed. Prefer
  leaving data packed when the consumer can operate on it directly. No assumed
  benefit from compressing already compressed or small payloads.
- For persisted format changes, require versioned decoding, bounded lengths and
  reads, recovery, and compatible migration proportional to the change. Require
  old/new format fixtures and declared error checks before changing stored data.

Primary format sources: [Khronos quantization](https://github.com/KhronosGroup/glTF/blob/main/extensions/2.0/Khronos/KHR_mesh_quantization/README.md),
[Lemire/Boytsov integer packing and differential coding](https://arxiv.org/abs/1209.2137).
Use these for mechanisms; their native/SIMD benchmark results do not predict Luau.

## Engine contracts

Use `api behavior buffer-layout-copy`, `api behavior encoding-codec-bounds`, and
`api behavior datastore-size-compression` for reusable sourced contracts; use
`api access EncodingService.METHOD` for affected caller/phase metadata. Preserve
unknown capabilities, MCP access, and engine-build alignment; documentation does
not authorize Studio execution. Recheck only missing or invalidated evidence.

- For buffers, require zero-based byte offsets (bit offsets for readbits/writebits),
  bounds, and little-endian numeric fields. Buffers are fixed-size mutable storage;
  Roblox API transfers copy them and do not preserve identity. Include copies in
  peak memory. `writebits` accepts 0..32 bits and writes low bits; require explicit
  range policy where truncation would change identity or accuracy.
- For EncodingService, use documented algorithm/level contracts. Require
  `GetDecompressedBufferSize` validation against an application limit before
  decompression, reject unknown size, and handle invalid compressed input. Service
  maxima are not application budgets. Hash methods return binary digests; require
  deterministic input encoding and appropriate handling for text-only paths.
- For transport, distinguish packed bytes, application compression, and platform
  encoding/compression. Events compress certain types including buffers;
  UnreliableRemoteEvent drops payloads over its documented limit. Require actual
  path measurements; raw buffer length cannot prove on-wire size or acceptance.
- For DataStores, separate serialized request size, request/rate budgets, rounded
  throughput, and compressed backend storage. Use the current JSONEncode sizing
  procedure for request limits. Current guidance measures latest-version backend
  storage after platform compression and advises against pre-compression. Prefer
  uncompressed application data there; require actual persistence-path evidence
  for any claimed exception or savings. No backend storage claim from raw buffer,
  JSON length, or application compression ratio alone.

Engine sources (Creator Docs revision `031b2f91d3d47274c255f3ed5691c29f792c181d`):
[buffer](https://create.roblox.com/docs/reference/engine/libraries/buffer),
[EncodingService](https://create.roblox.com/docs/reference/engine/classes/EncodingService),
[event transport](https://create.roblox.com/docs/reference/engine/classes/UnreliableRemoteEvent),
[DataStore limits/compression](https://create.roblox.com/docs/cloud-services/data-stores/error-codes-and-limits).

## Other Luau costs

- Measure target workloads/builds; warm benchmarks and keep results observable.
  Use `os.clock` deltas. Heap totals include live and uncollected objects; one
  sample does not prove a leak. Own/reset memory categories in shared threads.
- Use preallocation, reuse, bounded pools/caches, table.concat, swap-remove,
  stable query params, batched packets, and direct callback arguments when
  measurements identify their cost. Require alias, order, lifetime, and precision
  preservation.
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
