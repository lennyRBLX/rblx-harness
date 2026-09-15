# rblx-harness

Roblox workflows for Codex and Claude Code: six skills, four optional specialist
agents, one command interface, project scaffolding, and reusable Luau packages.

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

Setup creates ignored skill links and agent definitions for both hosts:
`.agents/skills` and `.codex/agents` for Codex, `.claude/skills` and `.claude/agents`
for Claude Code. Generated projects also receive `.roblox`, selected asset links,
and project instructions in `AGENTS.md`, imported by `CLAUDE.md`. Serena manages its own `.serena` directory. Python 3.11+ is required;
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

## Claude Code integration

| Concern | Implementation |
|---|---|
| Skill discovery | `.claude/skills/*/SKILL.md` links to the same `shared/skills` sources |
| Project context | `CLAUDE.md` imports `AGENTS.md` through a managed `@AGENTS.md` block |
| Tools | Native search/edit/Git plus `tools/harness.py` for domain operations |
| Agents | `.claude/agents/*.md` from `anthropic/agents`; inherited model, `Agent` denied so roles cannot delegate, write tools denied for read-only roles |
| Settings | Absent `env` defaults merged into `.claude/settings.json`: `MAX_MCP_OUTPUT_TOKENS=6000`, `BASH_MAX_OUTPUT_LENGTH=24000` characters |
| Hooks | None installed; `anthropic/hooks/adapter.py` identifies retired handlers |

These use official [subagents](https://code.claude.com/docs/en/sub-agents),
[settings](https://code.claude.com/docs/en/settings),
[environment variables](https://code.claude.com/docs/en/env-vars),
[CLAUDE.md imports](https://code.claude.com/docs/en/memory),
[skills](https://code.claude.com/docs/en/skills),
[hooks](https://code.claude.com/docs/en/hooks), and
[sandboxing](https://code.claude.com/docs/en/sandboxing). Claude Code has no
per-agent sandbox or named permission profile: read-only roles lose write tools,
while their Bash use stays read-only by instruction. Sandboxed commands cannot
write `.claude` or `.git` hooks/config, so run setup outside the sandbox.

## Migration

Setup removes only recognized legacy harness hook handlers and updates its four
agent files. It preserves unrelated agents, hooks, custom config values, and
instructions outside its managed block. An exact legacy generated `AGENTS.md`
is migrated; customized content is retained. Mapped place IDs survive relinking.
`templates/AGENTS.legacy` is migration input, not active context.

For Claude Code, setup removes only the exact `python3` handlers earlier releases
wrote into `.claude/settings.json` for `claude/hooks/adapter.py` and
`shared/gates/harness_gate.py`; those scripts no longer exist and would block tool
use. Other values from those releases, such as `env` or `permissions.deny`, are
treated as user configuration and retained. An existing `CLAUDE.md` keeps its text;
the import is added only when no `@AGENTS.md` line is present.

No automatic harness hooks, format retries, mandatory agent chains, milestone
receipts, or text-substitution compressor remain. The adapter is retained as a
no-op for already running clients. Skills keep detailed references on demand;
each host manages compaction. An optional handoff template remains in `shared/HANDOFF.md`.
Existing model and permission preferences remain in user/project configuration.
The optional Roblox permission profile can be installed with
`python3 openai/setup/permissions_harness.py --install`; setup does not select it.
For Claude Code, `python3 anthropic/setup/permissions_harness.py --install` writes
`~/.claude/rblx-harness-roblox.json` (or under `CLAUDE_CONFIG_DIR`); select it per
session with `claude --settings ~/.claude/rblx-harness-roblox.json`.

## Tools and checks

```sh
python3 tools/harness.py --help
python3 tools/harness.py check harness
python3 tools/harness.py check harness --case "native Codex"
python3 tools/harness.py check harness --case "Claude"
```

For project commands, use `python3 rblx-harness/tools/harness.py` from the project
root, or put `--root PROJECT` before the command family. See [tool details](shared/TOOLS.md).
Single commands replace the dispatcher process. Batched checks deduplicate selected
checkers and files. Required failures retain nonzero exit status. Studio execution
is explicit. Existing backend scripts remain available for compatibility.

For model selection, load the [evaluation guide](shared/skills/rblx-writer/references/models.md).
