## Roblox work

- Use Argon-resolved source for project behavior. Validate remote arguments and
  ownership before mutation; release connections, tasks, and instances at teardown.
- Use `python3 rblx-harness/tools/harness.py types write` for data defaults,
  generated owner types, and public declarations. It validates and commits related
  files together. Resolve changed public APIs with `types read`.
- Before relying on engine access or behavior, read the selected skill's engine
  reference and query `api`. Keep caller, phase, restrictions, and source revision.
- Use native search, file editing, and Git tools. Use harness helpers when they
  supply domain validation, batched evidence, or reusable artifacts. Read
  `rblx-harness/shared/TOOLS.md` only for the needed command family.
- For Studio checks, use the user's selected environment and existing execution
  authorization. Otherwise obtain the human result. Keep authored source changes
  in stopped Edit mode; report passed, failed, unrun, and skipped checks accurately.
- Run the smallest check that resolves an acceptance condition or material risk.
  Reuse conclusive results until relevant source, input, or environment changes.
  Review or completion alone does not require another run.
- Pass exact paths, APIs, literals, restrictions, and unresolved questions. Load
  missing references after compaction; preserve known evidence and its scope.
