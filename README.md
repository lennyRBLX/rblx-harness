# rblx-harness

Set up this repository for Codex and Claude Code. Python 3.11+ and symlink support
are required.

## This checkout

From the repository root, run:

```sh
python3 setup_project.py --harness
```

The command installs skills and agents for both hosts. Codex uses `.agents/skills`,
`.codex/agents`, and `AGENTS.md`. Claude Code uses `.claude/skills`,
`.claude/agents`, and `CLAUDE.md`, which imports `AGENTS.md`.

## Existing project

From a project root with this repository at `rblx-harness` and a `manifest.json`,
run:

```sh
git submodule update --init --recursive
python3 rblx-harness/setup_project.py --project . --from-state
```

This installs the same Codex and Claude Code support in the project.
