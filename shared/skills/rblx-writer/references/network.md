# Network contracts

Use for buffers, serialization, or remotes. Keep the existing Event/owner APIs.

- Define packet ID, version, field widths, units, length limits, and trailing-byte
  policy. Validate before mutation; decode failures must not commit partial state.
- Check integer, nonnegative offsets/lengths and `offset + width <= buffer.len(b)`.
  Bound strings, packet counts, allocation, and decode loops. Grow writers from
  positive capacity with a maximum; zero capacity must not cause endless doubling.
- Reject NaN/infinity and out-of-range values before integer writes or quantization.
  Match signedness and precision. Preserve UserIds with f64 or lossless mapping;
  keep external integers beyond exact double range as strings.
- `bit32` is 32-bit. Bound varints to the codec width; reject excess continuation
  and high overflow bits in the final byte. Do not use a u32 varint for large IDs.
- Test codec round trips at boundaries, truncation, malformed lengths, and overflow.
  Quantization tests need an error bound. Do not discard CFrame axes without a
  protocol contract. Use project-owned IDs/names for durable enum schemas.
- Batch within count/byte limits; bound per-player queues and clear on leave.
  Separate reliable state changes from disposable updates. Unreliable packets may
  be lost/reordered: sequence updates and periodically restore full state when
  deltas depend on prior packets. Check current payload limits through `api`.
- Transport reliability does not make purchases/saves exactly once. Use operation
  IDs and idempotent server handlers. Do not block server progress on InvokeClient;
  use requests with bounded pending state, deadlines, and disconnect cleanup.
- Runtime payload validation remains necessary with typed wrappers. A generic
  remote name alone does not link the argument types to its payload schema.
- For HTTP, distinguish protected-call success, HTTP Success/status, and valid
  response data. Protect JSON decoding; check its schema. Keep secrets server-side.
  Honor the external JSON contract for empty objects, arrays, nulls, mixed keys,
  and large IDs; do not invent sentinel fields without that contract.

`check source --only correctness,replication PATH...` checks literal lossy codec
uses (DATA38, advisory) and Event ownership, including UnreliableRemoteEvent
(WRIT8). Computed sizes, protocol semantics, and authorization need review/tests.

Sources: [buffer](https://luau.org/library/#buffer-library),
[remote events](https://create.roblox.com/docs/scripting/events/remote),
[HTTP](https://create.roblox.com/docs/reference/engine/classes/HttpService).
