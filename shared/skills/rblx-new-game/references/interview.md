# Interview prompts

Use each opening exactly. Add only the proposal described after it.

1. Gameplay loop:

   `What actions do players repeat, what result or reward do they receive, and how does the loop continue or restart?`

   Add: `Proposed loop: <project-specific loop>. Keep this or revise it.`

2. Places:

   `Which places will exist? The scaffold always uses a multi-place layout.`

   Add: `Proposed places: <comma-separated names>. Keep these or revise them.`

3. Services and Controllers:

   `Which Services and Controllers should be shared, and which should be specific to one place?`

   Add two scoped proposals. List inspected modules before new proposals.
   Exclude names under `harness_assets` in the inspection report because the
   matching harness asset selection adds them automatically, including
   `PlayerData` and `Gui`. Give every new module a bare PascalCase feature name
   without a `Service` or `Controller` suffix:
   `Proposed Services: <scoped list>. Proposed Controllers: <scoped list>. Keep these or revise them.`

4. Harness assets:

   `Should this project use harness packages, harness Services, harness Controllers, or plugin support? Answer with any combination, all, or none.`

5. Harness use:

   `Should this project use rblx-harness? Answer Yes or No. The optional Roblox permission profile and Full Access are both supported.`
