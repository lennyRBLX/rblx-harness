# Plan format

Use this structure for Plan Mode responses and written plans. Replace angle-bracket
fields with task facts; use `—` for an inapplicable section or field. Keep headings
and fields in this order. Add milestones with stable IDs in prerequisite order.
Place the marker inside the plan, including inside a required `<proposed_plan>` wrapper.

````markdown
<!-- rblx-plan -->
# <Deliverable>

Deliver <observable outcome>.
Store evidence at `<project-relative directory>`.

## Architecture

Assign <owners, exact write paths, authority, data flow and lifecycle>.

## APIs

- Use `<API/signature>` from <caller/phase> for <verified behavior>; review <direct source reference>.

## Luau Types

```luau
<Declare exact shared records and public signatures.>
```

## Milestones

### M01 — <Deliverable>

Requires: <milestone IDs or external inputs>.
Context: <missing facts, required source references and additional tool instructions>.
Write: <exact owned paths>.

1. Implement <action and output>.
2. Verify <observable acceptance, human/agent responsibility and evidence>.

Complete: <required proof>; receipt `<evidence directory>/M01.md`.
````

Use project-relative `path:line` or `path:start-end` references for local sources;
use commit-pinned URLs with line anchors for external source code. Identify proposed
APIs and types as proposed; cite existing source for verified contracts.

Apply TEST2–TEST3 to Verify actions. Use existing applicable results, direct
inspection or a focused new check as needed. Record skipped low-need checks
only when material; they do not block completion or count as passes.

After verified completion, save the milestone block with `Revision:` and `Evidence:`
fields in its receipt, then remove the block. Preserve IDs and contracts required by
remaining work. When all milestones have receipts, write `Complete.` under Milestones.
