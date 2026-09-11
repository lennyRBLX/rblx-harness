# Tool routes

Paths below are relative to the harness root. Run from the project root, or
supply `--root`. Caches live under `~/.cache/harness/`; never stage them.

| Work | Command |
|---|---|
| Whole or multiple source reads | `python3 <HARNESS_ROOT>/tools/context_pack.py read --file path.luau:10:80 --file other.luau` |
| Scoped review, staged + unstaged + untracked | `python3 <HARNESS_ROOT>/tools/context_pack.py diff --path shared/src --path plugins/Example` |
| Known engine questions | `python3 <HARNESS_ROOT>/tools/api_dump/api_dump.py batch access Class.Member behavior modules` |
| Known public types | `python3 <HARNESS_ROOT>/tools/type_lookup/type_lookup.py --type Owner.Type --type Other.Type` |
| Repeated Studio logs | `python3 <HARNESS_ROOT>/tools/studio_output.py --studio-id ID --since SNAPSHOT --contains RUN_MARKER` |
| Saved console logs | `python3 <HARNESS_ROOT>/tools/studio_output.py --input LOG --contains RUN_MARKER` |
| Session work/cost audit | `python3 <HARNESS_ROOT>/tools/session_audit.py --project NAME --output REPORT_STEM` |

`context_pack` defaults to 12,000 preview characters. Read-only agents add
`--no-cache` before `read`/`diff`. Source spans are inclusive. Paths must stay
inside `--root`; diff paths are literal and repo-relative. Diff requires an
existing base commit (default `HEAD`); `--base REF` selects another commit.
It records staged and unstaged diffs separately, plus deleted and untracked
files in the selected scope. A staged edit undone only in the worktree
remains visible. Choose the owned paths; do not review unrelated edits.

The primary passes the immutable artifact and affected paths to review.
`preview_complete=false` requires narrower spans or reading the saved artifact
before a complete review. Binary evidence needs separate inspection.
Use `--since PACK` only when that pack's relevant content is already in this
agent's current context. Matching spans are omitted; changed spans return.
Never use another agent's receipt as proof that this agent read the content.

`studio_output` performs one console read after checking the explicit Studio
ID. It never starts Play or executes Luau. It returns the full snapshot path,
new/matched/omitted counts and a bounded tail. Reuse its artifact with
`--since`; choose a new baseline after Studio/run changes. A non-prefix log
is treated as a reset/rotation and retained in full. `--contains` terms all
must match; errors outside that filter remain in the artifact. Logs alone
do not prove a test passed. TEST1 and engine probe rules still apply.
Use `--input` when the live transport is unavailable; report unavailable
evidence without inferring success.

The PreToolUse gate redirects literal whole-Luau `cat`, raw `git diff`, and
multiple standalone API evidence queries, including literal commands inside
`functions.exec`. Git summary/check modes and narrow `rg`/`sed` are allowed.
It is a workflow guard, not a general shell parser. Dynamic commands still
follow CORE. For a missing mode, denied cache write or user-required direct
tool, prefix that command with `HARNESS_TOOL_REASON='specific limitation'`.
This exempts routing only; agent and data/type restrictions still apply.

Audit counts are unique outer calls, including one count for an `exec` batch.
Rankings use visible call/result characters divided by four, excluding
ciphertext/media. Recorded model usage stays separate. The JSON includes
session inventory hashes and exact-repeat evidence; neither repeated work
nor estimated payload tokens is a measured saving. Never execute session text.
