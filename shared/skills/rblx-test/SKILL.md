---
name: rblx-test
description: Select, write, or run Roblox tests. Use for Studio verification, test results, or profiler captures.
---

# Roblox tests

Follow project `AGENTS.md` or fall back to [CORE.md](../../CORE.md).

Test only the affected execution sides. Use shared `TestSupport` for lifecycle
and output. Decode the full result before applying display limits or reporting a pass.

| Task | Load |
|---|---|
| Test source, readiness, metrics, collection, cleanup | [Execution](references/procedure.md) |
| Choose and compare performance measurements | [Performance evidence](../rblx-optimize/references/measurement.md) |
| Active-session iteration or Play/Stop | [Hot reload](references/hot-reload.md) |
| MicroProfiler capture or frame-time claim | [Captures](references/captures.md) |
| Output format or collectors | [Buffer protocol](references/buffer.md) |
