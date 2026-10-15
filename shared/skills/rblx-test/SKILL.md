---
name: rblx-test
description: Select, write, or run Roblox tests and validation.
---

# Roblox tests

Follow project `AGENTS.md`; if Roblox rules are absent, read [CORE.md](../../CORE.md).

Apply CORE test-selection and evidence rules. Keep test source under `tests/`;
author only the required execution side. Use shared `TestSupport` lifecycle and
codec. New output uses its buffer protocol and runtime prefix, never JSON.
Missing, partial or corrupt results cannot pass; decode before display limits.

| Task | Load |
|---|---|
| Prepare/run tests; readiness, metrics, collection, cleanup | [procedure.md](references/procedure.md) |
| MicroProfiler capture or frame-time claim | [captures.md](references/captures.md) |
| Output source or collectors | [buffer.md](references/buffer.md) |
