# Test procedure

## Decision and evidence

Give each test one question, one stable ID, the decision its result can change,
and a stopping condition. Start with the broadest useful measurement. Narrow
only when its result requires investigation. Remove prerequisites that cannot
change that decision. Reuse valid findings and documented engine facts. Keep
correctness checks for authored algorithms separate from engine behavior probes.
Measurement repeats, bug reproductions and checks affected by source or workload
changes are permitted. A new question needs a new ID. Freeze source during
comparisons. Repairs retain prior revisions and invalidate only affected evidence.

## Preparation and readiness

Keep test source under `tests/<Place>/<side>/`, mapped by Argon to
ServerScriptService.Tests or StarterPlayerScripts.Tests. Author only the needed
side. Use shared `TestSupport` from `shared/test_support` for lifecycle and codec;
scaffolding adds an explicit Argon TestSupport mapping beside the test. A test owns fixtures and its question.
Prepare source and invocation in stopped Edit mode. Use Studio MCP Play/Stop and
`studio output`; do not use Computer Use or screenshots for this procedure.

Before execution, save run identity and source hashes, engine build, caller,
Workspace properties, Studio settings, focus condition, seed and options once in
the existing run artifacts. Unknown values remain unknown. For a human capture,
record candidate files with `profile capture baseline` before execution. Present
required Workspace properties, Studio settings, focus conditions, and
MicroProfiler enable/pause/save actions together. Request only outstanding human
actions. No dependent setup, warm-up or measurement starts until readiness is
confirmed. Set the driver's `RunId` and `Ready` attributes before Play when ready.

`Runner.run(driver, spec)` states: readiness → warm-up → measurement →
capture-waiting (when required) → collection → completion. `State`,
`WorkloadState`, `ProfilerState` and `CollectionState` are independent attributes.
`Cancel` terminates work; deadlines bound readiness, execution, capture continuation
and collection. Callbacks must yield within the declared bound; Luau cannot
preempt a non-yielding callback. Own instances, connections, tasks and restoration
callbacks through the context. Release in reverse order, once, on all exits.
Restore a property only while it still has this run's assigned value. Never
restore after failed preflight or delete another owner's resources.

Automate fixtures, warm-up, workload, measurements and result collection. Warm-up counters are reset before measurement. Define
spike thresholds before measuring. `context:metric` declares one method/workload
and timing kind. `context:measure` times the callback; `observe` adds a measured
duration. Logging, encoding, transport, setup and teardown stay outside workload
timings. Report setup/teardown separately when relevant. Averages include spikes;
combine totals and counts, never unweighted means. Do not print normal frames.
Spikes retain observation indices and durations, at most 256 per metric, with
an overflow count. For scheduling observations those indices are scheduling
samples, not engine frame indices.

## Independent collection

Serialized results: test → encoded buffer → `studio output` → shared buffer
decoder → summary. Use `studio output --studio-id ID --side CLIENT|SERVER
--script NAME --run RUN --wait SECONDS`. Save the artifact; later reads use
`--since ARTIFACT`. It retains transport across console rotation, deduplicates
chunk delivery and decodes before display limits. Missing output cannot pass.
Set `Collected` after complete decoded results and required evidence retrieval.
Testing, debugging and optimization all use this decoder; `studio decode` and
`profile results` read saved output. This path needs no human or MicroProfiler.

MicroProfiler: human capture → Studio dump → automatic discovery → profiler
parser. At the capture point the runner emits exactly
`SIDE|TEST_SCRIPT_NAME|CTRL|PAUSE NOW FOR MICROPROFILER`, before encoding or fixture
destruction and outside measured regions. `continueCapture` may run bounded
representative samples while the human pauses; it must not append them to the
completed measurement totals. Use `context:scope(method, workload, index)` to
include run, test, phase and sample index in profiler labels. `CaptureDone` means
the human finished saving, not profiler acceptance. Keep Play available through
saving and retrieval; timeout is not permission to stop Play while either remains.

After human completion run `profile capture collect --human-complete` with the
baseline, place, required markers, coverage, predeclared spike threshold and
archive path. Candidate order is newest first, but identity, place, markers and
coverage decide acceptance. Stable file observations and bounded parse retries
handle incomplete writes. Multiple matches require explicit selection, never
implicit newest selection. Unsupported viewers are retained for native export.
The bounded saved-HTML adapter supports explicitly pinned viewer/tool formats.
It exports in a separate process; MicroProfiler files never enter the test codec.

Choose coverage before execution: a representative sample requires the declared
minimum contiguous frames; a complete window requires every indexed measurement
scope from 1 through the expected count. Check actual event coverage in either
case. Compute statistics only from that selected event window. Never combine
rolling aggregates, exports or captures with different windows. A partial capture
can support its observed sample, never full-run maxima or averages. Distinguish
script duration, scheduling interval, profiler scope and engine frame interval.
This project requires matching profiler evidence for frame-time claims. Workload
complete / profiler awaiting review is not unexecuted.

## Completion

Accept only complete, valid results. Archive accepted source, raw transport and
captures before deleting temporary files or redundant originals. Keep useful test
source. Remove owned temporary drivers and resources; preserve unrelated files,
active Studio logs and the sole copy of unresolved evidence. Report passed,
failed, reused, unrun, and outstanding human actions accurately.
