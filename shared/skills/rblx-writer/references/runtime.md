# Runtime contracts

Use [engine evidence](engine.md) for streaming, signals, replication, persistence,
module caches and API thread safety.

- Connect lifecycle/tag signals before enumeration. Handle existing
  players/characters and removal during setup. Subscribe readiness waiters without
  missing prior completion or immediate delivery.
- Make repeatable attachment setup idempotent. For services and controllers started
  once by their startup owner, rely on that lifecycle contract. Add startup guards
  only when repeated startup is supported or can occur.
- Define named callbacks used only by `Start` inside `Start`. Use the captured
  `self` where owner access is needed. Connect the callback before invoking it
  directly for existing state.
- Separate require from Start/init. Keep paths static and acyclic; check prefixes,
  replication readiness and engine/project resolver support. `.luaurc` aliases alone
  do not prove engine support.
- Select frame callbacks by phase. Own render-priority unbinding. Property signals
  supply no value; read it. Distinguish ValueBase.Changed, Instance.Changed, exact
  class lookup and inheritance.
- Pair explicit `task.desynchronize()` with `task.synchronize()` before every exit.
  Parallel callbacks need no opener; synchronize before unsafe APIs, including reads.
  Require dependencies in serial. Phase changes are not a nested stack.
- Pair `debug.profilebegin/end` within one function across branches/loops. Close
  profiles after protected calls before handling/propagating errors. Review
  cancellation and indirect effects separately.
- Reuse the persistence/session-lock owner. Keep transforms repeatable; coordinate
  leave/shutdown saves. Bound retries with backoff/jitter, cancellation and deadlines;
  resolve ambiguous success before retrying non-idempotent work. MemoryStore is
  temporary; messaging is notification. Query current quotas.
- Check EditableImage/EditableMesh permissions and budgets; handle creation failure
  and release resources. Reuse buffers; batch drawing when measured useful. Preload
  essential assets and check status. Use private seeded Random streams for determinism.

For changed parallel/profile scopes, run `check source --only correctness PATH...`.
OPT15/OPT20 follow direct calls and structural flow, not aliases, helper effects,
throws, cancellation, Actor ancestry, thread safety or correlated branch conditions.
Performance-mode scope/label warnings are advisory.

Sources: [parallel](https://create.roblox.com/docs/scripting/multithreading),
[profiles](https://create.roblox.com/docs/studio/microprofiler/tag-code),
[lifecycle](https://create.roblox.com/docs/players).
