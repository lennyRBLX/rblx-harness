---
name: rblx-new-game
description: Inspect and scaffold new or existing multi-place Roblox projects with optional harness assets and plugin support. Use for project setup, not feature work.
---

# Roblox project setup

Let `ROOT` be cwd and `SKILL` this skill's resolved directory.

1. Inspect without edits: `python3 SKILL/scripts/scaffold.py inspect --root ROOT`.
2. Resolve gameplay loop, places, shared/place Services and Controllers, assets, and harness choice. Reuse answers and authorization; ask only about gaps or conflicts. See [interview.md](references/interview.md).
3. Record accepted fields with `python3 SKILL/scripts/scaffold.py answer FIELD VALUE --root ROOT`. Fields: `gameplay`, `places`, `services`, `controllers`, `assets`, `harness`.
4. Once harness use is authorized, run `python3 SKILL/scripts/dependency.py setup --root ROOT --yes`. It adds the fixed public Git submodule and stages `.gitmodules` and its gitlink. For an existing clone missing the checkout, use `dependency.py init --root ROOT`.
5. Run `python3 SKILL/scripts/scaffold.py emit --root ROOT`. On integration failure, keep state and retry only `python3 ROOT/rblx-harness/setup_project.py --project ROOT --from-state`.

Keep a multi-place layout even for one place. Service/Controller answers use `shared: Name, Name; Place: Name` or `none`. New names: bare PascalCase nouns, letters/digits only, starting with a letter; omit Service/Controller suffixes. Propose detected modules before additions. Exclude detected harness assets from module proposals; asset selection supplies them.

Assets: packages, services, controllers, plugins; `all` selects all four. Packages/services/controllers need the harness; plugins may stand alone. Keep existing `plugins/`. Detected module bytes replace boilerplate at accepted destinations. Keep confirmed choices in root `manifest.json`.

Setup installs five project skills, four agents, selected asset links, and project instructions. Bootstrap `rblx-new-game` stays outside generated project skills. Keep generated `.agents/`, `.codex/`, `.roblox`, and Serena-owned `.serena/` ignored. Codex manages context loading and compaction; install no harness hooks. Preserve project docs and unrelated user configuration.
