Read `rblx-harness/shared/CORE.md` before Roblox work.
Use the shared compaction handoff at `rblx-harness/shared/HANDOFF.md`; do not
create a project-local `HANDOFF.md`.

Use `$rblx-writer` for feature code, `$rblx-debug` for bugs, and
`$rblx-optimize` for MicroProfiler-led work. Use only the researcher,
optimizer, reviewer, and debugger agents.

Project hooks enforce agent boundaries, agent tool use, and rule adherence.
They do not authorize sessions or require a session restart. The optional
Roblox permission profile and Full Access are both supported.

The `plugins/` directory is optional. Its absence is valid.

## project

{{SUMMARY}}

## places

{{PLACES}}

## harness assets

{{ASSETS}}
