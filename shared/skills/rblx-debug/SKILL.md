---
name: rblx-debug
description: Diagnose and fix a Roblox bug through human-selected Studio or live tests, then optimize, review, verify, and remove temporary diagnostics. Use when a bug needs fixing or its cause is not yet known.
---

# rblx-debug

Resolve `<HARNESS_ROOT>` from the project's `rblx-harness` submodule. Read
`<HARNESS_ROOT>/shared/CORE.md` before work.

Follow this sequence:

1. Treat a prompt about a bug to fix or an unexplained bug as the trigger for
   this skill.
2. Run the `researcher` agent for relevant Roblox documentation and project
   facts.
3. Write a focused test or diagnostic with the `debugger` agent. Continue the
   writer-debugger exchange until the test is ready.
4. Ask the human whether to run it in Studio or live. Wait for the human to
   test and report the cause.
5. Write the solution with the `debugger` agent's evidence.
6. Wait for the human to test and confirm that the bug is fixed.
7. Run the `optimizer` agent on the fix.
8. Apply the optimizer's issues.
9. Run the `reviewer` agent on the optimized fix.
10. Apply the reviewer's issues.
11. Wait for the human to test again and confirm that the optimized result is
   still fixed.
12. Delete every temporary test and debugging change created by this session.

The human controls the Studio-or-live choice and each test result. Do not infer
a pass. Keep diagnostic code disabled by default and scoped to the selected
place. Do not delete pre-existing tests or diagnostics.

Use the data and type tools for any data-shape or public-type change. New data
fields do not require a separate human review gate.

## Knowledge — conditional behavior investigation

For engine access, Workspace timing, modules, or lifecycle questions, load
`shared/skills/rblx-writer/SKILL.md` regions **Knowledge — conditional engine
evidence** and **Constraints — conditional engine operations**. Query the
same canonical `access` and `behavior` records before selecting a probe.
Classify a gap as missing source, lost tool output, retrieval failure, or
ambiguous engine behavior. Test only the remaining question. Community reports
are leads; prefer engine documentation, engineer-confirmed fixes, or reproduction.

## Constraints — scenario controlled engine probes

Trigger: documentation leaves a development-relevant engine question unresolved.
Use a disposable place. The human selects Studio or live and reports each result
[TEST1]. Stage disabled fixtures with the boilerplate tool and author all source
in stopped Edit. Assign exact paths and cleanup ownership; preserve other edits.
Discover studios/datamodels and supply `studio_id` and `datamodel_type` on every
MCP execution. Serialize writes to one datamodel. Record Studio build, MCP version
or executable identity, source revisions, place settings, RunContext/location,
caller, and serial/parallel phase; unavailable values remain unknown.

For each case retain operation, before, requested value, after, exact error,
observed effect, other-process observation, restart requirement, restoration and
human report. Separate successful assignment from effect, persistence and
replication. Never mark unrun cells passed. A failed test may expose a fixture
defect rather than an engine limit. Validate preconditions before mutation;
failed preflight must not trigger cleanup writes. Track whether each owned
mutation began and restore only affected values, including on errors. Stop the
case if restoration fails. After stopping, remove only owned temporary
fixtures. Retain useful regression tests.

Diagnostic reads also need access checks. Workspace.SignalBehavior is
NotScriptable and cannot be assumed readable or configurable through XML;
record the human-observed editor setting separately from the exact event's
measured dispatch. A callback observation does not establish the configured
setting or the Default mapping. Keep calibration scoped to that event and run. Validate a service result before
calling it: a successful pcall can return nil, and a later nil-index error is a
test defect, not evidence that the requested method rejected access. Keep output
bounded; if console or log truncation occurs, retain full records in owned
non-code runtime values and retrieve them before Play teardown.

For paired writes and observers, acknowledge the write before sampling and
acknowledge sampling completion before restoration. Use bounded deadlines and
restore on errors. Keep writer readbacks separate from observer reads; a protocol
acknowledgement does not establish replicated-property arrival.

For Workspace, read the member's behavior record: test a documented runtime
Gravity write with a controlled falling part and separate process observations;
configure documented streaming settings before a fresh Play. PluginSecurity
alone does not establish startup-only behavior. Do not toggle StreamingEnabled
during a production Play test. Read and write denials are separate evidence.

For modules, query `behavior modules`. Compare repeated require identity in the
same caller environment, then separate server/client/MCP callers. While stopped,
compare the same instance after a source edit with a destroyed/recreated owned
instance, retaining old references as a separate observation. A fresh Play is a
different case and must not mask the replacement result. MCP cache lifetime
remains unknown until that exact context has evidence. These are project test
procedures; recheck them against the current operational sources and versions.
