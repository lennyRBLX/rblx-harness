# rblx-harness

Use `rblx-harness` to build controlled Roblox projects w/ rules, lifecycle
hooks, write gates, review agents, scaffolds, validators, & shared Luau pkgs.

Mark each managed Git root w/ an empty `.roblox` file. Pin the harness as the
`.roblox-harness` Git submodule. Run generated hooks from that local rev.
Update the harness by updating the submodule rev.

Use 3 skills:

- Install `roblox-new-game` at user scope for Codex or Claude Code. Use it to
  gather inputs, install the harness w/ consent, & create a fixed game tree.
- Install `roblox-writer` per project via the scaffold or relinker. Use it to
  gate Roblox research, types, writes, optimization, debug, review, & checks.
- Install `math-tool` at user scope. Use it for bounded symbolic math.

## Requirements

Install & set up:

- Python 3.
- Git.
- GitHub CLI (`gh`): run `gh auth login` w/ access to
  `lennyRBLX/rblx-harness`.
- [Argon](https://argon.wiki/docs/installation): add `argon` to `PATH`, then
  run `argon plugin install`. Use Argon project files to map files to the
  Roblox DataModel.
- [Serena MCP](https://github.com/oraios/serena): use it for project symbol &
  ref queries.
- [Roblox Studio](https://create.roblox.com/docs/studio/setup): install the
  current release. Open **Assistant > ... > Manage MCP Servers**, enable
  **Studio as MCP server**, & keep the target place open for DataModel,
  console, or playtest tasks.
- Codex or Claude Code w/ project trust & hook support.

### Install Serena MCP

Install `uv`, then run:

```bash
uv tool install -p 3.13 serena-agent
serena init
```

Connect each host:

```bash
serena setup codex
serena setup claude-code
```

Use the [Serena client config](https://oraios.github.io/serena/02-usage/030_clients.html)
to expose Serena tools in each host.

## Install the skills

Clone & enter the repo:

```bash
gh repo clone lennyRBLX/rblx-harness
cd rblx-harness
```

### macOS or Linux

Install `roblox-new-game` for Codex & Claude Code, add Codex metadata, then
install `math-tool` & its lifecycle hooks:

```bash
R="$(pwd)"
C="$HOME/.agents/skills/roblox-new-game"
L="$HOME/.claude/skills/roblox-new-game"

mkdir -p "$C/agents" "$L"
cp -R "$R/shared/skills/roblox-new-game/." "$C/"
cp "$R/openai/skills/roblox-new-game/agents/openai.yaml" "$C/agents/"
cp -R "$R/shared/skills/roblox-new-game/." "$L/"
python3 "$R/openai/setup/math_tool.py" --install
```

Load Codex skills from `$HOME/.agents/skills` & Claude Code skills from
`$HOME/.claude/skills`. Restart each host to load new skills. Install
`roblox-writer` per managed project via its scaffold or relinker.

### Windows

Run in PowerShell from the harness checkout:

```powershell
$R = (Get-Location).Path
$C = Join-Path $env:USERPROFILE ".agents\skills\roblox-new-game"
$L = Join-Path $env:USERPROFILE ".claude\skills\roblox-new-game"

New-Item -ItemType Directory -Force (Join-Path $C "agents"), $L | Out-Null
Copy-Item (Join-Path $R "shared\skills\roblox-new-game\*") $C -Recurse -Force
Copy-Item (Join-Path $R "openai\skills\roblox-new-game\agents\openai.yaml") (Join-Path $C "agents") -Force
Copy-Item (Join-Path $R "shared\skills\roblox-new-game\*") $L -Recurse -Force
py -3 (Join-Path $R "openai\setup\math_tool.py") --install
```

From each managed project root, init the submodule, then run:

```powershell
.roblox-harness\setup_windows.bat
```

## Create a game

Start a new host session & request:

```text
Use $roblox-new-game to create a Roblox game.
```

Follow the skill flow:

1. Define the test loop, places, Services, Controllers, name, & path.
2. Approve the harness install.
3. Run the approved Codex setup cmd outside the sandbox for keyring access.
4. Trust the project.
5. Review the installed hooks.
6. Select the Roblox permission profile.
7. Allow `SessionStart`, then start feature work.

The skill records confirmed inputs, uses the current folder as the Git root,
adds the empty `.roblox` marker, adds & pins `.roblox-harness`, then relinks the
project.
The relinker installs `roblox-writer`, agent defs, & project hooks for Codex &
Claude Code. The scaffold creates 1 Argon project per place plus shared &
place source trees, confirmed Service & Controller modules, project rules,
hooks, review agents, & pkg/service templates.

For a partial setup, update the dependency remote & rerun the same setup cmd.
Let the relinker reuse & update the partial submodule, then retry integration.

## Example `roblox-new-game` interview

```text
Agent: What actions do players repeat, what result or reward do they get, & how
does the cycle continue or restart? Share a rough idea & I will help shape it.

User: Exit a lobby, enter a timed ruin, collect relics, return, & bank them.

Agent: Proposed loop: leave the lobby, enter a timed ruin, collect relics,
return before time expires, bank the relics, then start another run. Is that
correct?

User: Yes.

Agent: Which places will exist in the game? Based on that loop, I recommend
`Lobby, Ruin`. The project keeps a multi-place layout even with one place.

User: `Lobby, Ruin`.

Agent: Which shared & place Services should exist? Based on the loop, I
recommend `shared: RelicInventory; Ruin: ExpeditionRound`.
PlayerData, Payments, Updates, & Effects ship w/ the harness.

User: `shared: RelicInventory; Ruin: ExpeditionRound`.

Agent: Which shared & place Controllers should exist? Based on the loop & the
confirmed Services, I recommend `shared: RelicHud; Ruin: RelicInteraction`.
Effects, Gui, & Updates ship w/ the harness.

User: `shared: RelicHud; Ruin: RelicInteraction`.

Agent: rblx-harness provides the project structure, hooks, gates, & rules
needed for this setup. Would you like me to install it from
https://github.com/lennyRBLX/rblx-harness.git in `/path/to/RelicRun`? Please
answer Yes or No.

User: Yes.

Agent: Scaffold complete. Trust the project, select the Roblox permission
profile, review & approve its hooks, then confirm host auth for `SessionStart`.
```

Treat gameplay-loop text as proposal context. Persist confirmed file-shaping
answers in the `RelicRun` scaffold.

## Existing managed projects

Init & relink after cloning:

```bash
git submodule update --init --recursive -- .roblox-harness
python3 .roblox-harness/openai/setup/permissions_harness.py --relink
```

Run the project check from its root:

```bash
python3 .roblox-harness/tools/project_gate/project_gate.py --project-root "$(pwd)"
```
