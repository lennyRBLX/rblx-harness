## Roblox work

Harness CLI: `harness [--root PROJECT] FAMILY ...`; install the Rust binary with
`H/tools/cargo-clean.sh install --path . --locked` (cleans build artifacts afterward).

- Before development, register the project with `harness --root PROJECT argon ensure`. Argon opens a server only after Studio MCP verifies exactly one mapped PlaceId; if unmatched, ask the developer for the project mapping and run `harness --root PROJECT argon map NAME PLACE_ID` in the same session.
- Use Argon-resolved source for project behavior. Before mutation, validate remote types, sizes, finite ranges, and ownership. Release owned connections, tasks, and instances when their lifetime ends.
- Use `harness --root PROJECT types write` for data defaults, generated owner types, and public declarations; it validates and commits related files together. Resolve changed public APIs with `types read`.
- Use current scoped engine evidence before relying on access or behavior; query `api` only for missing or invalidated answers. Keep caller, phase, restrictions, source revision, and the selected skill's engine reference.
- Run commands for missing evidence or required changes only. Use scoped `rg`, bounded reads, native edits, Git, and harness helpers for domain validation or batched evidence. Batch independent operations; sequence dependencies. Inspect results; preserve failures and required output. Use non-login shells unless initialization requires otherwise. Read needed `rblx-harness/shared/TOOLS.md` sections and unfamiliar command help only.
- Prefer subagents when a concrete task split improves speed or output quality with efficient total token use. Handle small edits and settings tweaks directly unless complexity or risk warrants delegation. For team roles, reuse, assessment order and limits, load `H/shared/skills/rblx-plan/references/delegation.md`.
- For Studio checks, use the user's selected environment and existing execution authorization; otherwise obtain the human result. Prepare persistent Studio source and new test drivers/invocation in stopped Edit mode. For supported iteration in an authorized active session, use rblx-test's hot-reload reference. Use shared test support and its independent collection pipelines. Report passed, failed, reused, unrun, and skipped checks accurately.
- Select each test by one decision, question, stable ID and stopping condition. Start with the broadest useful measurement; remove prerequisites that cannot affect the decision. Required checks remain required. After edits settle, run the smallest decisive check. Test unresolved behavior only, not prose or implementation-mirroring assertions. Reuse valid findings and documented engine facts; keep authored-algorithm correctness separate. Permit necessary measurement repeats, failure reproductions and checks affected by source or workload changes. Run full suites for broad changes or explicit requests only.
- Pass exact paths, APIs, literals, restrictions, and open questions. Keep evidence revisions, scope, inputs, and environment in existing context or requested artifacts. Reuse evidence until relevant dependencies, fixtures, options, or environment change; rerun only affected checks. Compaction, review, and completion do not invalidate evidence. Create no receipts.

## Writing

- Keep docs token-minimal. Use short words and omit filler.
- Store each rule once and link to it.
- Omit skill names, references to these instructions, and hashes from project docs.
- Make plans fully actionable.
- Write prompts without repeated information.

## Tools

- Write non-Luau tools in Rust under `tools/`. Extend an existing tool before adding one.
- List each tool in the root [TOOLS.md](TOOLS.md) beside `tools/`.
- Use `## <name>`, a `` `path` · access · purpose. `` line, a `| Cmd | Effect |` table, then flag and limit bullets. Use the Conventions tokens from the harness `TOOLS.md`. Keep entries technical and short. Link shared rules.

## Modules

- Give each module one responsibility. Preserve gameplay and public and network contracts. Keep behavior on singleton modules, data in plain tables, and game objects in Roblox Instances. Avoid custom classes and per-entity method tables.
- Add child modules only for distinct subsystems, substantial algorithms, or execution boundaries. Each child owns its state, resources, and lifecycle. File length, formatting, helper grouping, debugging, and diagnostics do not justify a split.
- Parents may expose public APIs, forward operations, and start children with `task.spawn(Child.Start, Child)`. Avoid other forwarding layers, dependency-context objects, and helpers without distinct work.
- Expose only necessary public methods. Use PascalCase for public APIs and lowerCamelCase for internal colon methods. Keep data helpers, cleanup callbacks, and external callback adapters local. Name Troves `_t`, or use the first letter of the clearest contextual name if `_t` is taken.
- `:Start()` takes only `self`, wires startup and enumerates existing state. Return nothing unless a caller contract requires it. Declare cyclic dependencies as `nil` locals with the other dependencies and assign them in `:Start()`. Use `while shared.Running do` for loops in `:Start()`.
- Use internal `playerAdded` and `characterAdded` methods and local `cleanupPlayer` and `cleanupCharacter` helpers. Enumerate existing players with `task.spawn(self.playerAdded, self, player)` before connecting `Players.PlayerAdded`. Use `PlayerData.Ready` only for work that needs a loaded profile. Keep `playerAdded` independent of profile readiness.
- Use `DEFAULT_STATE` for player and NPC state and `DEFAULT_CHARACTER_STATE` for respawn-reset state. Use `m.State` for one player and `m.__players` with `GetState` for several.
- Gate data access with `PlayerData:Valid(player)`. Check PlayerData and getter results by truthiness.
- Clean up owned resources as gameplay lifecycles change. Gameplay modules omit module teardown, shutdown cleanup, `BindToClose`, and cleanup of permanent `Start()` connections. Create connection collections and character subscriptions only when owned resources need them. Pass context as the third argument of `EntityCleanup:Add` and release owned resources in the cleanup helpers.
- Call connection handlers directly unless ordering, batching, or concurrency requires scheduling. Yielding alone does not justify `task.defer`.
- Use `Event` for remotes, `Global` for shared ValueObjects, and `Exclusive` for player-private ValueObjects. Keep player-private ValueObjects out of `PlayerGui`. Name the internal method for `Exclusive:Set()` `updatePlayerReplicatedInfo` and call it through `self`. Leave Player-owned replicated Instances to the Player lifecycle and omit departure-removal flags.
- Keep remote sends and receives free of varargs and new rate limits.
- Put server-exclusive enums in `shared/src/ServerScriptService/Modules/Enums.luau` and shared or client-exclusive enums in `shared/src/ReplicatedStorage/Modules/Enums.luau`.
- Edit `Server.server.luau` and `Client.client.luau` only when explicitly requested.
- Keep actionable errors and warnings. Remove routine diagnostic prints and redundant diagnostics.
