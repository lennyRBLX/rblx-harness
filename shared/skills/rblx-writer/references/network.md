# Codec and remote contracts

Keep existing Event/owner APIs. For engine-dependent limits, use [engine evidence](engine.md).

## Codecs

- Specify packet ID/version, widths, byte/bit order, units, length limits and trailing-byte policy. Decode fully before committing state.
- Require nonnegative integers for zero-based offsets and lengths. Check `offset + width` against `buffer.len(b)` for byte access and `buffer.len(b) * 8` for bit access. Match the typed buffer accessors' little-endian order when exchanging bytes, or convert to the external format's order. Bound strings, counts, allocations and loops. Grow writers from positive capacity to a fixed maximum; zero must not loop forever.
- Reject nonfinite or out-of-schema inputs. Reject fractions for exact integer fields and round quantized fields explicitly. Validate encoded range and signedness before writing. Preserve UserIds with f64 or lossless mappings. Use strings for external integers beyond exact double range.
- Validate packed fields before combining them so excess bits cannot spill into adjacent fields. Bound varints by width and reject excess continuation and final overflow bits. Use a width that can hold the full ID range.
- Check boundary round trips, truncation, malformed lengths and overflow. Declare quantization error; preserve CFrame axes unless the schema permits loss. Use project IDs/names for durable enums.

## Transport

- Use `UnreliableRemoteEvent` only when the protocol tolerates loss and reordering. Keep the complete payload within the current engine limit. Sequence replaceable state updates and discard stale ones. Restore full state when unreliable deltas depend on prior packets.
- Bound batch counts/bytes and per-player queues; clear queues on leave.
- Use operation IDs and idempotent purchase/save handlers. Replace blocking InvokeClient dependencies with bounded requests, deadlines and disconnect cleanup.
- Validate runtime payloads despite typed wrappers; a generic remote name alone does not connect argument types to its schema.
- For HTTP, check protected-call success, HTTP status/Success and response schema separately. Protect JSON decoding; keep secrets server-side. Preserve the external contract for objects, arrays, nulls, mixed keys and large IDs; no invented sentinels.

DATA38/WRIT8 check literal codec risks and Event ownership; review computed schemas, protocol semantics and authorization separately.

Sources: [buffer](https://luau.org/library/#buffer-library), [remotes](https://create.roblox.com/docs/scripting/events/remote), [HTTP](https://create.roblox.com/docs/reference/engine/classes/HttpService).
