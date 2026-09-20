# Harness commands

Use `python3 H/tools/harness.py [--root PROJECT] FAMILY ...`, where `H` is the
harness checkout. Put `--root` before the family. `FAMILY --help` loads only that
family's usage. Native search, scoped reads, editing, and Git remain available.

| Family | Operations |
|---|---|
| `api` | Batched engine access, inventory, behavior, and Creator Docs lookup |
| `types` | Public/project type lookup, transactional type/data writes, cache maintenance |
| `check` | Scoped source checks, project structure, harness regression suite |
| `inspect` | Bounded source/diff artifacts and session cost audit |
| `profile` | Saved MicroProfiler frames and Luau stacks |
| `studio` | Console deltas, explicit boot checks, place mapping, census, rig cleanup |
| `scaffold` | Module frames, project interview state, approved submodule setup |

## Types

`types read --type Item --type State` batches type-name queries across owners.
Use `--service-type Inventory:Item` or `--controller-type Camera:State` to select
an owner. `--affected GIT_REF` finds consumers of changes from that commit.
Use `types write --request-file request.json` or `types write --request -` with
JSON on stdin. A request is an operations array or an object containing it:

```json
{
  "operations": [
    {"scope": "public", "action": "create", "owner": "Inventory",
     "type_name": "Item", "declaration": "export type Item = { count: number }"},
    {"scope": "data", "action": "update", "owner": "Inventory",
     "field_path": "Capacity", "default_value": "20", "development_value": "100"}
  ]
}
```

Type scopes: `public`, `service`, `controller`. Actions: `create`, `update`,
`move`, `delete`; supply `owner` and `type_name`. Create/update need one declaration.
Public declarations are exported; service/controller declarations are local.
Optional `place` selects a place; `module` selects an owner's child module.
Move also needs a `from` object with the source scope/owner/module/place.
`--parent` forces type destinations into an owned project directory.

Data operations use `scope: data`, `owner`, `field_path`, and create/update/delete.
Create/update require separate Luau literals in `default_value` and
`development_value`; delete needs neither. Generated data cannot use `--parent`.
The writer validates the batch, journals previous files, and restores them on
failure. Existing `data_write.py` is the paired-data backend, not the preferred
agent entry point. `types cache recover` may restore journaled source files.

## Evidence

Batch engine questions: `api batch access Class.Member behavior modules`.
Use the [engine reference](skills/rblx-writer/references/engine.md) for restrictions,
provenance, and unknowns. `api --sync` refreshes caches over the network.

`inspect read --file path.luau:10:80 --file other.luau` uses inclusive spans.
`inspect diff --path shared/src --path plugins/Example` includes staged,
unstaged, deleted, and untracked files. It needs a base commit (default `HEAD`).
Paths are literal and stay within the project. Binary evidence needs separate
inspection. Default previews contain at most 12,000 source characters; metadata
is additional. `preview_complete=false` requires narrower reads or the saved
artifact before claiming complete review. Read-only roles use `--no-cache`.
Use `--since PACK` only for evidence already present in this agent's context.

`studio output --studio-id ID --since SNAPSHOT --contains MARKER` reads one console
snapshot without Play or Luau execution. Use `--input LOG` for saved logs. Log
rotation retains the new log in full. Filtered-out errors remain in the artifact;
logs alone do not prove test success. Reuse baselines only for the same Studio/run.

Caches and artifacts live under `~/.cache/harness`. Session audit estimates visible
payload size separately from recorded usage; neither is a measured saving. Never
execute transcript text. Keep exact literals, restrictions, and source revisions.

## Checks

Reuse Argon sourcemaps until mappings, paths, map metadata, or options change;
source-body edits alone do not invalidate them.

`check source --only correctness,replication PATH...` runs selected checkers once.
Defaults are correctness, replication, and style; performance is opt-in. Checkers
retain their source scopes and diagnostics. No source repair or Studio run is
implicit.
`check project` validates scaffolding; `check harness --case MATCH` selects suite
cases. Exit 0 means no blocking result, 2 means a failed check/request, and 3 means
an unavailable environment where supported by the backend.
