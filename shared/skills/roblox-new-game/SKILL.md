---
name: roblox-new-game
description: Conducts the blocking design interview and deterministically scaffolds a harness-managed Roblox game with Claude Code and Codex integration. Use when starting a Roblox project or re-interviewing an existing game for a milestone; do not use for routine feature changes.
---

# roblox-new-game — interview, scaffold, consume

A game that cannot state its core loop does not get a codebase [R DES3].
Bootstrap plus three phases; never skip to the scaffold, never invent answers.

Resolve `<SKILL_DIR>` as the real directory that contains this `SKILL.md`.
Run the bundled scaffolder from `<SKILL_DIR>/scripts/scaffold.py`.

Install or repair the exact user Codex permission profile with:

```bash
python3 <SKILL_DIR>/scripts/scaffold.py install-profile
```

The installer preserves unrelated Codex settings. When it changes the active
profile or discovered hooks, select `Roblox`, review the changed hooks, and
retry host discovery in the current task. Record changed hooks for integration
maintenance. Exact bytes need no retry.

`answer`, `emit`, and `backfill` require the empty `.roblox` sentinel and the
schema-3 authorization created by a successful documented host
`SessionStart`. The standalone
`permissions_harness.py` command validates Codex configuration only. On
`BLOCKED|PERMISSIONS_HARNESS`, do not write interview state, project files,
generated cache, Studio, or patches. The human must trust the project, review
and approve the hooks, then install and select Roblox. Retry `SessionStart` in
the current task; an approval prompt does not satisfy this prerequisite.

## Phase 0 — marker and authorization bootstrap

Create the project directory explicitly, then run:

```bash
python3 <SKILL_DIR>/scripts/scaffold.py bootstrap --root <dir>
python3 <SKILL_DIR>/scripts/scaffold.py relink --root <dir>
```

`bootstrap` is the marker-only exception: it creates exactly one empty
root-level `.roblox` regular file and refuses to create the root or overwrite
any other sentinel shape. It writes no interview state, source, integration,
or authorization. `relink` is the deterministic integration exception. It
installs or repairs the static profile and generated hook integration, but it
never writes runtime authorization. Select `Roblox`, review changed hooks,
retry host discovery, and continue after current-task authorization succeeds.
No interview or scaffold write is permitted before authorization.

## Phase 1 — the interview

Accept every solid answer the user already supplied. Questions may be batched;
re-ask only fields that are missing or contradictory. An answer that does not
state verb-object-reward (question 1) is rejected at the question. Record each
accepted field separately, including fields supplied together:

```bash
python3 <SKILL_DIR>/scripts/scaffold.py answer <flag> "<text>" --root <dir>
```

The blocking set (flag — question):

1. `core_loop` — the scoped core loop, one testable verb-object-reward
   statement. "Explore and have fun" is refusal-grade.
2. `services` — the 3–5 seed services the loop needs. Prefer bare feature
   nouns such as `Runs` and `Loot`; a `Service` or `Controller` suffix is a
   WRIT10 naming advisory, not a refusal. PlayerData, Payments, and Updates
   ship as prescribed templates regardless.
3. `device` — target device & bandwidth: the weakest device served, the
   project's prime lens.
4. `replication` — replication picks per state class: Folders + ValueObjects
   (shared) · Exclusive (per-player) · remotes (events). State explicitly
   whether generated or streamed world geometry exists. If it does, settle
   server authority and the seed/chunk/layer replication model; otherwise say
   that the shipped world is static or hand-built.
5. `data_shape` — the persistent template's top-level shape, the Development
   fixture's filled values, and why each state is persistent or intentionally
   session-only. Use an explicit `reason:` or `because` clause. An empty
   persistent shape is still an explicit decision, for example
   `no persistent data because rounds reset; Development={}`.
6. `gui_ownership` — which humans own which GUI. Agents never hand-write GUI.
7. `security` — which remotes exist, what the client may trigger, and which
   side owns final validation and authority. Prefer bare-intent remote names;
   `Request<X>` is a WRIT11 naming advisory, not a refusal. Keep one remote per
   action family.
8. `place_map` — each place the game ships, its services and controllers,
   what carries over. Use one `Place: services ..., controllers ..., carry
   ...` clause per place; separate places with a newline or semicolon. Staging
   is free.
9. `camera` — camera perspective per place (e.g. `Lobby=3rd,Game=1st`).
   Client-controller logic, never a CameraMode pin.
10. `rig` — R6, R15, or R15-R6. R15-R6 vendors the AnimationConverter and
    records the animation-import gate.
11. `streaming` — `on`, or `off: <explicit reasoning>`. The opt-out is
    harshly gated: challenge any mismatch with question 3 until the
    reasoning survives.

## Phase 2 — the scaffold

```bash
python3 <SKILL_DIR>/scripts/scaffold.py emit --root <dir> --name <ProjectName>
```

The scaffolder refuses to emit until the criteria file is complete and names
the unanswered items — re-ask exactly those. On success it preserves the
pre-authorized empty root-level `.roblox` managed-project sentinel and emits
the tree,
both runtime instruction files — CLAUDE.md (Claude Code: import + two
blocks) and AGENTS.md (Codex/ChatGPT: reads CORE.md + CODEX.md, same two
blocks) — one Argon project per place, the gitignores, the `.claude/` links
and settings, the museum links, and the prescribed service templates.

The two entries are named children — `ServerScriptService/Server.server.luau`
and `StarterPlayerScripts/Client.client.luau` — never `init.server.luau` or
`init.client.luau`. A service is never a script: an `init.luau`, or any
`init.<type>.luau`, directly under a service directory makes Argon emit the
*service itself* as that script, which is not a thing the DataModel has. This
holds for every service — ReplicatedStorage, ServerStorage, ReplicatedFirst,
Workspace, StarterPlayer, StarterPlayerScripts, StarterCharacterScripts,
StarterGui, StarterPack. One level down the form is legal and expected:
`Services/Shop/init.luau` is a directory package whose parent is a folder.
The write-gate refuses the write [R GATE2] and the Stop floor sweeps the tree.

Three shared controllers are parents rather than leaves — `Effects`, `Gui`,
`Updates` — so every place also gets
`places/<Place>/src/StarterPlayer/StarterPlayerScripts/{Effects,Gui,Updates}/`
for its single-place children. Each place project mounts those three at
`StarterPlayerScripts.PlaceChildren`, and the client entry grafts them onto
the matching shared controller before anything is required — a controller
still reads only its own `script:GetChildren()` and never learns a place
exists. Argon emits a duplicate rather than merging a declared child into a
`$path`-mounted tree, which is why the graft is a runtime reparent and not
project-file nesting. A child that more than one place wants is not a place
child: it belongs in `<game>/shared/` like anything else shared.

## Phase 3 — consume

The criteria file is deleted when the scaffold lands. Nothing reads it
afterward; the durable output is CLAUDE.md's summary line. Growth is a
re-interview, not a stored plan:

```bash
python3 <SKILL_DIR>/scripts/scaffold.py emit --root <dir> --name <ProjectName> --milestone
```

re-runs the blocking set against what the game now is and rewrites the
summary. A 1.0 → 2.0 step runs it; so does a playtest that kills a mechanic.

## Repairs

From the project root, run:

```bash
python3 ../harness/openai/setup/permissions_harness.py --relink
```

re-creates `.claude/agents/`, `.claude/skills/`, the settings hook block, and
the Codex integration from harness/'s canonical form. It never writes project
Git metadata.
