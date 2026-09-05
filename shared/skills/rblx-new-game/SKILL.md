---
name: rblx-new-game
description: Inspect, interview & scaffold new/existing multi-place Roblox projects with optional harness assets/plugins. Excludes feature work.
---

Use cwd as `<ROOT>` & this skill directory as `<SKILL_DIR>`.

1. Read [interview.md](references/interview.md); inspect without edits:
   `python3 <SKILL_DIR>/scripts/scaffold.py inspect --root <ROOT>`.
2. Interview in the order below. Reuse explicit answers; ask only missing/conflicting fields. Use exact reference openings & revisable project-specific proposals.
3. Record each accepted field separately:
   `python3 <SKILL_DIR>/scripts/scaffold.py answer <field> "<answer>" --root <ROOT>`.
   Fields: `gameplay`, `places`, `services`, `controllers`, `assets`, `harness`.

## Interview

1. **Gameplay:** Confirm even with existing modules. Propose repeatable action, reward/result & continuation/restart.
2. **Places:** Propose from gameplay & inspection; retain multi-place layout even for one place.
3. **Services/Controllers:** Propose every detected module first with inferred shared/place scope, then gameplay-driven additions. Exclude inspected `harness_assets` (including `PlayerData`/`Gui`); asset selection supplies them. If none exist, user must name shared/place modules. New names: bare PascalCase feature nouns, letters/digits only, starting with a letter; no `Service`/`Controller` suffix. Answer format: `shared: Name, Name; Place: Name`; `none` for a confirmed empty set.
4. **Assets:** Ask independently for packages, services, controllers & plugins; `all` selects four. Existing `plugins/` keeps support without another decision.
5. **Harness:** Confirm yes/no independently of optional Roblox permissions; Full Access is valid. Packages/services/controllers require harness; resolve conflicting answers. Plugins can stand alone.

## Scaffold

After explicit harness approval:

```sh
python3 <SKILL_DIR>/scripts/dependency.py setup --root <ROOT> --yes
```

This preserves existing Git & adds the public
`https://github.com/lennyRBLX/rblx-harness.git` submodule at `rblx-harness/`,
with staged `.gitmodules` & pinned gitlink. Use this dependency tool without
substitute links, clones or URLs; no permission profile required.

For a clone missing its pinned checkout:

```sh
python3 <SKILL_DIR>/scripts/dependency.py init --root <ROOT>
```

Then emit:

```sh
python3 <SKILL_DIR>/scripts/scaffold.py emit --root <ROOT>
```

Confirmed data belongs in root `manifest.json`. On `project integration failed`,
retain emitted files/state & retry only integration with the Relink command.
Do not rerun the pinned submodule's scaffolder; interview-state versions may differ.

Emission creates per-place Argon projects, shared/place source, confirmed
boilerplate, AGENTS.md, README, Codex agents, three workflow skills & three hook
events. Preserve existing README; new README includes gameplay & post-clone setup.
Detected Service/Controller bytes replace boilerplate at confirmed destinations,
including original formatting. Setup links accepted harness assets on
macOS/Linux/Windows. `plugins/` is optional: create only if accepted/already present;
absence must pass validation.

Keep `.agents/`, `.codex/`, `.roblox` & Serena-owned `.serena/` ignored. Root
`.codex/` is required for discovery; Serena alone initializes `.serena/`.
Use shared `rblx-harness/shared/HANDOFF.md`. Bootstrap `rblx-new-game` stays outside
generated project skills. No session restart; report emitted places & preserved modules.

## Relink

For existing projects or failed integration:

```sh
python3 <ROOT>/rblx-harness/setup_project.py --project <ROOT> --from-state
```

Restores Codex support, asset links & `.roblox`; removes stale project-local
`rblx-new-game` installs.
