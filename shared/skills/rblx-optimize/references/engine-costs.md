# Engine and platform costs

## Runtime workload

- Reserve frame callbacks for per-frame requirements. Stagger periodic jobs, spread long jobs across frames and slow distant work when response latency and freshness allow it. Check peak frame time after batching. Use the writer's [runtime rules](../../rblx-writer/references/runtime.md) for event timing.
- Keep owned hot-loop state in Luau and reuse stable rest poses. Publish changed values to Instances at the required cadence. Use attributes for configuration or externally consumed state. Apply the writer's rules for cached inputs and coalesced writes. Use bulk queries when geometry, filters and completeness match.
- Use `TweenService` or an `AnimationTrack` for authored interpolation when timing and observer behavior match. Follow the writer's runtime rules for client-side cosmetics.
- Pool frequently recreated instances when reuse saves material construction cost within the retained-memory budget. Apply the writer's [pool rules](../../rblx-writer/references/luau.md). Spread publication of large subtrees across frames when consumers can handle incremental availability. Follow the writer's runtime rules for initial state.
- When physics is costly, anchor assemblies that need no simulation and disable collision, touch and query participation wherever consumers allow it. Use box or hull collision shapes when they preserve contact and query behavior. Reduce unnecessary constraints and disable unwanted self-collisions, such as ragdoll links that can pass through each other. Keep adaptive stepping unless gameplay requires fixed steps.
- Disable unused Humanoid states. Use `AnimationController` for animation-only rigs and custom movers that can provide their own gameplay behavior.
- For rendering bottlenecks, reuse identical mesh assets and matching appearance. Set `MeshPart.RenderFidelity` to `Automatic` or `Performance` where quality permits. Reduce overlapping transparency, repeated emitter reconfiguration and unneeded `CastShadow` or light `Shadows`. For rig movement, avatar customization, or skinned mesh changes, see [FastCluster updates](fast-clusters.md).
- For client memory, use streaming and distant model LOD when consumers tolerate partial availability. Size texture dimensions to their visible detail. Keep server-only assets in `ServerStorage`. Defer nonessential work until after spawn and measure startup and preload separately from frame work. Investigate retention with steady-workload trends in `LuaHeap`, `InstanceCount` and `PlaceScriptMemory`.
- Reduce send frequency, audience and bytes before tuning the packer. Send changed state and batch deltas when ordering and recovery allow it. When a scratch buffer has spare capacity, send its used prefix if the byte savings justify the allocation and copy. Use the writer's [network rules](../../rblx-writer/references/network.md) for transport contracts.
- Use Actors for separable compute when the savings exceed dispatch, copying and synchronization. Use chunks small enough to balance the workload. Keep write-bound work serial by default and batch the apply phase. Follow the [parallel contracts](../../rblx-writer/references/runtime.md).

Sources: [Creator performance guide](https://create.roblox.com/docs/performance-optimization/improve), [MicroProfiler tags](https://create.roblox.com/docs/performance-optimization/microprofiler/tag-table).

## Size and copies

Resolve missing contracts with `api behavior buffer-layout-copy`, `api behavior encoding-codec-bounds` or `api behavior datastore-size-compression`. Use [engine evidence](../../rblx-writer/references/engine.md) for access and evidence reuse.

- Treat buffers sent through events or Actor messages as snapshots. Include each transfer copy in peak memory. Use the writer's network rules for layout, offset and range checks.
- Use documented `EncodingService` algorithms and levels. Check `GetDecompressedBufferSize` against an application limit before decompression. Reject unknown sizes and invalid input. Encode binary digests deterministically for text-only paths.
- Send buffers directly to use the event transport's compression. Add application compression only when actual transport savings justify its CPU and scratch cost. Check acceptance on the actual event path and use transport evidence for wire-size claims. Report `buffer.len` as application bytes.
- For DataStores, track request size, rate budgets, rounded throughput and compressed backend storage separately. Use current `JSONEncode` request sizing. Store uncompressed application data by default. Require persistence-path evidence for precompression or claims about compressed latest-version storage.

[Buffers](https://create.roblox.com/docs/reference/engine/libraries/buffer) · [EncodingService](https://create.roblox.com/docs/reference/engine/classes/EncodingService) · [Transport](https://create.roblox.com/docs/reference/engine/classes/UnreliableRemoteEvent) · [DataStores](https://create.roblox.com/docs/cloud-services/data-stores/error-codes-and-limits)
