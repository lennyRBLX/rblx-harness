# Runtime contracts

Use for startup, async services, Actors, or runtime assets. Resolve engine facts
through [engine evidence](engine.md); existing behavior records own streaming,
deferred signals, replication, persistence, and module-cache contracts.

- Connect lifecycle/tag signals before enumerating current objects. Make setup
  idempotent; handle existing players/characters and objects removed during setup.
  A readiness check must also handle completion before the waiter subscribes.
  An unconditional event Wait after firing can miss immediate delivery.
- Keep module loading separate from Start/init. Keep require paths static and
  acyclic; verify string prefixes, replication readiness, and resolver support in
  both engine and project tools. Tool-only `.luaurc` aliases are not engine proof.
- Choose frame callbacks by required phase, not by name recency. Use explicit
  render priority for camera ordering and own the matching unbind. A property
  signal delivers no value; read the property. ValueBase.Changed differs from
  Instance.Changed. Match exact class vs inheritance in instance lookups.
- Keep explicit `task.desynchronize()` scopes paired with `task.synchronize()`
  before normal/early exit. Parallel callbacks start parallel without an opener;
  synchronize before unsafe APIs. Query thread safety for reads as well as writes.
  Load dependencies in serial. Phase changes are not a nested stack.
- Pair `debug.profilebegin/end` in the same function, including branches and loop
  exits. Nested profiles are valid. If profiled work can throw, close the label
  after a protected call, then propagate/handle the failure. Cancellation and
  indirect calls require separate lifecycle review.
- Reuse the project's persistence/session-lock owner. Keep transforms repeatable;
  save on leave and shutdown through one coordinated owner. Bound retries with
  backoff/jitter, cancellation, and deadlines; retry non-idempotent work only after
  resolving ambiguous success. MemoryStore is temporary; messaging is notification,
  not durable state. Read current quotas instead of copying reference numbers.
- Use current asset permission/budget evidence for EditableImage/EditableMesh.
  Handle creation failure, release owned resources, reuse buffers, and prefer
  bulk drawing when measured useful. Preload only essential assets and inspect
  completion status. Seed a private Random stream when determinism matters.

Run `check source --only correctness PATH...` for OPT15/OPT20 pairing. It follows
direct global calls, branches, loops, early returns, and literal parallel callbacks.
It isolates nested functions and ignores comments/strings. It does not prove
alias/helper effects, arbitrary throws, cancellation, Actor ancestry, or API
thread safety. Keep scopes structurally balanced; correlated branch conditions
are not solved. `--only performance` also reports possible unsafe parallel writes
and missing per-frame labels as advisories.

Sources: [parallel execution](https://create.roblox.com/docs/scripting/multithreading),
[profiling](https://create.roblox.com/docs/studio/microprofiler/tag-code),
[lifecycle](https://create.roblox.com/docs/players).
