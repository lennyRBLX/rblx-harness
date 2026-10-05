# Harness commands

Use `python3 H/tools/harness.py [--root PROJECT] FAMILY ...`; `H` is the harness checkout. Put `--root` before the family. `FAMILY --help` loads that family's usage. Native search, scoped reads, edits, and Git remain available.

| Family | Operations |
|---|---|
| `api` | Batched engine access, inventory, behavior, Creator Docs lookup |
| `types` | Public/project type lookup, transactional type/data writes, cache maintenance |
| `check` | Scoped source, project structure, harness regression checks |
| `inspect` | Bounded source/diff artifacts, session cost audit |
| `profile` | Saved MicroProfiler frames, Luau stacks |
| `studio` | Console deltas, explicit boot checks, place mapping, census, rig cleanup |
| `scaffold` | Module frames, project interview state, approved submodule setup |

## Types

`types read --type Item --type State` batches owner type queries. Select an owner with `--service-type Inventory:Item` or `--controller-type Camera:State`. `--affected GIT_REF` finds consumers of changes from that commit.

Use `types write --request-file request.json` or `types write --request -` with JSON on stdin. Pass an operations array or an object containing one:

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

Type scopes: `public`, `service`, `controller`. Actions: `create`, `update`, `move`, `delete`; pass `owner` and `type_name`. Create/update need one declaration. Public declarations are exported; service/controller declarations are local. Optional `place` selects a place; `module` selects an owner's child module. Move needs `from` with source scope/owner/module/place. `--parent` forces type destinations into an owned project directory.

Data operations use `scope: data`, `owner`, `field_path`, and create/update/delete. Create/update need separate Luau literals in `default_value` and `development_value`; delete needs neither. Generated data cannot use `--parent`. The writer validates the batch, journals prior files, and restores them on failure. `data_write.py` is the paired-data backend, not the preferred agent entry point. `types cache recover` may restore journaled files.

## Evidence

Batch engine questions with `api batch access Class.Member behavior modules`. For restrictions, provenance, and unknowns, read the [engine reference](skills/rblx-writer/references/engine.md). `api --sync` refreshes caches over the network.

`inspect read --file path.luau:10:80 --file other.luau` uses inclusive spans. `inspect diff --path shared/src --path plugins/Example` includes staged, unstaged, deleted, and untracked files; it needs a base commit (default `HEAD`). Paths are literal and project-contained. Inspect binaries separately. Default previews contain at most 12,000 source characters plus metadata; `preview_complete=false` requires narrower reads or the saved artifact before claiming full review. Read-only roles use `--no-cache`. Use `--since PACK` only for evidence already in this agent's context.

`studio output --studio-id ID --side CLIENT --script NAME --run RUN --wait SECONDS` collects and decodes complete test buffers without Play or Luau execution. `--since SNAPSHOT` retains transport across rotation. `--contains MARKER` only filters display. Use `--input LOG` for saved logs. Rotation retains the new log in full. Errors remain visible outside marker filters and in the artifact; logs alone do not prove test success. Reuse baselines only for the same Studio/run.

Caches and artifacts live under `~/.cache/harness`. Session audit estimates visible payload separately from recorded usage; neither measures savings. Never execute transcript text. Keep exact literals, restrictions, and source revisions.

## Checks

Reuse Argon sourcemaps until mappings, paths, map metadata, or options change; source-body edits alone do not invalidate them.

`check source --only correctness,replication PATH...` runs selected checkers once. Defaults: correctness, replication, style; performance is opt-in. Checkers keep their source scopes and diagnostics. No source repair or Studio run is implicit.

Correctness includes OPT15 explicit parallel-scope pairing/serial require, OPT20 profile pairing, and DATA38 literal codec advisories. Flow checks cover direct calls per function; review aliases, helper effects, exceptions, and cancellation. Performance adds advisory labels/possible parallel writes. Replication WRIT8 covers reliable and unreliable remotes. Pinned Lute/LSP supports `const`, which the style formatter preserves; no syntax suppression is needed.

`check project` validates scaffolding; `check harness --case MATCH` selects suite cases. Exit 0 means no blocking result; 2 means a failed check/request; 3 means an unavailable environment where the backend supports it.

## Test results and captures

Read the [shared procedure](skills/rblx-test/references/procedure.md) and
[buffer protocol](skills/rblx-test/references/buffer.md) when authoring tests or
collection. `studio decode LOG --side SIDE --script NAME --run RUN` and
`profile results` share the collector. `--historical` reads old TEST JSON only.
New authored output and decoded summaries are not JSON.

Before a human capture: `profile capture baseline --baseline RUN/candidates.json`
records candidate files. After the human finishes saving: `profile capture collect
--baseline RUN/candidates.json --human-complete --place ID --marker MARKER
--coverage sample --min-frames N --spike-ms N --output RUN/captures` discovers,
checks stable writes, parses and archives a unique matching capture. Repeat
`--root DIR` to select dump directories. Full coverage additionally requires
`--coverage full --expected-frames N` and indexed workload markers. `--select FILE`
resolves an ambiguous match explicitly. A capture failure leaves the completed
workload awaiting review; do not report it as unexecuted.

`profile frames FILE.html --place ID --marker MARKER` uses the bounded saved-HTML
adapter. Unsupported viewer hashes require native exports or an explicit adapter
update with evidence. Historical CSV/counters/summary trios remain readable.
Statistics use one selected event window, never rolling aggregate fields. Profiler
files do not enter the buffer decoder. Required captures, saving and retrieval
finish before Studio Stop. No spatial benchmark is needed for harness prose or
configuration checks.
