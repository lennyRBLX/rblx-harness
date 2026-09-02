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
