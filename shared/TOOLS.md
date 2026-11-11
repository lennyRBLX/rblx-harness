# Harness commands

Install the Rust binary with `cargo install --path H --locked`, then use `harness [--root PROJECT] FAMILY ...`. Put `--root` before the family. Family and subcommand help is available with `--help`. Native search, scoped reads, edits, and Git remain available.

Both `setup --harness` and `setup --project` install the pinned Lute 1.0.0,
Argon 2.0.29, and Luau LSP 1.70.1 binaries into the harness checkout's
`tools/bin`. Archives come from their upstream GitHub releases and are
SHA-256-verified before extraction. Downloads need network access; supported
automatic targets are macOS arm64, Linux arm64/x86_64, and Windows x86_64.

| Family | Operations |
|---|---|
| `api` | Batched engine access, inventory, behavior, Creator Docs lookup |
| `types` | Public/project type lookup, transactional type/data writes, cache maintenance |
| `data-write` | Direct validated paired PlayerData writes; `types write` is preferred |
| `check` | Scoped source, project structure, harness regression checks |
| `inspect` | Bounded source/diff artifacts, session cost audit |
| `coord` | Atomic write scopes, owner checks, lifecycle cleanup |
| `profile` | Saved MicroProfiler frames, Luau stacks |
| `studio` | Console deltas, runtime reload/source commands, explicit boot checks, place mapping, census, rig cleanup |
| `argon` | Automatic Argon serving, status, shutdown, verified project → PlaceId mapping |
| `scaffold` | Module frames, project interview state, approved submodule setup |
| `setup` | Host integration, permissions, hook migration |

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

Data operations use `scope: data`, `owner`, `field_path`, and create/update/delete. Create/update need separate Luau literals in `default_value` and `development_value`; delete needs neither. Generated data cannot use `--parent`. The writer validates the batch, journals prior files, and restores them on failure. `harness data-write` retains the direct paired-data interface; use `types write` for journaled batch transactions and recovery.

## Evidence

Batch engine questions with `api batch access Class.Member behavior modules`. For restrictions, provenance, and unknowns, read the [engine reference](skills/rblx-writer/references/engine.md). `api --sync` refreshes caches over the network.

`inspect read --file path.luau:10:80 --file other.luau` uses inclusive spans. `inspect diff --path shared/src --path plugins/Example` includes staged, unstaged, deleted, and untracked files; it needs a base commit (default `HEAD`). Paths are literal and project-contained. Inspect binaries separately. Default previews contain at most 12,000 source characters plus metadata; `preview_complete=false` requires narrower reads or the saved artifact before claiming full review. Read-only roles use `--no-cache`. Use `--since PACK` only for evidence already in this agent's context.

`inspect diff --path PATH --overlap` compares local worktrees, including reverted staged edits. States: `clear`, shared-file `overlap`, textual `conflict`, missing-coverage `unknown`. Conflict/unknown exits 2. Scans stop at 20 seconds or 20 peers; skipped coverage stays unknown. Indexes stay intact; isolated objects are removed on exit or recovered after process death. No network or claims occur. Clean merges do not prove compatible behavior.

`coord begin --owner ID --path PATH [--parent ID]` reserves scopes per worktree and returns a token. Repeat `--path` for more scopes. Identical requests reuse tokens; changed scopes replace them. `coord check --owner ID --lease N [--path PATH]` validates scope and renews; `coord end --owner ID --lease N` releases. Tokenless `check [--path PATH]` lists owners; `--overlap` adds worktree checks. Root IDs default to `CODEX_THREAD_ID` or `CLAUDE_CODE_SESSION_ID`; subagents receive explicit owner/parent IDs. Git's common directory stores leases. Expiry stays unknown. `--pid PID` permits cleanup after a known owner process dies; CLI PIDs are unsuitable. Setup preserves user hooks and adds `SubagentStop`/`SessionEnd` cleanup; native hook trust still applies. Leases coordinate cooperating writers, without restricting other writes.

`studio output --studio-id ID --side CLIENT --script NAME --run RUN --wait SECONDS` collects and decodes complete test buffers without Play or Luau execution. `--since SNAPSHOT` retains transport across rotation. `--contains MARKER` only filters display. Use `--input LOG` for saved logs. Rotation retains the new log in full. Errors remain visible outside marker filters and in the artifact; logs alone do not prove test success. Reuse baselines only for the same Studio/run.

Caches and artifacts live under `~/.cache/harness`. Session audit estimates visible payload separately from recorded usage; neither measures savings. Never execute transcript text. Keep exact literals, restrictions, and source revisions.

## Active-session source commands

For supported iteration in an authorized running playtest, read
[hot reload](skills/rblx-test/references/hot-reload.md) before restarting.
`studio reload bootstrap|patch|undo|status|poll --side Server|Client --session ID
--output FILE` generates Luau for the existing Studio connector; it does not
connect or execute. Target operations take `--path-file JSON` or `--path JSON`;
patch adds `--source FILE --expected FILE --revision N --audited`, undo adds
`--revision N`.

`studio source snapshot --side Edit|Server|Client --path-file JSON --output FILE`
generates exact stored/editor source readback. `studio source persist --side Edit
--path-file JSON --source FILE --expected FILE --expected-editor FILE --output FILE`
generates compare-before-write editor/stored synchronization for Edit.

## Argon

`argon ensure [--project NAME --port PORT]` registers the root and starts one
user-level watcher. Setup also starts it. `argon status` reports MCP, PlaceId,
server, connection, and port state; `argon stop` closes its servers. On a
developer-confirmed mapping, use `argon map NAME PLACE_ID`; it requires Studio
MCP and checks the ID against the open universe before updating the managed
`AGENTS.md` places block. The watcher retries without restarting the agent.

Only Edit-mode places with one matching project map are served. MCP loss, place
changes, and ambiguous/unmapped places stop or block syncing. Argon owns both
sync directions and reconnects through its existing Studio plugin; configure
that plugin on the port reported by `argon status`. The harness never installs
the plugin. Host is `localhost`; ports start at 8000 and remain unique per
canonical project path in `~/.argon/harness/ports.json`, outside temporary caches.
Only the CLI is updated on supervisor startup and every 24 hours with `argon update cli`; default
verbosity is normal and notifications are off. The existing Argon global config
file remains untouched.

## Checks

Reuse Argon sourcemaps until mappings, paths, map metadata, or options change; source-body edits alone do not invalidate them.

`check source --only correctness,replication PATH...` runs selected checkers once. Defaults: correctness, replication, style; performance is opt-in. Checkers keep their source scopes and diagnostics. No source repair or Studio run is implicit.

Correctness includes OPT15 explicit parallel-scope pairing/serial require, OPT20 profile pairing, and DATA38 literal codec width/range advisories. Flow checks cover direct calls per function; review aliases, helper effects, exceptions, and cancellation. Performance adds advisory labels/possible parallel writes and OPT21 representation candidates. For scans, sorts, computed keys, or codec calls, use the returned location, required comparison, and evidence limits; no finding establishes a material cost. Replication WRIT8 covers reliable and unreliable remotes. Pinned Lute/LSP supports `const`, which the style formatter preserves; no syntax suppression is needed.

Style WRIT20 compares exact function signatures/bodies across same-side source and
server/package or client/package source in `shared/src` and `places/*/src`; reports selected copies
with owner locations. Trivia and function names are ignored; renamed bindings,
partial copies, state equivalence and API ownership need review.

`check project` validates scaffolding; `check harness --case MATCH` selects suite cases. Exit 0 means no blocking result; 2 means a failed check/request; 3 means an unavailable environment where the backend supports it.

## Test results and captures

Read the [shared procedure](skills/rblx-test/references/procedure.md) and
[buffer protocol](skills/rblx-test/references/buffer.md) when authoring tests or
collection. `studio decode LOG --side SIDE --script NAME --run RUN` and
`profile results` share the collector. `--historical` reads old TEST JSON only.
New authored output and decoded summaries are not JSON.
For paired method timing groups, add `--compare BASE CANDIDATE` to `profile results`.
It validates group/count/threshold alignment and reports timing deltas and a
conditional setup/script/teardown timing estimate. Require equivalent results, comparable
inputs, production reuse, and separate memory/byte evidence before selection.

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
