# Command review — 2026-09-15

Source: Codex task **Prepare Physics diagnostics**, id
`01a0a6fc-788f-7c51-9b00-24b812acd5eb`, read through `read_thread`.
Snapshot: three completed turns (32, 9, and 17 command executions) and one active
turn (57). These are tool-call counts, not subprocess counts or measured waste.
The active turn may continue; no changes were made to that task or its project.

## Findings

| Evidence | Assessment and change |
|---|---|
| `exec-03b6dd18-b559-4e91-a0ff-87eabdaebea3` and surrounding reads revisit Sparse/Codec ranges; first-turn command positions 3/5 reread PhysicsTest.server, 8/9 reread History before edits | Retain source spans. Batch known independent reads; narrow follow-up reads to missing content. Truncated output can justify a narrower read. |
| First-turn API batches at command positions 7, 15, 28 repeat BindToSimulation, PreRender, GetServerTimeNow, JSONEncode, SetAttribute | Query new APIs only. Keep earlier scoped answers and source revisions. These batches were individually fast (about 0.1 s for the later calls); redundant context and calls were the main cost. |
| `exec-2a99c90c-59fd-4230-8b1f-58225cd684a7` searches nonexistent `tools/check.py` / glob after `lute --help` | Use known `harness.py` family help, once. Avoid guessing paths or redoing discovery. |
| Each completed turn generates an Argon Game sourcemap despite primarily source-body changes | Reuse path mapping unless mapping inputs change. Do not confuse source-content hashes with path-map invalidation. |
| Summary-reduction turn: recorder check runs in command positions 6 and 7; position 7 changes analyzer/docs | The recorder rerun has no evident recorder-input change. Run the changed analyzer check and retain the recorder result. |
| Active turn: `exec-b7a49e28-cb00-444e-a273-a45393ee38da` edits one diagnostic classification, parses 12 sources via 12 Lute subprocesses, then runs five test scripts | Scope the classification check to recorder/analyzer consumers. Reuse unrelated solver/history results if dependencies are unchanged. Batch remaining parse-only files in one process when valid, and omit parses already covered by executable tests. |
| Active turn optimization tests fail during fixture and implementation changes | Those targeted reruns are useful; do not ban them as duplicates. Require the failure or changed input to be identified. |
| User explicitly assigns the three-shot capture to a human | Preserve that execution choice and report runtime gates unrun until human evidence arrives. |

Existing use of `api batch`, multi-path source checks, and batched file reads was
useful. Retain it. No claim is made that every repeat was waste, nor that every
test dependency is known from the transcript. No time/token saving is fabricated.

## Native mechanism selection

- [AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md):
  project instructions carry command and evidence policy from `shared/CORE.md`.
  This is model guidance, not a hard boundary.
- [Rules](https://learn.chatgpt.com/docs/agent-configuration/rules): command-prefix
  allow/prompt/forbidden decisions concern execution permissions. Prefix matching
  cannot determine whether a test adds evidence. No blanket Python, Git, grep,
  or test-runner ban is installed; such a ban would also block justified work.

No documented native setting assigns a semantic test-need score or automatically
caches arbitrary shell results. Agents assess need, decision, and evidence gap;
cross-call reuse stays in task context.

## Retired mechanism

The former `PreToolUse` hook required a first-line JSON declaration for recognized
shell checks and rejected identical check arguments within a batch. It validated
syntax, not the truth of a declared need or evidence gap. Arbitrary scripts and
Studio/MCP calls remained instruction-governed.

The hook and declaration protocol are retired. Setup removes exact generated
entries, including old checkout paths, while preserving custom handlers and
metadata. A no-op script keeps already-running sessions with cached hook entries
usable. Migration tests cover removal, repeated setup, and stale calls. Instruction delivery
uses native project guidance; declaration and duplicate-command blocking no longer
apply.
