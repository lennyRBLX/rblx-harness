---
name: rblx-test
description: Use during Roblox development when writing tests, verification, or validation, or deciding whether to write any of them.
---

# Roblox tests

Follow project `AGENTS.md`; if its Roblox guidance is absent, read
[CORE.md](../../CORE.md) once. Resolve the harness containing this skill as `H`.

- Treat `researcher` findings as settled; do not write checks to reconfirm them.
- Follow the surrounding suite's format. For standalone scripts, use named cases and one entry point.
- Standalone scripts emit one `TEST|` JSON line per run with `status` (`pass`, `fail`, or `unrun`) and `passed`, `failed`, `skipped` counts. On failure, include at most 10 unique entries in `failures`, each with `case` and a reason of at most 160 characters; include `omitted` when failures exceed 10. Give `unrun` a brief `reason`. Print no per-case successes. Python exits nonzero unless status is `pass`.
- Read Studio results with `python3 H/tools/harness.py studio output --studio-id ID --contains 'TEST|'`; pass `--since ARTIFACT` on later reads.
- Obtain human permission before automated Computer Use or screenshots for test evidence. Otherwise request the human result.
