# Platform size and copy costs

Query sourced contracts: `api behavior buffer-layout-copy`,
`api behavior encoding-codec-bounds`, `api behavior datastore-size-compression`.
Use [engine evidence](../../rblx-writer/references/engine.md) for caller/phase access.

- Buffers use zero-based byte offsets (bits for readbits/writebits), little-endian
  numbers and fixed mutable storage. API transfer copies buffers, losing identity;
  include copies in peak memory. writebits accepts 0..32 bits and writes low bits;
  specify range policy before identity/precision can truncate.
- EncodingService: use documented algorithms/levels. Check
  `GetDecompressedBufferSize` against an application limit before decompression;
  reject unknown size/invalid input. Service maxima are not application budgets.
  Hashes are binary digests; encode deterministically and handle text-only paths.
- Distinguish packed bytes, application compression and platform encoding/compression.
  Events compress some types, including buffers; unreliable packets exceeding limits
  drop. Measure the actual path; raw length proves neither wire size nor acceptance.
- DataStores: distinguish serialized request size, rate budgets, rounded throughput
  and compressed backend storage. Use current JSONEncode request sizing. Guidance
  measures latest-version storage after platform compression and discourages
  pre-compression: prefer uncompressed application data. Require persistence-path
  evidence for exceptions/savings; raw buffer, JSON length or compression ratios
  cannot establish backend storage.

Creator Docs baseline `031b2f91d3d47274c255f3ed5691c29f792c181d`:
[buffer](https://create.roblox.com/docs/reference/engine/libraries/buffer),
[EncodingService](https://create.roblox.com/docs/reference/engine/classes/EncodingService),
[transport](https://create.roblox.com/docs/reference/engine/classes/UnreliableRemoteEvent),
[DataStores](https://create.roblox.com/docs/cloud-services/data-stores/error-codes-and-limits).
