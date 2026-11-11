# rblx-harness

Set up this repository for Codex and Claude Code. Rust 1.82+ and Cargo, plus
symlink support, are required.

## This checkout

Install the command from the repository root, then initialize this checkout:

```sh
./tools/cargo-clean.sh install --path . --locked
harness setup --harness
```

The command installs skills and agents for both hosts. Codex uses `.agents/skills`,
`.codex/agents`, and `AGENTS.md`. Claude Code uses `.claude/skills`,
`.claude/agents`, and `CLAUDE.md`, which imports `AGENTS.md`.

Both setup modes download pinned Lute 1.0.0, Argon 2.0.29, and Luau LSP 1.70.1
release binaries into `tools/bin`, verifying each archive's SHA-256 before
installation. Downloads require network access. Automatic binaries are available
for macOS arm64, Linux arm64/x86_64, and Windows x86_64; unsupported targets use
matching tools already on `PATH`.

## Existing project

From a project root with this repository at `rblx-harness` and a `manifest.json`,
run:

```sh
rblx-harness/tools/cargo-clean.sh install --path . --locked
harness setup --project . --from-state
```

This installs the same Codex and Claude Code support in the project.

## Build cleanup

Use `./tools/cargo-clean.sh` instead of `cargo` for this checkout, for example
`./tools/cargo-clean.sh build` or `./tools/cargo-clean.sh run -- check harness`.
The wrapper runs from the repository root and automatically runs `cargo clean`
after the command finishes, including failures. It respects `CARGO_TARGET_DIR`
and `--target-dir`. Installed executables remain available; binaries and caches
under the build directory are removed, so subsequent builds recompile.
Direct `cargo` commands bypass this wrapper and do not automatically clean.
