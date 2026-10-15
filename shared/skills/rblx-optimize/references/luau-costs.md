# Cost candidates

Load only the affected decision:

| Decision | Reference |
|---|---|
| Workload budgets, benchmarks, paired results | [measurement.md](measurement.md) |
| Keys, scans, indexes, sorting, spatial hashes | [keys.md](keys.md) |
| Packing, quantization, deltas, compression | [formats.md](formats.md) |
| Buffer copies, EncodingService, wire/storage sizes | [engine-costs.md](engine-costs.md) |

## Luau-specific limits

- Heap totals include live/uncollected objects; one sample cannot prove a leak.
  Own/reset memory categories in shared threads.
- Compare preallocation, reuse, bounded pools, concat, swap-remove, stable query
  params, batching or direct callback arguments only for identified costs.
  Preserve aliases, order, lifetime and precision.
- Numeric `for` bounds evaluate once; hoisting `#t` saves no repeated evaluation.
  Imports/fastcalls often remove global lookup cost. Closure reuse depends on
  captures/compiler; prove callback allocation/identity claims on target runtime.
- Vector3.new does not establish heap allocation; vectors are values. Prefer typed
  engine boundaries over `any` casts.
- Native compilation targets measured computation. Verify deployment support and
  current codegen limits as needed; Studio speed does not prove client speed.
- Preserve query geometry/filters; bound results only if truncation is acceptable.
  Bounds queries cannot silently replace exact queries.

Use [runtime.md](../../rblx-writer/references/runtime.md) for profile/parallel scope
checks and their limits.
