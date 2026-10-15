# Test execution

Use `rblx-test` for selection/output rules and CORE for evidence reuse. Freeze
source during comparisons; preserve prior revisions after repairs.

## Prepare

- Keep drivers under `tests/<Place>/<side>/`, Argon-mapped to
  ServerScriptService.Tests or StarterPlayerScripts.Tests. Mount
  `shared/test_support` beside each authored side; the test owns fixtures.
- Prepare source/invocation in stopped Edit. Use Studio MCP Play/Stop and
  `studio output`; no Computer Use/screenshots for this procedure.
- Save run ID, source hashes, build, caller, Workspace/Studio settings, focus,
  seed and options once in run artifacts; mark unknowns.
- Present outstanding human settings/actions together. Wait for confirmed readiness
  before dependent setup/warm-up/measurement. Set driver `RunId` and `Ready` before
  Play when ready. For profiler work, first read [captures.md](captures.md).

## Runner and measurements

`Runner.run(driver, spec)`: readiness → warm-up → measurement → optional
capture-waiting → collection → completion. `State`, `WorkloadState`, `ProfilerState`
and `CollectionState` are independent attributes. `Cancel` ends work; bound
readiness, execution, capture continuation and collection deadlines. Callbacks must
yield within their bound; Luau cannot preempt non-yielding callbacks.

Own instances, connections, tasks and restoration callbacks through context;
release once in reverse order on all exits. Restore properties only while they
retain this run's assigned value; failed preflight permits no restoration writes.

Automate fixtures, workload, warm-up and collection. Reset warm-up counters.
`context:metric` declares method/workload/kind; `context:measure` times a callback;
`observe` adds duration. Exclude logging, encoding, transport, setup and teardown
from workload timing; report affected setup/teardown separately. Use non-yielding
regions for CPU claims.

Predeclare positive spike thresholds. Averages include spikes: combine totals/counts,
not unweighted means. Retain observation indices/durations for at most 256 spikes
per metric plus overflow count; scheduling samples are not engine frame indices.
Do not print normal frames.

## Collect and finish

Results: test → encoded buffer → `studio output` → shared decoder → summary.
Use `studio output --studio-id ID --side CLIENT|SERVER --script NAME --run RUN
--wait SECONDS`. Save its artifact; `--since ARTIFACT` retains transport across
rotation and deduplicates delivery. `studio decode`/`profile results` read saved
output. Serialized results require neither human capture nor MicroProfiler.

Set `Collected` only after complete decoded results and required evidence retrieval.
Archive accepted source, raw transport and captures before deleting temporary files
or redundant originals. Keep useful tests, active Studio logs and the sole copy of
unresolved evidence; remove owned temporary drivers/resources. Report check states
and outstanding human actions accurately.
