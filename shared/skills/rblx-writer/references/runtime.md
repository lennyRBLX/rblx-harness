# Runtime contracts

Use [engine evidence](engine.md) for streaming, signals, replication, persistence,
module caches and API thread safety.

- Connect lifecycle/tag signals before enumeration. Handle existing
  players/characters and removal during setup. Subscribe readiness waiters without
  missing prior completion or immediate delivery.
- Make repeatable attachment setup idempotent. For services and controllers started
  once by their startup owner, rely on that lifecycle contract. Add startup guards
  only when repeated startup is supported or can occur.
- Register owned cleanup helpers with `EntityCleanup:Add`. Leave automatic lifecycle
  dispatch to `Server.server.luau` and `Client.client.luau`; do not call
  `EntityCleanup:Remove` or duplicate that dispatch in services, controllers, or
  their children. Never wrap any EntityCleanup API call in `pcall` or `xpcall`,
  including through closures or method references.
- Define owner operations at module scope, including operations called only during
  startup. Keep short signal adapters inline in `Start()` and call owner methods
  through the captured `self`. When passing a colon method to `task.spawn`, pass
  its receiver explicitly.
- Keep callbacks owned by `Start` inside `Start`. Name a callback when it is both
  connected and invoked directly for existing state; connect it before invocation.
  Use the captured `self` where owner access is needed.
- Use `task.spawn(function() ... end)` directly when no task handle is needed.
- Use Signals for notifications. Use explicit `Add`/`Remove` APIs for registered
  work.
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
- Access owned PlayerData through `getPlayerData`. Keep session profiles and
  persistence operations inside PlayerData. Do not repeat validity checks without
  an intervening yield or state change.
- Keep persistence transforms repeatable; coordinate leave/shutdown saves. Bound
  retries with backoff/jitter, cancellation and deadlines;
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
