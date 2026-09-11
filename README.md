# rblx-harness

Roblox workflows for Codex: six skills, four optional specialist agents, one
command interface, project scaffolding, and reusable Luau packages.

## Setup

For this checkout:

```sh
python3 setup_project.py --harness
```

For an existing harness project:

```sh
git submodule update --init --recursive
python3 rblx-harness/setup_project.py --project . --from-state
```

Setup creates ignored `.agents/skills` links and `.codex/agents` definitions.
Generated projects also receive `.roblox`, selected asset links, and project
instructions. Serena manages its own `.serena` directory. Python 3.11+ is required;
asset linking requires symlink support. The bundled toolchain downloader currently
supports Apple Silicon macOS; other hosts must supply compatible tool binaries.

For a new project, link `shared/skills/rblx-new-game` into
`~/.agents/skills/rblx-new-game`, then invoke `$rblx-new-game` in that project.
It records choices in `manifest.json` and installs the approved Git submodule from
`https://github.com/lennyRBLX/rblx-harness.git`. Packages, Services, Controllers,
and `plugins/` support are selectable. Existing detected module bytes are preserved.

## Codex integration

| Concern | Implementation |
|---|---|
| Skill discovery | `.agents/skills/*/SKILL.md`, YAML name/description, optional `agents/openai.yaml` |
| Project context | Root `AGENTS.md`; conditional knowledge in skill references |
| Tools | Native search/edit/Git plus `tools/harness.py` for domain operations |
| Agents | `.codex/agents/*.toml`; inherited model settings, role sandbox defaults, nested delegation disabled |
| Validation | Checks inside transactional writers; explicitly selected source/project/harness checks |
| Context size | Progressive disclosure, bounded artifacts, native compaction, 6,000-token tool-history default |

These use official [skills](https://learn.chatgpt.com/docs/build-skills),
[project instructions](https://learn.chatgpt.com/docs/agent-configuration/agents-md),
[subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents), and
[configuration](https://learn.chatgpt.com/docs/config-file/config-reference).
Descriptions and instructions express tool preferences. There is no Codex CLI
`tool_choice` setting that forces every source edit through a script. Native
[rules](https://learn.chatgpt.com/docs/agent-configuration/rules) govern command
prefixes; [MCP allowlists](https://learn.chatgpt.com/docs/extend/mcp) limit tools on
configured servers. Neither proves data semantics. Writer checks enforce their
own invariants. Parent runtime permission overrides can supersede role defaults.

## Migration

Setup removes only recognized legacy harness hook handlers and updates its four
agent files. It preserves unrelated agents, hooks, custom config values, and
instructions outside its managed block. An exact legacy generated `AGENTS.md`
is migrated; customized content is retained. Mapped place IDs survive relinking.
`templates/AGENTS.legacy` is migration input, not active context.

No automatic harness hooks, format retries, mandatory agent chains, milestone
receipts, or text-substitution compressor remain. The adapter is retained as a
no-op for already running clients. Skills keep detailed references on demand;
Codex manages compaction. An optional handoff template remains in `shared/HANDOFF.md`.
Existing model and permission preferences remain in user/project configuration.
The optional Roblox permission profile can be installed with
`python3 openai/setup/permissions_harness.py --install`; setup does not select it.

## Tools and checks

```sh
python3 tools/harness.py --help
python3 tools/harness.py check harness
python3 tools/harness.py check harness --case "native Codex"
```

For project commands, use `python3 rblx-harness/tools/harness.py` from the project
root, or put `--root PROJECT` before the command family. See [tool details](shared/TOOLS.md).
Single commands replace the dispatcher process. Batched checks deduplicate selected
checkers and files. Required failures retain nonzero exit status. Studio execution
is explicit. Existing backend scripts remain available for compatibility.

For model selection, load the [evaluation guide](shared/skills/rblx-writer/references/models.md).
