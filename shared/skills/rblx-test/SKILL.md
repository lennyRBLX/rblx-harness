---
name: rblx-test
description: Use during Roblox development when writing tests, verification, or validation, or deciding whether to write any of them.
---

# Roblox tests

Follow project `AGENTS.md`; if it lacks Roblox guidance, read [CORE.md](../../CORE.md) once. Let `H` be this skill's harness checkout.

- Treat `researcher` findings as settled; do not reconfirm them with checks.
- Follow the suite's format. Standalone scripts use named cases and one entry point; emit one `TEST|` JSON line per run with `status` (`pass`, `fail`, `unrun`) and `passed`, `failed`, `skipped` counts. On failure, include at most 10 unique `failures` with `case` and a reason of at most 160 characters; include `omitted` for excess failures. Give `unrun` a brief `reason`. Print no per-case successes. Python exits nonzero unless status is `pass`.
- Read Studio results with `python3 H/tools/harness.py studio output --studio-id ID --contains 'TEST|'`; add `--since ARTIFACT` for later reads.
- Get human permission before automated Computer Use or screenshots for test evidence; otherwise request the human result.
