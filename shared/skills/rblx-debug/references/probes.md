# Engine probes

Use after [engine evidence](../../rblx-writer/references/engine.md) leaves a
fix-relevant question unresolved. Retrieve existing output first. Follow `rblx-test`
and its [procedure](../../rblx-test/references/procedure.md).

## Setup and observations

- Use a disposable place. Stage disabled fixtures with `scaffold module --test`.
- Discover Studio/datamodel IDs; supply `studio_id` and `datamodel_type` on each
  MCP execution. Serialize writes per datamodel.
- Record build, MCP version/executable, source revisions, settings, RunContext,
  location, caller and serial/parallel phase; mark unavailable values unknown.
- Record operation, before/requested/after values, exact error, effect, observer
  result, restart need, restoration and human report. Assignment, effect,
  persistence and replication are separate results.
- Validate service results: successful `pcall` may return nil; a later nil-index
  error does not prove access denial.

## Mutation protocol

Preflight before mutation. Track started owned changes; restore only those changes,
including on errors. Failed preflight permits no restoration writes. Stop if
restoration fails.

For paired writer/observer tests, acknowledge write before sampling and sampling
completion before restoration. Bound deadlines and restore on errors. Separate
writer readback from observer reads; ACK does not prove property arrival.

## Conditional cases

Select only cases that can resolve the question; no full matrix or duplicate pass.

| Topic | Probe distinction |
|---|---|
| Signals | Record human editor setting separately from event timing; timing proves neither configured setting nor Default mapping. Calibration applies only to that event/run. Access-check diagnostic reads. |
| Workspace | Test documented Gravity writes with a falling part and separate-process observations. Configure streaming before fresh Play; keep read/write denials separate. Security metadata alone does not establish startup timing. |
| Modules | Query `api behavior modules`. Compare require identity within one caller, then server/client/MCP separately. While stopped, compare source-edited and destroyed/recreated owned instances; retain old references. Fresh Play is a separate case. MCP cache lifetime needs caller-specific evidence. |
