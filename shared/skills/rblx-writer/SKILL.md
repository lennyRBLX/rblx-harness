---
name: rblx-writer
description: Implement Roblox Luau features through the researcher, optimizer, and reviewer sequence. Use for Roblox code-writing requests that are not bug investigations or MicroProfiler-led optimization.
---

# rblx-writer

Resolve `<HARNESS_ROOT>` from the project's `rblx-harness` submodule. Read
`<HARNESS_ROOT>/shared/CORE.md` before writing.

Follow this sequence:

1. Treat the feature-writing prompt as the trigger for this skill.
2. Run the `researcher` agent with the prompt, relevant project paths, and the
   exact Roblox or project facts needed. Wait for its response.
3. Use that response to write the requested output.
4. Run the `optimizer` agent on the complete output. Apply every relevant
   optimizer issue to the output.
5. Run the `reviewer` agent on the updated output. Apply every reviewer issue
   to the output.

Use `apply_patch` for source edits. Create new Service or Controller frames
with `tools/create_boilerplate/create_boilerplate.py`.

Data defaults, generated owner types, and public type declarations must be
changed with `tools/data_write/data_write.py` or
`tools/type_write/type_write.py`. Do not ask a human to approve a new data
field. Present human choices only when product behavior is genuinely
undecided.

Keep agent prompts bounded to the changed paths and compact their returned
evidence before carrying it forward. Do not dispatch agents outside
`researcher`, `optimizer`, and `reviewer` in this flow.

## Knowledge — conditional engine evidence

Trigger: code, commands, or tests depend on an engine member's access, timing,
replication, initialization, or cleanup. Use
`<HARNESS_ROOT>/tools/api_dump/api_dump.py access Class.Member`; class-only
`access Class` includes class restrictions. Use `inventory Workspace` for all
properties, including inherited and restricted members. Legacy lists are for
discovery; `--all` does not add access evidence to their old field format.

Read the named `behavior` route returned by access. For behavior questions use
`behavior` with an exact API or topic: `workspace`, `signals`, `replication`,
`physics`, `parallel`, `modules`, `persistence`, `assets`, `gui`, or `environment`.
These operational records are canonical: each carries its scope, action,
evidence, status, exceptions, and recheck condition. If a query misses, search
full Creator Docs and linked primary guides with the exact question. Report
an unresolved question and bounded next evidence action; do not infer a rule
from silence. Other skills and agents use these same records.

For automatic UI sizing, query `behavior gui` before changing AutomaticSize,
Size, CanvasSize or AutomaticCanvasSize. Keep minimum size, content bounds,
scrollable canvas and viewport separate; include Scale/Offset, layout,
constraints and padding in the context. Numerical formulas and update timing
remain hypotheses where the operational record marks them untested.

## Knowledge — conditional model selection

Trigger: changing or evaluating agent roles. Read the current `openai/agents`
TOML files. Normal roles use Luna Max research, Sol High optimization, Astra
High review, and Astra Extra High debugging; the primary model is selected
by the session. Treat these assignments as role-fit choices, not measured
Roblox accuracy. Require sources and precise MISS results.

When using a benchmark, check its version, uncertainty intervals and scoring
definition. Success across multiple attempts, such as pass@4, is not
single-attempt accuracy. More reasoning or output does not establish better
accuracy; more steps do not prove higher latency; cumulative input does not
measure peak context. Do not mix updated displayed costs with older artifact
costs. Benchmark costs are not session bills; API tiers, cache traffic, long
context and Fast settings affect costs. Recheck evidence when roles, models,
pricing or tasks change.
For local comparisons, count retries, orchestration, repair, missed restrictions,
test defects, and human reruns; record input, cached input, output and reasoning
separately without double-counting reasoning. Mark absent baseline, latency,
usage, or actual cost unknown. No session restart is needed to read new evidence.

## Constraints — conditional engine operations

Trigger: an affected engine operation is about to be written or executed.
Engine limits: assess read/write/call security, caller capabilities, all tags,
class restrictions and serial/parallel phase separately. `Security=None` alone
does not establish permission. `ReadSafe` concerns parallel reads. It does not
grant writes or establish runtime effect, persistence, or replication.
Record Script RunContext, location, caller and datamodel. A required ModuleScript
uses its caller's environment; its class is not an independent privilege level.
Keep custom attributes (`GetAttribute`) distinct from engine properties.

Tool limits: a successful assignment/readback proves neither engine effect nor
replication. Studio MCP, Command Bar, plugins, and game scripts are distinct
contexts; unresolved MCP access stays unknown. Named restricted APIs must
return restriction evidence. Decline known inaccessible operations without
repeated trial calls or identity elevation. A version or metadata conflict
requires rechecking the decisive source, not choosing the more permissive value.
Read-only researchers report missing/stale cache to the primary; the primary
uses `api_dump.py --sync` for maintenance. No new session, hook, or per-turn scan
is required. Human-maintained `house_overlay.txt` is separate from sourced
operational records: propose exact undocumented entries with evidence before
adoption.

Project rule: prepare authored Script, LocalScript and ModuleScript objects and
source while Studio is stopped. Do not create or replace authored source objects
during Play. Source authoring, cloning prepared code, object creation, and script
activation are separate operations. Use the existing debug skill's controlled
probe procedure when unresolved behavior needs a test.
