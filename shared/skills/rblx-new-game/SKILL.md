---
name: rblx-new-game
description: Inspect and scaffold new or existing multi-place Roblox projects with optional harness assets and plugin support. Use for project setup, not feature work.
---

# Roblox project setup

Use cwd as `ROOT` and this skill's resolved directory as `SKILL`.

1. Inspect without edits: `python3 SKILL/scripts/scaffold.py inspect --root ROOT`.
2. Resolve the gameplay loop, places, shared/place Services and Controllers,
   assets, and harness choice. Reuse existing answers and explicit authorization;
   ask only for missing or conflicting choices. See [interview.md](references/interview.md).
3. Record accepted fields with `python3 SKILL/scripts/scaffold.py answer FIELD VALUE --root ROOT`.
   Fields: `gameplay`, `places`, `services`, `controllers`, `assets`, `harness`.
4. With harness use authorized, run `python3 SKILL/scripts/dependency.py setup --root ROOT --yes`.
   This adds the fixed public Git submodule and stages `.gitmodules` and its gitlink.
   Use `dependency.py init --root ROOT` for an existing clone missing its checkout.
5. Run `python3 SKILL/scripts/scaffold.py emit --root ROOT`. On integration failure,
   retain state and retry only `python3 ROOT/rblx-harness/setup_project.py --project ROOT --from-state`.

Keep a multi-place layout even with one place. Service/Controller answers use
`shared: Name, Name; Place: Name`, or `none`. New names are bare PascalCase nouns,
letters/digits only, starting with a letter; omit Service/Controller suffixes.
Propose detected modules before additions. Exclude detected harness assets from
module proposals; asset selection supplies them.

Assets are packages, services, controllers, and plugins; `all` selects all four.
Packages/services/controllers require the harness; plugins can stand alone.
Retain an existing `plugins/` directory. Detected module bytes replace boilerplate
at accepted destinations. Confirmed choices remain in root `manifest.json`.

Setup installs five project skills, four agents, selected asset links, and project
instructions. Bootstrap `rblx-new-game` stays outside generated project skills.
Keep generated `.agents/`, `.codex/`, `.roblox`, and Serena-owned `.serena/` ignored.
Codex handles context loading and compaction; no harness hook installation is needed.
Preserve existing project documentation and unrelated user configuration.
