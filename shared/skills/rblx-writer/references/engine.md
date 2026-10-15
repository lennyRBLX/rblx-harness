# Engine evidence

Load before relying on engine access, timing, replication, startup or cleanup.

1. Query exact members/topics: `api access Class.Member`, `api behavior TOPIC`.
   Use class access for restrictions, `api inventory CLASS` for inherited members,
   or `api batch access GuiObject.Size behavior gui` for independent questions.
   Legacy lists, including `--all`, are discovery only.
2. Read embedded behavior records first. Follow returned routes only for missing
   evidence at those revisions. On a miss, search Creator Docs and linked primary
   guides for the exact question; retain unknowns and a bounded next action.
3. Preserve caller/datamodel, operation, restrictions, exceptions, source revision
   and recheck conditions. Distinguish engine limits, tool limits and project rules.

## Access and provenance

- Check read/write/call security, capabilities, tags, inherited owner, class limits
  and serial/parallel phase separately. `Security=None` is insufficient;
  `ReadSafe` establishes only parallel reads.
- Record RunContext/location; ModuleScripts inherit caller privileges. Attributes
  use `GetAttribute`, not property access. MCP, Command Bar, plugins and game scripts
  are distinct callers; untested MCP access stays unknown.
- Assignment/readback proves neither effect, persistence nor replication. Decline
  known inaccessible operations; no retry loops or identity elevation.
- Resolve metadata/version conflicts at the decisive source, not by permissiveness.
  Researchers report stale caches to the primary for `api --sync`.
- Keep human `house_overlay.txt` entries separate from sourced records; propose exact
  additions with evidence. Batch `$ref` resolves through `shared`, then sibling
  fields; retain referenced evidence.

Author Script/LocalScript/ModuleScript source in stopped Edit. Distinguish authoring,
cloning prepared code, object creation and activation. For unresolved behavior, use
[probes.md](../../rblx-debug/references/probes.md).
