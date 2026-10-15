# MicroProfiler collection

Load for captures or frame-time claims. Use the [test procedure](procedure.md)
for runner readiness/lifecycle. Profiler files never enter the buffer decoder.

## Before execution

Record candidates with `profile capture baseline --baseline RUN/candidates.json`.
Present required settings/focus and profiler enable/pause/save actions together.
Choose coverage and spike threshold before execution:

- Sample: declared minimum contiguous frames and actual event coverage.
- Full window: every indexed measurement scope, 1 through expected count.

## Capture handoff

At capture readiness, emit exactly
`SIDE|TEST_SCRIPT_NAME|CTRL|PAUSE NOW FOR MICROPROFILER`, outside timing and before
encoding or fixture destruction. `continueCapture` may run bounded representative
samples while the human pauses; exclude them from completed totals.
`context:scope(method, workload, index)` labels run, test, phase and sample index.

`CaptureDone` means the human finished saving, not acceptance. Keep Play available
through saving/retrieval; timeout does not authorize Stop while either is pending.

## Retrieve and accept

After human completion, use `profile capture collect --baseline RUN/candidates.json
--human-complete --place ID --marker MARKER --coverage sample --min-frames N
--spike-ms N --output RUN/captures`. For full coverage use `--coverage full
--expected-frames N`; repeat `--root DIR` for dump directories.

Match identity, place, markers and coverage; newest-first discovery does not select
an ambiguous match. Resolve with `--select FILE`. The collector checks stable writes
and retries parsing within bounds. Retain unsupported viewers for native export or
an evidenced adapter update; the saved-HTML adapter runs in a separate process.

Compute statistics from one selected event window; do not mix rolling aggregates,
exports or captures from different windows. Partial captures support only observed
samples, not full-run maxima/averages. Distinguish script duration, scheduling
interval, profiler scope and engine frame interval. Frame-time claims require
matching profiler evidence. Completed workload with capture pending is not unrun.
