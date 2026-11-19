# Runtime contracts

Use [engine evidence](engine.md) for streaming, signals, replication, persistence, module caches and API thread safety.

- Follow the [module startup rules](../../../CORE.md#modules) for players. Connect other lifecycle and tag signals before enumeration. Handle removal during setup and subscribe readiness waiters without missing prior completion or immediate delivery.
- Make repeatable attachment setup idempotent. For services and controllers started once by their startup owner, rely on that lifecycle contract. Add startup guards only when repeated startup is supported or can occur.
- Register owned cleanup helpers with `EntityCleanup:Add`. Leave automatic lifecycle dispatch to `Server.server.luau` and `Client.client.luau`; do not call `EntityCleanup:Remove` or duplicate dispatch in services, controllers, or their children. Never wrap an `EntityCleanup` API call in `pcall` or `xpcall`, including through closures or method references.
- Define owner operations at module scope, including operations called only during startup. Keep short signal adapters inline in `Start()` and call owner methods through the captured `self`.
- Call `task.spawn` directly when no task handle is needed. When passing a colon method, pass its receiver explicitly.
- Use Signals for notifications. Use explicit `Add`/`Remove` APIs for registered work.
- Separate require from Start/init. Keep paths static and acyclic; check prefixes, replication readiness and engine/project resolver support. `.luaurc` aliases alone do not prove engine support.
- Use a change signal when it meets the consumer's timing and ordering requirements. Select frame callbacks by required phase and own render-priority unbinding. Property signals supply no value; read it. Distinguish ValueBase.Changed, Instance.Changed, exact class lookup and inheritance.
- Resolve repeatedly used Instances once per valid lifetime. Refresh references at respawn, replacement, or stream-in and release them on removal. Coalesce writes only when consumers tolerate the resulting notifications, order and freshness. Run cosmetic motion on clients when they can reconstruct it from shared inputs. Keep gameplay outcomes with their authoritative owner.
- When setup can run off-tree, finish the properties and descendants required by observers before parenting the root into the live tree.
- Pair explicit `task.desynchronize()` with `task.synchronize()` before every exit. Parallel callbacks need no opener; synchronize before unsafe APIs, including reads. Require dependencies in serial. Phase changes are not a nested stack.
- Use Actor messages for discrete work items and results. Treat ordinary table payloads as copies. Use `SharedTable` when Actors need shared mutable state and have explicit write ownership or synchronization.
- Pair `debug.profilebegin/end` within one function across branches/loops. Close profiles after protected calls before handling/propagating errors. Review cancellation and indirect effects separately.
- Access owned PlayerData through `getPlayerData`. Keep session profiles and persistence operations inside PlayerData. Do not repeat validity checks without an intervening yield or state change.
- Keep persistence transforms repeatable; coordinate leave/shutdown saves. Bound retries with backoff/jitter, cancellation and deadlines; resolve ambiguous success before retrying non-idempotent work. MemoryStore is temporary; messaging is notification. Query current quotas.
- Check EditableImage/EditableMesh permissions and budgets; handle creation failure and release resources. Reuse buffers; batch drawing when measured useful. At startup, preload only assets needed for loading or spawn and check status. Use private seeded Random streams for determinism.

For changed parallel/profile scopes, run `check source --only correctness PATH...`. OPT15/OPT20 follow direct calls and structural flow, not aliases, helper effects, throws, cancellation, Actor ancestry, thread safety or correlated branch conditions. Performance-mode scope/label warnings are advisory.

Sources: [parallel](https://create.roblox.com/docs/scripting/multithreading), [profiles](https://create.roblox.com/docs/studio/microprofiler/tag-code), [lifecycle](https://create.roblox.com/docs/players).
