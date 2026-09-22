# Roblox agent delegation

Use the Agent tool to launch the named Roblox specialist as a separate subagent
without waiting for the user to ask. Never perform a specialist role inline in
the primary session or substitute the primary session's analysis for its result.
When a role below applies, launch that role's configured subagent and pass exact
paths, APIs, known evidence, and open questions:

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
other work meanwhile. Keep work that does not match a specialist role, such as
single lookups, straightforward edits, Studio probes, and user decisions, in the
primary session. Report subagent conclusions with their sources and limits.
