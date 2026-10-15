# Codec and remote contracts

Keep existing Event/owner APIs. For engine-dependent limits, use
[engine evidence](engine.md).

## Codecs

- Specify packet ID/version, widths, units, length limits and trailing-byte policy.
  Decode fully before committing state.
- Require integer, nonnegative offsets/lengths and `offset + width <= buffer.len(b)`.
  Bound strings, counts, allocations and loops. Grow writers from positive capacity
  to a fixed maximum; zero must not loop forever.
- Reject nonfinite/out-of-range values before integer writes or quantization.
  Match signedness/precision. Preserve UserIds with f64 or lossless mappings;
  use strings for external integers beyond exact double range.
- `bit32` is 32-bit. Bound varints by width; reject excess continuation and final
  overflow bits. A u32 varint cannot hold large IDs.
- Check boundary round trips, truncation, malformed lengths and overflow. Declare
  quantization error; preserve CFrame axes unless the schema permits loss.
  Use project IDs/names for durable enums.

## Transport

- Bound batch counts/bytes and per-player queues; clear queues on leave.
  Sequence disposable updates; restore full state when unreliable deltas depend
  on prior packets. Query current payload limits.
- Use operation IDs and idempotent purchase/save handlers. Replace blocking
  InvokeClient dependencies with bounded requests, deadlines and disconnect cleanup.
- Validate runtime payloads despite typed wrappers; a generic remote name alone
  does not connect argument types to its schema.
- For HTTP, check protected-call success, HTTP status/Success and response schema
  separately. Protect JSON decoding; keep secrets server-side. Preserve the external
  contract for objects, arrays, nulls, mixed keys and large IDs; no invented sentinels.

DATA38/WRIT8 check literal codec risks and Event ownership; review computed schemas,
protocol semantics and authorization separately.

Sources: [buffer](https://luau.org/library/#buffer-library),
[remotes](https://create.roblox.com/docs/scripting/events/remote),
[HTTP](https://create.roblox.com/docs/reference/engine/classes/HttpService).
