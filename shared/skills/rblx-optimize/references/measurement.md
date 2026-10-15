# Cost comparisons

- Record candidate location, consuming path, size/key distribution, hit/miss ratio,
  update rate, results/precision and lifetime. Return missing inputs and the
  smallest decisive comparison; do not rewrite representations on static findings.
- Assign build/load/runtime/save/transfer phase, frequency and reuse. Charge hashing,
  key creation, extraction and codecs only where performed. Never charge runtime
  decompression for data not decoded there.
- Compare lifetime cost (setup + frequency × operation cost) and amortization
  against separate CPU, latency, retained/peak memory and byte budgets. Extra CPU
  can be acceptable for material memory/transfer/storage savings within latency.
- Match production representations, access, seeds, distributions, updates, semantics,
  precision and environment. Separate representation and algorithm changes; measure
  affected construction, update, lookup, extraction and sorting. Include conversion
  in lifetime costs. Warm benchmarks and keep results observable.
- Require equivalent results or verified error bounds. Measure affected throughput,
  latency, allocations/GC, retained/peak memory and encoded/transmitted bytes.
  Include original strings, dictionaries, indexes, metadata, copies, decoded tables
  and scratch. Buffer length is not heap use; label estimates.
- OPT21 finds direct scans/sorts/keys/codecs; inspect aliases, helper effects,
  cardinality, frequency and phase. DATA38 covers literal widths/ranges only.

For paired HTB1 timings, run `profile results LOG --side SIDE --script NAME --run RUN
--compare BASE CANDIDATE`. Methods name alternatives; workloads name phase/operation.
The tool checks group/count/threshold alignment, reports candidate-minus-base and
conditional setup/script/teardown crossover. Apply only with production reuse and
comparable batching. Timings alone prove neither memory/byte savings, equivalence,
environment equality nor platform storage reduction. Use `rblx-test` for execution.
