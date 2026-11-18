# Harness maintenance

@TOOLS.md

Edit native code in `src/` and canonical assets or tests in `shared/`, `tools/`,
`tests/`, `openai/`, and `anthropic/`. `harness setup --harness` generates
`.agents/`, `.codex/`, and `.claude/`.

Use native Codex and Claude Code configuration and skill discovery. Keep project
instructions short. Put task details in skill references. Preserve unrelated user
configuration during setup.

Apply the shared [command, check, and evidence rules](shared/CORE.md),
[Writing](shared/CORE.md#writing), [Tools](shared/CORE.md#tools), and
[Modules](shared/CORE.md#modules) rules.

Use `./tools/cargo-clean.sh` for builds, installs, runs, and checks. It cleans on
success and failure. Use `install` when the executable must persist.

List commands with `harness --help` or `./tools/cargo-clean.sh run -- --help`.
Run `./tools/cargo-clean.sh run -- check harness --case MATCH` for affected
behavior. Use the full suite for broad harness changes. Package source is a
supplied asset. Harness configuration checks run outside Studio.
