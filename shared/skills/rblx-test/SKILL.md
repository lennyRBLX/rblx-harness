---
name: rblx-test
description: Use during Roblox development when writing tests, verification, or validation, or deciding whether to write any of them.
---

# Roblox tests

Follow project `AGENTS.md`; if it lacks Roblox guidance, read [CORE.md](../../CORE.md).
Let `H` be this skill's harness checkout.

Select tests by the decision they can change. Give one question, stable ID and
stopping condition. Start with the broadest useful measurement; remove irrelevant
prerequisites. Reuse valid findings and engine facts. Permit necessary measurement
repeats, failure reproductions and checks invalidated by changed source or workload.
Keep authored-algorithm correctness separate from documented engine behavior.

For execution, lifecycle, human readiness, independent result/capture pipelines,
measurement and cleanup, read [procedure.md](references/procedure.md). Use shared
support; keep tests under `tests/` and author only the required execution side.
For result source or collectors, read [buffer.md](references/buffer.md). New test
output uses the shared buffer codec and runtime prefix, never JSON. Missing,
partial or corrupt output cannot pass. Decode before shortening display.
