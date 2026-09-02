---
name: rblx-new-game
description: Inspect, interview, and scaffold a new or existing multi-place Roblox project. Use for project creation or adoption, including optional rblx-harness assets and plugin support; do not use for feature work.
---

# rblx-new-game

Use the current working directory as the project root. Do not ask for another
path or project name. Resolve `<SKILL_DIR>` as this skill directory.

Before the interview, read [references/interview.md](references/interview.md)
and run:

```bash
python3 <SKILL_DIR>/scripts/scaffold.py inspect --root <project-root>
```

Use the inspection result to decide whether this is a new or existing project
and to identify existing places, Services, Controllers, their shared or
place-specific scope, Git state, and plugin support. Do not modify the project
during inspection.

## Interview

Accept explicit answers already present in the user's request. Ask only for
missing or contradictory answers. Use the static opening text in the interview
reference and append a project-specific proposal where that reference permits
one. A proposal must remain open to revision.

Use this order:

1. Gameplay loop. Ask even when Services or Controllers already exist. Propose
   a concise repeatable action, result or reward, and restart or continuation.
2. Places. Always retain a multi-place layout, including when there is one
   place. Propose places from the gameplay loop and inspection.
3. Services and Controllers. Propose every detected module first, preserving
   its inferred scope, then add modules justified by the gameplay loop. If none
   exist, the user must name the shared and place-specific modules to create.
4. Harness assets. Ask independently for packages, services, controllers, and
   plugin support. `all` accepts all four. An existing `plugins/` directory
   keeps plugin support without another decision.
5. Harness use. Ask whether the project should use rblx-harness. The optional
   Roblox permission profile is not part of this decision. Full Access is
   supported.

Record each accepted field separately:

```bash
python3 <SKILL_DIR>/scripts/scaffold.py answer gameplay "<answer>" --root <project-root>
python3 <SKILL_DIR>/scripts/scaffold.py answer places "<answer>" --root <project-root>
python3 <SKILL_DIR>/scripts/scaffold.py answer services "<answer>" --root <project-root>
python3 <SKILL_DIR>/scripts/scaffold.py answer controllers "<answer>" --root <project-root>
python3 <SKILL_DIR>/scripts/scaffold.py answer assets "<answer>" --root <project-root>
python3 <SKILL_DIR>/scripts/scaffold.py answer harness "<yes-or-no>" --root <project-root>
```

Use `shared: Name, Name; Place: Name` for Services and Controllers. Use `none`
when the confirmed set is empty. Use safe names that begin with a letter and
contain only letters or digits.

Packages, harness Services, and harness Controllers require harness use. If the
user selects those assets and declines the harness, ask them to revise one of
the two answers. Plugin support can exist without the harness.

## Scaffold

When harness use is accepted, run:

```bash
python3 <SKILL_DIR>/scripts/dependency.py setup --root <project-root> --yes
```

After explicit harness approval, the dependency tool runs the equivalent of:

```bash
git submodule add https://github.com/lennyRBLX/rblx-harness.git
```

Git checks out the repository at `rblx-harness/`, records the public URL in
`.gitmodules`, and stages that file plus the pinned submodule gitlink. Do not
replace this with a symlink, nested clone, alternate URL, or hidden dependency
directory. The command preserves an existing Git repository and never requires
the Roblox permission profile.

After cloning a scaffolded project without recursive submodules, initialize
the pinned harness checkout with:

```bash
python3 <SKILL_DIR>/scripts/dependency.py init --root <project-root>
```

Then run:

```bash
python3 <SKILL_DIR>/scripts/scaffold.py emit --root <project-root>
```

The emitter creates one Argon project per place, shared and place-specific
source trees, confirmed boilerplate, AGENTS.md, Codex agents, three project
workflow skills, and only the three lean hook events. It calls the
cross-platform Python setup script to symlink accepted harness packages,
Services, and Controllers on macOS, Linux, and Windows. `rblx-new-game` remains
a bootstrap skill and is not installed into the generated project's
`.agents/skills/`. Existing detected Service and Controller bytes overwrite
generated boilerplate at their confirmed destination, even when their
formatting differs.

Create `plugins/` only when accepted or already present. Its absence is valid
and must not fail setup or validation.

Do not create project `HANDOFF.md`. Use the single static compaction handoff at
`rblx-harness/shared/HANDOFF.md`.

The generated `.agents/`, `.codex/`, and `.roblox` paths are local runtime
state and must remain ignored. `.codex/` is required at runtime because Codex
discovers project configuration, agents, and hooks from the project root; the
submodule alone does not replace it. Serena owns `.serena/`, which is also
ignored and is created only when Serena initializes the project.

Do not request a session restart. Report the emitted places and preserved
modules when the command succeeds.

## Relink

For an existing harness project, restore Codex support and asset links with:

```bash
python3 rblx-harness/setup_project.py --project <project-root> --from-state
```

This command also recreates the ignored `.roblox` marker and removes any stale
project-local `rblx-new-game` skill install.
