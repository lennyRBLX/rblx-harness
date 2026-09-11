# Engine evidence

Use before code, commands or tests depend on engine access, timing, replication,
initialization or cleanup. CLI: `python3 <HARNESS_ROOT>/tools/harness.py api`.

- Query `access Class.Member`; `access Class` includes class restrictions. `inventory Workspace` includes inherited/restricted properties. Batch known questions: `batch access GuiObject.Size access GuiObject.AutomaticSize behavior gui`. Batch `$ref` values resolve through `shared`, then apply sibling fields; retain referenced evidence with results. Legacy lists, even `--all`, are discovery only.
- Read embedded `behavior` evidence; retrieve returned routes only for evidence not already included at the same source revisions. For behavior queries use an exact API or topic: `workspace`, `signals`, `replication`, `physics`, `parallel`, `modules`, `persistence`, `assets`, `gui`, `environment`.
- Canonical records contain scope, action, evidence, status, exceptions & recheck conditions. On a miss, search full Creator Docs & linked primary guides with the exact question. Retain unresolved questions & bounded next evidence actions; silence proves nothing.
- Preserve caller/datamodel, operation, restrictions, source revisions, exceptions & scoped unknowns through review. Keep engine limits, tool limits & project rules distinct.

## Operation checks

- Check read/write/call security, capabilities, all tags, inherited owner, class limits & serial/parallel phase separately. `Security=None` alone does not prove access. `ReadSafe` covers parallel reads, not writes, effect, persistence or replication.
- Record Script RunContext/location, caller & datamodel. ModuleScripts use caller privileges. Distinguish custom attributes (`GetAttribute`) from engine properties.
- Assignment/readback proves neither effect, persistence nor replication. Studio MCP, Command Bar, plugins & game scripts are distinct callers; untested MCP access stays unknown. Named restricted APIs must return restriction evidence. Decline known inaccessible operations; no retry loops or identity elevation.
- On version/metadata conflict, recheck the decisive source; never pick the more permissive value. Recheck affected records after engine/MCP changes. Researchers report stale/missing cache to the primary, who runs `api --sync`. Reuse current evidence until its recheck conditions apply.
- Keep human-maintained `house_overlay.txt` separate from sourced records. Propose exact undocumented entries with evidence before adoption.
- Author Script, LocalScript & ModuleScript objects/source in stopped Edit; never create/replace authored source objects during Play. Distinguish authoring, cloning prepared code, object creation & activation. For unresolved behavior, use [controlled probes](../../rblx-debug/references/probes.md).

## UI sizing

Before changing AutomaticSize, Size, CanvasSize or AutomaticCanvasSize, query
`behavior gui`. Separate minimum size, content bounds, canvas & viewport; retain
Scale/Offset, layout, constraints & padding. Formulas/timing marked untested
remain hypotheses.
