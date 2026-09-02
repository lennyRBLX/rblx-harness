# rblx-harness

`rblx-harness` supplies Codex workflows for Roblox code writing, debugging,
optimization, and multi-place project scaffolding.

## Included surface

- Skills: `rblx-new-game`, `rblx-writer`, `rblx-debug`, `rblx-optimize`.
- Agents: `researcher`, `optimizer`, `reviewer`, `debugger`.
- Tools: Roblox API and Creator Docs lookup, data and type writers, Git repair,
  MicroProfiler analysis, boilerplate generation, and style assessment.
- Rules: `shared/CORE.md`.
- Codex support: reproducible project agent definitions, project skills, and
  three lean hook events.
- Templates: shared Packages, short project `README.md`, project `AGENTS.md`,
  and one shared `shared/HANDOFF.md`.
- Token compression: bounded agent records and `token_shrink.py`.
- Plugin support: an optional project `plugins/` directory.

Claude support is not included.

## Set up a harness checkout

After cloning `rblx-harness` itself, rebuild its ignored Codex support and
repository skill links with:

```bash
python3 setup_project.py --harness
```

This installs all four harness skills for harness development. It does not
create `.roblox` or `.serena/`.

## Permissions

The Roblox permission profile remains available, but it is optional. Full
Access is also supported. No gate requires profile selection.

Install the optional profile with:

```bash
python3 openai/setup/permissions_harness.py --install
```

The harness does not authorize sessions and does not force session restarts.

## Install rblx-new-game locally

Link the skill into the Codex skill directory. After explicit harness
approval, the linked skill installs
`https://github.com/lennyRBLX/rblx-harness.git` as the `rblx-harness` Git
submodule.

```bash
python3 -c 'import os,pathlib; r=pathlib.Path.cwd(); d=pathlib.Path.home()/".agents/skills/rblx-new-game"; d.parent.mkdir(parents=True,exist_ok=True); d.unlink(missing_ok=True); os.symlink(r/"shared/skills/rblx-new-game",d,target_is_directory=True)'
```

Run `$rblx-new-game` from the target project directory.

`rblx-new-game` is a bootstrap skill. It is not installed into the generated
project's `.agents/skills/` directory.

## rblx-new-game flow

1. Inspect the current folder and identify existing places, Services,
   Controllers, and shared or place-specific scope.
2. Confirm the gameplay loop.
3. Confirm the places. The layout always supports multiple places.
4. Confirm shared and place-specific Services and Controllers.
5. Select harness packages, Services, Controllers, and plugin support.
6. Confirm whether the project uses rblx-harness.
7. Scaffold the project.

The scaffolder preserves an existing Git repository. Existing detected Service
and Controller bytes replace generated boilerplate at their confirmed
destination. It creates and stages `.gitmodules` and the `rblx-harness`
gitlink. Clone generated projects with `--recurse-submodules`, or initialize a
normal clone with `git submodule update --init --recursive`.

`setup_project.py` replaces the former Windows batch setup. It creates relative
file symlinks for accepted harness Packages, Services, and Controllers on
Windows, Linux, and macOS. Shared links are mounted by every generated place;
place-specific source remains under `places/<Place>/`. The optional `plugins/`
directory is created only when selected or already present.

## Generated local state

The submodule contains the tracked source for Codex support, but Codex discovers
project configuration, agents, hooks, and repository skills only from the
project root. Run setup after cloning:

```bash
git submodule update --init --recursive
python3 rblx-harness/setup_project.py --project "$(pwd)" --from-state
```

Setup recreates the ignored `.roblox` marker, `.codex/`, and the
`.agents/skills/` links for `rblx-writer`, `rblx-debug`, and `rblx-optimize`.
Serena creates `.serena/` when it is initialized. All four paths are ignored
and must not be committed. Project `HANDOFF.md` is not generated; every harness
project uses `rblx-harness/shared/HANDOFF.md`.

## Hooks and gates

Generated projects install only:

- `PreToolUse` for agent tool boundaries and mechanical rule checks.
- `SubagentStart` for the four allowed agent roles and rule context.
- `SubagentStop` for compact, role-specific returns.

These hooks do not gate the primary `rblx-writer`, `rblx-debug`,
`rblx-optimize`, or `rblx-new-game` session flow.

## Relink and validate

```bash
python3 rblx-harness/setup_project.py --project "$(pwd)" --from-state
python3 rblx-harness/tools/project_gate/project_gate.py --project-root "$(pwd)"
```

Validate this harness checkout with:

```bash
python3 tools/tests/run_verify.py
```
