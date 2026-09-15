# Roblox agent delegation

This project requests delegation to its Roblox agents. Use the Agent tool without
waiting for the user to ask, and pass exact paths, APIs, known evidence, and open
questions:

- `researcher`: engine API, access, or behavior questions and project-source
  tracing that need several lookups, docs, or files.
- `debugger`: failures whose cause the supplied source or logs do not establish.
- `optimizer`: MicroProfiler captures and frame-time or memory questions.
- `reviewer`: non-trivial Luau changes, before reporting them complete.

Launch independent agents together and continue other work meanwhile. Keep single
lookups, straightforward edits, Studio probes, and user decisions in the primary
session. Report agent conclusions with their sources and limits.
