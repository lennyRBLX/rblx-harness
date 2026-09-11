# Controlled engine probes

Use only for development-relevant engine questions left unresolved by
[engine evidence](../../rblx-writer/references/engine.md).
Apply TEST2–TEST3: name the unresolved question and result that would change
the fix. Retrieve existing output first. Do not rerun an established failure
for confirmation or repair an optional probe unless its answer is still needed.

## Setup & records

- Use a disposable place and the selected environment/execution authority (TEST1). Stage disabled fixtures with `tools/create_boilerplate/create_boilerplate.py --test`; author source in stopped Edit. Assign exact paths & cleanup ownership; preserve other edits.
- Discover studios/datamodels; supply `studio_id` & `datamodel_type` on every MCP execution. Serialize writes per datamodel.
- Record Studio build, MCP version/executable identity, source revisions, place settings, RunContext/location, caller & serial/parallel phase. Unavailable values stay unknown.
- Each case: operation, before, requested value, after, exact error, effect, other-process observation, restart need, restoration & human report. Separate assignment, effect, persistence & replication; unrun cases never pass.

## Execution & cleanup

- Validate preconditions before mutation. Failed preflight permits no cleanup writes. Track started owned mutations; restore only affected values, including on errors. Stop if restoration fails. After stopping, remove owned temporary fixtures; retain useful regression tests.
- Distinguish fixture defects from engine limits. Validate service results before calls: successful `pcall` may return nil; a later nil-index error does not prove access denial.
- Bound output; on truncation, retain full records in owned non-code runtime values & retrieve before Play teardown.
- Paired writer/observer: acknowledge write before sampling & sampling completion before restoration; use bounded deadlines & restore on errors. Separate writer readback from observer reads; protocol ACK does not prove property arrival.

## Conditional cases

Select only operations needed by the unresolved question. These cases do not
require a complete matrix or a second identical successful run.

- **Signals:** Access-check diagnostic reads. Workspace.SignalBehavior is NotScriptable; do not assume XML makes it readable/configurable. Record human-observed editor setting separately from exact event dispatch. Callback timing proves neither configured setting nor Default mapping; calibration applies only to that event/run.
- **Workspace:** Read member behavior records. Test documented runtime Gravity writes with a controlled falling part & separate process observations. Configure documented streaming settings before fresh Play; never toggle StreamingEnabled during production Play. PluginSecurity alone does not imply startup-only behavior. Keep read/write denials separate.
- **Modules:** Query `behavior modules`. Compare repeated require identity within one caller, then server/client/MCP callers separately. While stopped, compare the same instance after a source edit against a destroyed/recreated owned instance; record old references separately. Fresh Play is a separate case, not a replacement test. MCP cache lifetime stays unknown without evidence for that context.

Recheck affected procedures when operational sources or versions change.
