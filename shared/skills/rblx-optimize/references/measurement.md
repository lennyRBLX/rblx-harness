# Performance evidence

## Choose the evidence

- Use Script Profiler to find expensive Luau functions and distinguish self time from time in callees. Use MicroProfiler for frame spikes and cost in scheduling, rendering, physics or networking. Label a suspect code region with a named [profile scope](../../rblx-writer/references/runtime.md) when engine scopes alone cannot identify it. Use the [capture procedure](../../rblx-test/references/captures.md) for frame-time claims.
- For a quick probe of a known script block, use the [elapsed-time clock](../../rblx-writer/references/luau.md). Use the shared [workload timer](../../rblx-test/references/procedure.md#runner-and-measurements) for paired timings. Use `Stats` frame counters for triage and keep their scope separate from script durations. Use client Render Stats to track draw calls and triangles when tuning rendering. Read supplied artifacts with the [matching harness tool](../../../../TOOLS.md#test-results-and-captures).

## Cost comparisons

- Record location, consumer, size and key distribution, hit rate, update rate, precision and lifetime. Name missing inputs and the smallest decisive comparison before changing a representation flagged by a source audit.
- Assign build/load/runtime/save/transfer phase, frequency and reuse. Charge hashing, key creation, extraction and codecs only where performed. Never charge runtime decompression for data not decoded there.
- Compare lifetime cost (setup + frequency × operation cost) and amortization against separate CPU, latency, retained/peak memory and byte budgets. Extra CPU can be acceptable for material memory/transfer/storage savings within latency.
- For frame hot spots, estimate operations per frame from update cadence and fanout, including bursts. Label extrapolated costs and use them to choose what to measure against the shared `1,000 / target FPS` millisecond frame budget.
- Match production representations, access, seeds, distributions, updates, semantics, precision and environment. Change one mechanism per pair. Measure affected construction, update, lookup, extraction and sorting. Include conversion in lifetime costs.
- Require equivalent results or verified error bounds. Measure affected throughput, latency, allocations/GC, retained/peak memory and encoded/transmitted bytes. Include original strings, dictionaries, indexes, metadata, copies, decoded tables and scratch. Report buffer length as bytes of data. Measure heap use separately.
- For OPT21 candidates, check aliases, helper effects, cardinality, frequency and phase. See [check coverage](../../../../TOOLS.md#checks).

## Benchmarks

- Use target-workload measurements to resolve uncertain tradeoffs or quantify a gain. Treat timings from another device, scene, or execution mode as evidence for choosing what to test.
- Warm each case and keep an observable result from the timed work. Match the scene, app focus, frame cap and compiler settings other than the setting under test. Record device, frame phase, optimization level, observed frame rate and workload alongside the runner's standard run metadata. Use the [deployment execution tier](luau-costs.md) for target claims. Keep Edit-mode results scoped to that environment and measure rendered work on a representative playtest client.
- For setter-only tests, precompute poses and vary values across frames to exercise real changes. Also measure the full workload, including downstream rendering, physics or replication costs.
- Repeat matched trials. For frame comparisons, interleave no-op, baseline and candidate windows with matched starting state, and vary case order when it could bias the result. Treat deltas within baseline variation as inconclusive. Recheck decision-critical results when runtime, hardware, scene or workload changes.

## Collect and report

- Execute through [rblx-test](../../rblx-test/SKILL.md). For paired HTB1 timings, name alternatives as methods and phases or operations as workloads. Use [`profile results --compare`](../../../../TOOLS.md#test-results-and-captures) and interpret crossover with production reuse and comparable batch sizes.
- Report what changed and its behavior tradeoffs. Give before and after measurements with units and sample variation when available. Label estimates and unmeasured costs explicitly. Provide evidence for each claimed improvement.
