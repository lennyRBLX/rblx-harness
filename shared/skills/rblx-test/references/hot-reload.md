# Hot reload

## Bridge fit

- Use only for pure modules whose consumers read a mutable flat export table.
  Use project adapters for private state, cached functions/callbacks, copied
  exports, running coroutines, old instances or closure/`self` identity assumptions.
- Audit both versions, cloned children and callers for require-time side effects.
  Check own-name/identity lookups, folder/tag/attribute discovery, omitted
  non-Archivable descendants and clone size.
- Order changed dependencies and owners explicitly: sibling caches survive;
  cloned child modules load fresh.

## Sequence

1. Snapshot stored/editor source exactly; reconcile drafts before patching.
2. Bootstrap; poll until `Ready`. Use a new session per playtest; recheck identity
   after respawn/reconnect.
3. Read the target's `Revision`, not the root's. Serialize patches by target/side;
   poll the submitted `RequestId` to a terminal state.
4. After `Applied`, exercise the retained game caller on each affected side/client.
5. If behavior fails, undo at the current revision and verify the old caller.
   Account for action effects and disk edits separately.
6. Stop on `TimedOut` or the candidate cap. Retain bridge/candidates, including
   failed evaluations, until Play ends: closures may still reference `script`.

## Persistence

Keep intended source on disk; runtime target Source stays unchanged. Keep
bridge/candidates out of persistent source. Defer persistence until Edit without
stopping Play solely to save. Use fresh Edit stored/editor snapshots; reconcile
conflicts before retrying. Reapply runtime properties to their Edit templates.
