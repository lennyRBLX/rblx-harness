# Compact formats

Compare through the consuming path; retain precision, inspection, recovery and
migration needs. Large machine-processed data/maps are candidates; inspected
PlayerData can favor readable fields. Neither category has a fixed exclusion.
Use [network.md](../../rblx-writer/references/network.md) for codec correctness.

| Candidate | Required comparison/contract |
|---|---|
| Fixed widths | Ranges, signedness, offsets, endianness, overflow; actual bytes including headers/padding |
| Dictionary IDs | Low cardinality; include dictionary bytes, lifetime, updates and decode cost. Hashes cannot replace reversible mappings. |
| Bit packing | Narrow ranges; masks, cross-byte access, bounded reads. Compare block-local widths/exceptions when outliers inflate width. |
| Varints/ZigZag | Mostly small magnitudes, ZigZag for signed values; may exceed fixed widths for large values. Bound decode length/overflow. |
| Quantization | Range, resolution, rounding, overflow and accepted error. Nearest step s gives ≤s/2 error within range, excluding overflow/FP error. Test boundaries and consumer; scale/range changes may require re-encoding. Fixed widths permit random access/independent updates. |
| Deltas | Base, resets/checkpoints, dependency bounds, updates, reconstruction. Lossless only with exact arithmetic/no overflow. Smaller magnitudes do not shrink fixed fields. Chains need prefix reconstruction; checkpoints trade bytes for access. Updates may affect neighbors/suffix; quantized chains need propagated error bounds. |
| Compression | Encode/decode, scratch/copies, output bytes, random access/updates; compare blocks including headers/checkpoints. For supported trained dictionaries, include distribution/version cost and held-out data. Keep data packed if consumers can use it; small/already compressed inputs may not benefit. |

For persisted changes, require versioned bounded decoding, recovery, proportional
migration, old/new fixtures and declared error checks before stored-data changes.

Mechanism sources: [quantization](https://github.com/KhronosGroup/glTF/blob/main/extensions/2.0/Khronos/KHR_mesh_quantization/README.md),
[integer/delta packing](https://arxiv.org/abs/1209.2137),
[varints/ZigZag](https://protobuf.dev/programming-guides/encoding/),
[compression dictionaries](https://github.com/facebook/zstd#the-case-for-small-data-compression).
Native/SIMD results do not predict Luau timing. For platform effects, use
[engine-costs.md](engine-costs.md).
