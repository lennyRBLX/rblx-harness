# Roblox agent delegation

This project requests delegation to its Roblox agents. Use the Agent tool without
waiting for the user to ask, and pass exact paths, APIs, known evidence, and open
questions:

- `researcher`: engine API, access, or behavior questions and project-source
  tracing that need several lookups, docs, or files.
- `debugger`: failures whose cause the supplied source or logs do not establish.
- `optimizer`: source and plan costs, MicroProfiler captures, and frame-time or
  memory questions.
- `reviewer`: Luau changes and implementation plans, after optimizer assessment.

For non-GUI features, GUI features, bugs or regressions, and implementation plans,
prepare the implementation or plan, run `optimizer`, address its findings, then
run `reviewer` before completion. Source and plan assessment does not require a
capture. Pass optimizer findings and their disposition to reviewer.

Launch independent agents together; optimizer and reviewer run in order. Continue
other work meanwhile. Keep single
lookups, straightforward edits, Studio probes, and user decisions in the primary
session. Report agent conclusions with their sources and limits.
