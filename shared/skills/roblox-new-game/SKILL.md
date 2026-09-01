---
name: roblox-new-game
description: Conducts a gameplay-loop-first file-shaping interview, obtains consent to install the GitHub-hosted rblx-harness dependency, deterministically scaffolds a Roblox game, then requests project-hook authorization. Use when starting a Roblox project; do not use for routine feature changes.
---

# roblox-new-game — interview and scaffold

Four ordered phases; never skip to the scaffold or invent file-shaping
decisions.

Resolve `<SKILL_DIR>` as the real directory that contains this `SKILL.md`.
Run the bundled scaffolder from `<SKILL_DIR>/scripts/scaffold.py`.

`roblox-new-game` is a user-scope skill. Never copy or link it into the target
project. The cloned `.roblox-harness` dependency is the only source for the
project-local `roblox-writer`, agents, hooks, gates, and rules. Project setup
does not install Roblox harness hooks at user scope.

`answer` and `emit` require the empty `.roblox` sentinel and initialized
project-local dependency. They do not require schema-3 session authorization:
the new-game scaffold must finish before the user is asked to authorize its
new project hooks. `backfill` and all post-scaffold project work require the
schema-3 authorization created by a successful documented host `SessionStart`.
The standalone `permissions_harness.py` command validates Codex configuration
only. An approval prompt does not create runtime authorization.

## Phase 0 — the interview

Accept every explicit answer the user already supplied. Questions may be batched;
re-ask only missing or contradictory file-shaping fields.

Start by obtaining the gameplay loop unless the user already supplied it: ask
what players are doing in the current test. Treat that loop as temporary
proposal context: do not record it in criteria or runtime instructions, and do
not make it a future-agent constraint.

Before asking any remaining file-shaping question, derive a concrete proposed
answer from that loop and include it as an example in the question. Give a
separate loop-derived example for places, Services, and Controllers when
batching questions. Adapt names and scopes to the supplied loop; do not reuse a
stock example. The examples are proposals only. Accept a field after the user
explicitly confirms or replaces its proposal.

Propose the smallest stable mechanic seams as Services and Controllers. Keep
each accepted answer in the current conversation; do not run
`scaffold.py answer` yet.

The blocking set (flag — file effect — question):

1. `places` — creates one place tree and Argon project per name — which
   places should exist now? Include a loop-derived example using
   comma-separated safe names.
2. `services` — creates the confirmed keystone service modules — which
   shared and place-scoped Services should exist? Include a loop-derived
   example using `shared: Name; Place: Name`, or propose `none`. PlayerData,
   Payments, Updates, and Effects already ship as prescribed services.
3. `controllers` — creates the confirmed keystone controller modules — which
   shared and place-scoped Controllers should exist? Include a separate
   loop-derived example using the same scoped format, or propose `none`.
   Effects, Gui, and Updates already ship as prescribed controllers.

Do not ask for a target or final build stage, roadmap, fixed player count,
device, replication plan, data shape, GUI ownership, remote surface, camera,
rig or animation-conversion choice, or streaming choice during this scaffold.
Those decisions belong to the feature work that consumes them.

GUI responsibility is fixed, not interviewed: agents may write GUI code,
humans create GUI instances, and agents inspect those instances through the
Studio MCP.

After the gameplay loop, obtain every missing file-shaping answer. Also obtain
the project name and destination directory if they were not supplied and cannot
be inferred safely. Do not start installation or integration before the entire
interview is complete.

## Phase 1 — harness consent and integration

Create the project directory explicitly after the interview. Run the setup
tool once without `--yes` and without supplying terminal input:

```bash
python3 <SKILL_DIR>/scripts/dependency.py setup --root <dir>
```

The tool returns `CONSENT_REQUIRED` with the exact question beginning
`Do you want to install rblx-harness?` and makes no change. Ask the user that
question and stop. Do not infer consent from the new-game request or interview
answers, and do not pipe or synthesize an answer. After an explicit yes, run:

```bash
python3 <SKILL_DIR>/scripts/dependency.py setup --root <dir> --yes
```

In Codex, run this approved command outside the sandbox. The sandbox can block
access to the macOS keyring and make `gh auth status` report a false invalid
token. If setup reports that GitHub authentication is unavailable inside the
Codex sandbox, rerun the same approved command outside the sandbox. Do not
classify that result as invalid user authentication.

The approved setup verifies Git, verifies an authenticated GitHub CLI session,
and confirms access to `lennyRBLX/rblx-harness`. It initializes the project Git
repository only when absent, creates the empty `.roblox` marker only when
absent, adds `https://github.com/lennyRBLX/rblx-harness.git` as the
`.roblox-harness` submodule, and clones it locally. It then runs the cloned
harness's canonical relinker. `roblox-writer`, both host agent sets, and both
host hook definitions are installed into the project. Gates remain at
`.roblox-harness/shared/gates`; rules remain at
`.roblox-harness/shared/CORE.md`. The GitHub credential helper is configured in
the project and dependency repositories only, never globally. The Codex Roblox
permission preset is host configuration; it does not install harness hooks at
user scope.

Setup validates the cloned project-local installation API before it runs the
relinker. A clean partial `.roblox-harness` install is updated from its
registered remote on retry. Existing staged `.gitmodules` and
`.roblox-harness` entries are reused.

When setup reports changed profile or hook discovery, retain that result for
Phase 3. Do not ask the user to select `Roblox`, approve hooks, or retry host
discovery yet. Setup never creates runtime authorization. Continue directly to
the scaffold.

## Phase 2 — record and scaffold

Record every accepted file-shaping answer separately, including fields supplied
together. Do not repeat the interview and do not require current-task
authorization:

```bash
python3 <SKILL_DIR>/scripts/scaffold.py answer <flag> "<text>" --root <dir>
```

```bash
python3 <SKILL_DIR>/scripts/scaffold.py emit --root <dir> --name <ProjectName>
```

The scaffolder refuses to emit until the three file-shaping fields are complete
and names the unanswered items — re-ask exactly those. On success it preserves
the pre-created empty root-level `.roblox` managed-project sentinel and emits
the tree,
both runtime instruction files — CLAUDE.md (Claude Code: import + two
blocks) and AGENTS.md (Codex/ChatGPT: reads CORE.md + CODEX.md, same two
blocks) — one Argon project per place, confirmed keystone module files, the
gitignores, the `.claude/` links and settings, the museum links, and the
prescribed service templates. The runtime summary records only the confirmed
keystone architecture, never the temporary gameplay loop.

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

The criteria file is deleted when the scaffold lands. Nothing reads it
afterward. Playtests, temporary Free-for-All slices, mechanics such as Double
Jump, mode changes, and changes to player count are ordinary feature work.
They may add, retain, or remove Services and Controllers without a stage,
milestone, final-build path, or new-game re-interview.

## Phase 3 — authorize project hooks

After `emit` reports `EMITTED`, tell the user that scaffolding is complete.
Then ask the user to trust the project and authorize the installed hooks. When
setup or emit reported a changed permission profile or hook definition, ask
the user to select `Roblox` and review and approve the changed hooks. Do not
perform feature work before this post-scaffold authorization.

After the user completes the host action, retry `SessionStart` in the current
task. Continue only after current-task authorization succeeds. Exact hook bytes
do not need another hook approval, but they still require a successful
documented `SessionStart` for a task that has no authorization.

## Repairs

From the project root, run:

```bash
python3 .roblox-harness/openai/setup/permissions_harness.py --relink
```

re-creates `.claude/agents/`, `.claude/skills/`, the settings hook block, and
the Codex integration from `.roblox-harness`'s canonical form. It never writes
project Git metadata.

After cloning an existing project, initialize the dependency before relinking:

```bash
python3 <SKILL_DIR>/scripts/dependency.py init --root <dir>
python3 .roblox-harness/openai/setup/permissions_harness.py --relink
```
