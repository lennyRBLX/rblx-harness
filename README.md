# rblx-harness

`rblx-harness` is a controlled development harness for Roblox projects. It
supplies the project rules, lifecycle hooks, write gates, review agents,
scaffolding tools, validation tools, and reusable Luau packages for Codex and
Claude Code.

A managed project has an empty `.roblox` file at its Git root. The harness is
stored in that project as the revision-pinned `.roblox-harness` Git submodule.
Generated hooks run the files from this local submodule. A project update does
not change the harness until the submodule revision changes.

The harness supplies three skills:

- `roblox-new-game` is a user skill. It interviews the user, installs the
  harness with consent, and creates a deterministic game tree.
- `roblox-writer` is a project skill. It controls Roblox code changes through
  research, type, write, optimization, debug, review, and validation gates.
  The project relinker installs this skill.
- `math-tool` is a user skill. It runs bounded symbolic calculations that the
  harness requests.

## Requirements

Install these items before you use the harness:

- Python 3.
- Git.
- GitHub CLI (`gh`). Authenticate it with `gh auth login`. The account must
  have access to `lennyRBLX/rblx-harness`.
- [Argon](https://argon.wiki/docs/installation). The `argon` command must be
  on `PATH`. Install the Studio plugin with `argon plugin install`. The harness
  uses Argon project files as the source map between the file tree and the
  Roblox DataModel.
- [Serena MCP](https://github.com/oraios/serena). The harness uses Serena for
  symbol and reference queries in project code.
- [Roblox Studio](https://create.roblox.com/docs/studio/setup). Install the
  current release. In Studio, open **Assistant > ... > Manage MCP Servers** and
  enable **Studio as MCP server**. Keep the applicable project place open when
  a task needs DataModel, console, or playtest information.
- Codex or Claude Code with project trust and hook support.

### Install Serena MCP

Install `uv`, then run:

```bash
uv tool install -p 3.13 serena-agent
serena init
```

Connect Serena to each host that you use:

```bash
serena setup codex
serena setup claude-code
```

See the [Serena client configuration](https://oraios.github.io/serena/02-usage/030_clients.html)
if a host does not show the Serena tools.

## Install the skills

Clone this repository first:

```bash
gh repo clone lennyRBLX/rblx-harness
cd rblx-harness
```

### macOS or Linux

Install `roblox-new-game` at user scope for Codex and Claude Code. Install the
optional Codex display metadata. Then install `math-tool` and its lifecycle
hooks.

```bash
HARNESS_ROOT="$(pwd)"
CODEX_NEW_GAME="$HOME/.agents/skills/roblox-new-game"
CLAUDE_NEW_GAME="$HOME/.claude/skills/roblox-new-game"

mkdir -p "$CODEX_NEW_GAME/agents" "$CLAUDE_NEW_GAME"
cp -R "$HARNESS_ROOT/shared/skills/roblox-new-game/." "$CODEX_NEW_GAME/"
cp "$HARNESS_ROOT/openai/skills/roblox-new-game/agents/openai.yaml" "$CODEX_NEW_GAME/agents/openai.yaml"
cp -R "$HARNESS_ROOT/shared/skills/roblox-new-game/." "$CLAUDE_NEW_GAME/"
python3 "$HARNESS_ROOT/openai/setup/math_tool.py" --install
```

Codex reads user skills from `$HOME/.agents/skills`. Claude Code reads user
skills from `$HOME/.claude/skills`. Restart the host if it does not detect the
new skills.

Do not install `roblox-writer` at user scope. The scaffold or relinker installs
it into the managed project.

### Windows

Run these commands in PowerShell from the harness checkout:

```powershell
$HarnessRoot = (Get-Location).Path
$CodexNewGame = Join-Path $env:USERPROFILE ".agents\skills\roblox-new-game"
$ClaudeNewGame = Join-Path $env:USERPROFILE ".claude\skills\roblox-new-game"

New-Item -ItemType Directory -Force (Join-Path $CodexNewGame "agents"), $ClaudeNewGame | Out-Null
Copy-Item (Join-Path $HarnessRoot "shared\skills\roblox-new-game\*") $CodexNewGame -Recurse -Force
Copy-Item (Join-Path $HarnessRoot "openai\skills\roblox-new-game\agents\openai.yaml") (Join-Path $CodexNewGame "agents\openai.yaml") -Force
Copy-Item (Join-Path $HarnessRoot "shared\skills\roblox-new-game\*") $ClaudeNewGame -Recurse -Force
py -3 (Join-Path $HarnessRoot "openai\setup\math_tool.py") --install
```

For a managed project on Windows, run `.roblox-harness\setup_windows.bat` from
the project root after the submodule is initialized.

## Create a game

Start a new host session and request the user skill:

```text
Use $roblox-new-game to create a new Roblox game.
```

The skill completes the interview before it changes the destination. It then
asks for explicit consent to install the harness. After consent, it creates or
uses the project Git root, creates the empty `.roblox` marker, adds the
`.roblox-harness` submodule, and relinks the project integration. The user must
trust the project, review changed hooks, select the Roblox permission profile,
and allow the current session to pass `SessionStart` before the skill records
the interview or emits files.

The scaffold creates one Argon project per place. It also creates the shared
and place-specific source trees, the confirmed Service and Controller modules,
the project instructions, the host hooks, the review-agent definitions, and
the prescribed package and service templates.

## Example `roblox-new-game` interview

```text
Agent: What are players doing in the current test?

User: Players leave a lobby, enter a timed ruin, collect relics, and return to
the lobby to bank them.

Agent: Which places should exist now? For this loop, an example is
`Lobby, Ruin`.

User: Use `Lobby, Ruin`.

Agent: Which shared and place-scoped Services should exist? For this loop, an
example is `shared: RelicInventory; Ruin: ExpeditionRound`. PlayerData,
Payments, Updates, and Effects already ship with the harness.

User: Use `shared: RelicInventory; Ruin: ExpeditionRound`.

Agent: Which shared and place-scoped Controllers should exist? For this loop,
an example is `shared: RelicHud; Ruin: RelicInteraction`. Effects, Gui, and
Updates already ship with the harness.

User: Use `shared: RelicHud; Ruin: RelicInteraction`.

Agent: What project name and destination directory should I use?

User: Use `RelicRun` in `/path/to/RelicRun`.

Agent: Do you want to install rblx-harness? This will install it from
https://github.com/lennyRBLX/rblx-harness.git into /path/to/RelicRun,
initialize Git when needed, and install its hooks, gates, and rules. [y/N]

User: Yes.
```

After project authorization succeeds, the skill records each confirmed
file-shaping answer and emits the `RelicRun` scaffold. The gameplay-loop text
is proposal context only. It is not stored as a project constraint.

## Existing managed projects

Initialize the harness after you clone a managed project:

```bash
git submodule update --init --recursive -- .roblox-harness
python3 .roblox-harness/openai/setup/permissions_harness.py --relink
```

Run the project check from the managed project root:

```bash
python3 .roblox-harness/tools/project_gate/project_gate.py --project-root "$(pwd)"
```
