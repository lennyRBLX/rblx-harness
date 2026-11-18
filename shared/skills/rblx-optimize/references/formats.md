# Compact formats

Compare through the consuming path. Preserve precision, inspection, recovery and
migration. Consider compact formats for large machine-processed data and readable
fields for PlayerData people inspect. Follow the [codec rules](../../rblx-writer/references/network.md).

| Candidate | Required comparison/contract |
|---|---|
| Fixed widths | Set range, signedness, offsets, byte order and overflow policy. Count headers and padding. Use fixed widths for random access or independent updates. |
| Dictionary IDs | Use for low cardinality. Include dictionary bytes, lifetime, updates and decode cost. Keep a reversible mapping. |
| Bit packing | Use for narrow ranges. Check masks, cross-byte access and bounds. Compare block widths or exceptions when outliers inflate width. |
| Varints and ZigZag | Use for mostly small magnitudes. Use ZigZag for signed values. Check large values against fixed-width sizes and bound decoding. |
| Quantization | Set range, step, rounding, overflow and error bounds. Nearest rounding gives ≤ half a step within range, excluding floating-point error. Test boundary values and consumers. Recheck encodings when scale or range changes. |
| Deltas | Set the base, resets and dependency bounds. Require exact arithmetic without overflow for lossless coding. Check encoded widths, prefix reconstruction, checkpoint bytes and effects on neighbors or the suffix. Check propagated error for quantized chains. |
| Compression | Measure encode/decode, scratch, copies, headers, checkpoints and access or update cost. Include dictionary distribution and version costs and test held-out data. Keep data packed when consumers can use it. Check small and already compressed inputs. |

For persisted changes, require versioned bounded decoding, recovery, proportional
migration, old/new fixtures and declared error checks before stored-data changes.

## Luau buffer defaults

- In a hot codec, pack adjacent fixed-width bit fields that share a byte-aligned
  8-, 16- or 32-bit word using `bit32` shifts and `bor` on validated fields. Write
  the word once with a typed accessor. Read it once and use `bit32.extract`.
  Verify byte equivalence when preserving the layout. Use `buffer.readbits` and
  `buffer.writebits` for dynamic widths or when clearer on a cold path. Split wider
  fixed records across words when the layout allows it. Use typed accessors for
  byte-aligned fields. Combine neighboring byte writes only where fewer calls
  matter in the deployment mode and the byte layout stays equivalent.
- Keep ordinary arrays as tables, especially read-heavy interpreted paths. Use a
  buffer at the needed width for large dense numeric data when memory or encoded
  bytes drive the choice. Check deployed read and write throughput separately for
  hot paths and include conversion, GC, retained memory and transfer copies. Use
  `buffer.copy`, `buffer.fill` and `buffer.writestring` for bulk byte operations.
- Keep named booleans for ordinary objects. Pack flags when the stored or encoded
  size of many flags matters.

Mechanism sources: [quantization](https://github.com/KhronosGroup/glTF/blob/main/extensions/2.0/Khronos/KHR_mesh_quantization/README.md),
[integer/delta packing](https://arxiv.org/abs/1209.2137),
[varints/ZigZag](https://protobuf.dev/programming-guides/encoding/),
[compression dictionaries](https://github.com/facebook/zstd#the-case-for-small-data-compression).
Native/SIMD results do not predict Luau timing. For platform effects, use
[engine-costs.md](engine-costs.md).
