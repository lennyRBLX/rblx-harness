# Tools

See the [shared tool rules](shared/CORE.md#tools).

## Conventions

`*` · R · command notation.

| Token | Meaning |
|---|---|
| `R` / `S` / `N` | Local files / Studio / network |
| `H` | Harness checkout root |
| `…` | Repeat the command prefix |
| `<value>` / `[value]` | Required / optional |

## cargo-clean

`tools/cargo-clean.sh` · R / N · Run Cargo and clean build artifacts.

| Cmd | Effect |
|---|---|
| `H/tools/cargo-clean.sh install --path . --locked` | Install `harness` |
| `… run -- <harness args>` | Run the CLI from source |
| `… <cargo args>` | Run Cargo from the harness root |

- Cleans on success and failure. Honors `CARGO_TARGET_DIR` and `--target-dir`.

## harness

`src/` · R / S / N · Set up, inspect, and check Roblox projects.

| Cmd | Effect |
|---|---|
| `harness --help` | List command families |
| `harness scaffold --help` | Find module and project scaffolding commands |
| `harness [--root <project>] <family> [<action>] --help` | Show family or subcommand options |

- Put `--root` before the command family.

## api_dump

`tools/api_dump/` · R / N · Supply engine behavior and access data to `harness api`.

| Cmd | Effect |
|---|---|
| `harness api batch access <Class.Member> behavior <topic>` | Look up access and behavior |
| `harness api inventory <class>` | List inherited properties and access restrictions |
| `harness api --sync` | Refresh API and documentation caches over the network |
| `harness api --emit-globals` | Write the API globals cache for style checks |

- Follow the [engine evidence rules](shared/skills/rblx-writer/references/engine.md).

## Types

`src/types.rs` · R · Look up types and transact type and data edits.

| Cmd | Effect |
|---|---|
| `harness types read --type <name> [--type <name>]` | Batch owner type queries |
| `harness types write --request-file <file>` | Validate and apply a JSON request file |
| `harness types write --request -` | Read the request from stdin |

- Select an owner with `--service-type Inventory:Item` or `--controller-type Camera:State`. Use `--affected <git_ref>` to find consumers of changes from that commit.
- Pass an operations array or an object containing one.

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

- Type scopes are `public`, `service`, and `controller`. Each operation needs `owner` and `type_name`. Create and update need one declaration. Export public declarations. Keep service and controller declarations local.
- Use `place` and `module` to select a place and child module. Move needs `from` with source scope, owner, module, and place. Use `--parent` for an owned project destination.
- Set `scope: data`, `owner`, and `field_path` for data. Create and update need Luau literals in `default_value` and `development_value`. Omit them for delete. Data uses its standard destination. The writer validates the batch, journals files, and restores them on failure.

## data_write

`tools/data_write/data_write_core.luau` · R · Edit paired PlayerData files.

| Cmd | Effect |
|---|---|
| `harness data-write --help` | Show the direct paired-data interface |

- Use [Types](#types) for journaled batch writes and recovery.

## data_shape_diff

`tools/data_shape_diff/data_shape_diff.luau` · R · Check changes to existing PlayerData shapes.

| Cmd | Effect |
|---|---|
| `H/tools/bin/lute run H/tools/data_shape_diff/data_shape_diff.luau <baseline> <proposed> [--migrations <dir>]` | Check a proposed default against its baseline |

- The [writer](#types) runs this check when a prior default exists.

## deny_scan

`tools/deny_scan/` · R · Check Luau correctness.

| Cmd | Effect |
|---|---|
| `harness check source --only correctness <path>` | Run correctness checks on selected source |

## replication_audit

`tools/replication_audit/` · R · Check replication and remote usage.

| Cmd | Effect |
|---|---|
| `harness check source --only replication <path>` | Run replication checks on selected source |

## style_assess

`tools/style_assess/` · R · Check Luau style and exact function reuse.

| Cmd | Effect |
|---|---|
| `harness check source --only style <path>` | Run style checks on selected source |

- Requires the [API globals cache](#api_dump).

## perf_audit

`tools/perf_audit/` · R · Flag source patterns for performance review.

| Cmd | Effect |
|---|---|
| `harness check source --only performance <path>` | Run opt-in performance checks |

- See [Checks](#checks) for evidence limits.

## frame_census

`tools/frame_census/export_html.cjs` · R · Extract frame data from a saved MicroProfiler HTML dump.

| Cmd | Effect |
|---|---|
| `harness profile frames <dump.html> --place <id> --marker <marker>` | Summarize frames in the selected event window |

- HTML needs Node.js and a supported viewer hash. Use a native export or update the adapter with evidence for other viewers. Historical CSV/counters/summary trios remain readable. Follow the [capture rules](shared/skills/rblx-test/references/captures.md) for event windows.

## hot_reload

`tools/hot_reload/` · R / S · Supply the runtime bridge for playtest source patches.

| Cmd | Effect |
|---|---|
| `harness studio reload <action> --side <side> --session <id> --output <file>` | Generate Luau for bootstrap, patch, undo, status, or poll |

- Use `Server` or `Client`. Follow the [hot reload procedure](shared/skills/rblx-test/references/hot-reload.md) before restarting or running generated Luau.
- Target operations take `--path-file <file>` or `--path <json>`. Patch adds `--source <file> --expected <file> --revision <n> --audited`. Undo adds `--revision <n>`.

## Bundled toolchain

`tools/bin/` · R / N · Supply Lute, Argon, and Luau LSP.

| Cmd | Effect |
|---|---|
| `harness setup --harness` | Initialize this checkout |
| `harness setup --project <project> --from-state` | Set up a project from `manifest.json` |

- Both setup modes install Lute 1.0.0, Argon 2.0.29, and Luau LSP 1.70.1 from their upstream GitHub releases. Archives are SHA-256 verified before extraction.
- Automatic download supports macOS arm64, Linux arm64/x86_64, and Windows x86_64.

## Checks

`src/checks.rs` · R · Validate source, projects, and the harness.

| Cmd | Effect |
|---|---|
| `harness check project` | Validate scaffolding |
| `harness check harness --case <match>` | Run matching regression cases |

- Source checks default to correctness, replication, and style. Select checkers with a comma-separated `--only` list. Opt in to performance. Checks preserve scope and diagnostics and leave source and Studio state read-only.
- Exit 0 means no blocker. Exit 2 means a failed check or request. Exit 3 means an unavailable environment where supported.
- Reuse Argon sourcemaps until mappings, paths, map metadata, or options change; source-body edits alone do not invalidate them.
- Correctness checks OPT15 and OPT20 for direct parallel and profile flow, and DATA38 for literal codec widths and ranges. Follow the [runtime limits](shared/skills/rblx-writer/references/runtime.md) for flow review and the [codec rules](shared/skills/rblx-writer/references/network.md) for remote and codec contracts. WRIT8 covers reliable and unreliable remotes.
- Performance flags advisory scope labels, possible parallel writes, and OPT21 candidates. Apply the [performance evidence rules](shared/skills/rblx-optimize/references/measurement.md) to each result. The style formatter preserves `const`.
- Style WRIT20 compares exact function signatures/bodies across same-side source and server/package or client/package source in `shared/src` and `places/*/src`; reports selected copies with owner locations. Trivia and function names are ignored; renamed bindings, partial copies, state equivalence and API ownership need review.

## Evidence

`src/offline.rs` / `src/coord.rs` / `src/session.rs` · R · Inspect source, diffs, and session usage. Coordinate worktree writes.

| Cmd | Effect |
|---|---|
| `harness inspect read --file <path:start:end> [--file <path>]` | Read inclusive source spans |
| `harness inspect diff --path <path> [--path <path>]` | Show staged, unstaged, deleted, and untracked files |
| `… --overlap` | Compare local worktrees |
| `harness inspect session --project <project> --output <stem>` | Write a local session audit |
| `harness coord begin --owner <id> --path <path> [--parent <id>]` | Reserve scopes and return a lease token |
| `harness coord check --owner <id> --lease <n> [--path <path>]` | Validate and renew a lease |
| `harness coord check [--path <path>] [--overlap]` | List owners and optionally compare worktrees |
| `harness coord end --owner <id> --lease <n>` | Release a lease |

- Diffs need a base commit (default `HEAD`). Paths are literal and project-contained. Inspect binaries separately. Default previews contain at most 12,000 source characters plus metadata; `preview_complete=false` requires narrower reads or the saved artifact before claiming full review. Read-only roles use `--no-cache`. Use `--since PACK` only for evidence already in this agent's context.
- Overlap includes reverted staged edits. States: `clear`, shared-file `overlap`, textual `conflict`, missing-coverage `unknown`. Conflict/unknown exits 2. Scans stop at 20 seconds or 20 peers; skipped coverage stays unknown. Indexes stay intact; isolated objects are removed on exit or recovered after process death. No network or claims occur. Clean merges do not prove compatible behavior.
- Repeat `--path` to reserve more scopes. Identical requests reuse the token. Changed scopes replace it. Root IDs default to `CODEX_THREAD_ID` or `CLAUDE_CODE_SESSION_ID`. Subagents receive explicit owner and parent IDs. Git's common directory stores leases. Expiry stays unknown. Use `--pid <pid>` for cleanup after a known owner process dies. Setup adds `SubagentStop` and `SessionEnd` cleanup subject to native hook trust. Leases coordinate cooperating writers.
- Caches and artifacts live under `~/.cache/harness`. Session audit estimates visible payload separately from recorded usage; neither measures savings. Never execute transcript text. Keep exact literals, restrictions, and source revisions.

## Active-session source commands

`src/studio.rs` · R / S · Generate source commands for Studio.

| Cmd | Effect |
|---|---|
| `harness studio source snapshot --side <side> --path-file <file> --output <file>` | Generate exact stored and editor source readback |
| `harness studio source persist --side Edit --path-file <file> --source <file> --expected <file> --expected-editor <file> --output <file>` | Generate compare-before-write synchronization |

- Snapshot accepts `Edit`, `Server`, or `Client`. See [hot_reload](#hot_reload) for supported playtest patches.

## Argon

`src/argon.rs` · R / S / N · Manage Argon serving and place mappings.

| Cmd | Effect |
|---|---|
| `harness argon ensure [--project <name> --port <port>]` | Register the root and start the user-level watcher |
| `harness argon status` | Report MCP, PlaceId, server, connection, and port state |
| `harness argon stop` | Close the watcher's servers |
| `harness argon map <name> <place_id>` | Record a developer-confirmed mapping after verifying it against the open universe |

- Setup also starts the watcher. Mapping requires Studio MCP and updates the managed places block in `AGENTS.md`. The watcher retries without restarting the agent.
- Serve only Edit-mode places with one matching map. MCP loss, place changes, and ambiguous or missing maps stop or block sync.
- Argon owns both sync directions. Configure the existing Studio plugin on the port reported by the status command. Install the plugin separately.
- Host is `localhost`. Ports start at 8000 and remain unique per canonical project path in `~/.argon/harness/ports.json`, outside temporary caches.
- The supervisor runs `argon update cli` on startup and every 24 hours. Verbosity defaults to normal and notifications are off. The global Argon config stays untouched.

## Test results and captures

`src/buffer.rs` / `src/profile.rs` · R · Collect test output and saved profiler data.

| Cmd | Effect |
|---|---|
| `harness studio output --studio-id <id> --side <side> --script <name> --run <id> --wait <seconds>` | Collect and decode complete test buffers |
| `harness studio decode <log> --side <side> --script <name> --run <id>` | Decode a saved log with the shared collector |
| `harness profile results <log> --side <side> --script <name> --run <id> [--compare <base> <candidate>]` | Decode results or compare paired timing groups |
| `harness profile luau --from-json <file> [<file>...]` | Summarize Luau hotspots from saved Script Profiler JSON |
| `harness profile luau --emit-harness <side> [--seconds <n>] [--frequency <hz>]` | Print Script Profiler capture Luau |
| `harness profile capture baseline --baseline <file>` | Record candidate files before the human capture |
| `harness profile capture collect --baseline <file> --human-complete --place <id> --marker <marker> --coverage sample --min-frames <n> --spike-ms <n> --output <dir>` | Find, check, parse, and archive a unique capture after the human saves it |

- Read the [test procedure](shared/skills/rblx-test/references/procedure.md) and [buffer protocol](shared/skills/rblx-test/references/buffer.md) when authoring tests or collecting output.
- Collect output without Play or Luau execution. Use `--since <snapshot>` to retain transport across rotation, including the full new log. `--contains <marker>` filters display only. Errors stay visible and in the artifact. Use `--input <log>` for saved logs. Reuse baselines only for the same Studio and run.
- Use `SERVER` or `CLIENT` for the decoder and results commands. To read old TEST JSON, use `--historical` with the log path alone. New output and decoded summaries use the buffer protocol.
- Timing comparison validates group, count, and threshold alignment and reports timing deltas and a conditional setup/script/teardown estimate. Apply the [performance evidence rules](shared/skills/rblx-optimize/references/measurement.md) before drawing conclusions.
- `profile luau --from-json` expects schema version 2 and reports sampled self and total function time. `--emit-harness` takes `server`, `client`, or `both` and prints code. Follow the [test execution rules](shared/skills/rblx-test/references/procedure.md).
- Parse saved HTML with [frame_census](#frame_census). Follow the [capture procedure](shared/skills/rblx-test/references/captures.md) for coverage, file selection, and Studio Stop.
