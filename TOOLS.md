# Tools

Command reference for `tools/` and the [harness CLI](shared/TOOLS.md).

## Conventions

`*` · R · command notation.

| Token | Meaning |
|---|---|
| `R` / `S` / `N` | Local files / Studio / network |
| `H` | Harness checkout root |
| `…` | Repeat the command prefix |
| `<value>` / `[value]` | Required / optional |

## cargo-clean

`tools/cargo-clean.sh` · R / N · Run Cargo and clean build artifacts.

| Cmd | Effect |
|---|---|
| `H/tools/cargo-clean.sh install --path . --locked` | Install `harness` |
| `… run -- check harness --case <match>` | Run matching harness checks |
| `… <cargo args>` | Run Cargo from the harness root |

- Cleans on success and failure. Honors `CARGO_TARGET_DIR` and `--target-dir`.

## harness

`src/` · R / S / N · Set up, inspect, and check Roblox projects.

| Cmd | Effect |
|---|---|
| `harness --help` | List command families |
| `harness setup --harness` | Initialize this checkout |
| `harness setup --project . --from-state` | Set up a project from `manifest.json` |
| `harness [--root <project>] <family> --help` | Show family options |

- [Command reference](shared/TOOLS.md) covers workflows, flags, and limits.
