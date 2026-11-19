# Mesh deformation and rigid movement

## Choose the movement path

- Use a skinned mesh and animate `Bone.Transform` for continuous deformation when topology is fixed and skin weights can express the result. Use the fewest bones that meet the visual tolerance. Use bones for independently animated pieces of one visual object when the pieces need no separate physics. Tile large cosmetic surfaces and animate only nearby patches if transitions remain acceptable.
- Use `EditableMesh` for runtime topology changes, infrequent geometry edits or required per-vertex control. Prefer fixed size when existing vertices change and topology stays fixed. Update only changed vertices and lower the cadence where the visual contract allows. Apply local edits on each peer that needs the result. Follow the writer's [asset rules](../../rblx-writer/references/runtime.md).
- Move a welded assembly at its root when behavior allows. Use `Model:PivotTo` for rigid placement of an intact rig when its model pivot meets the movement requirements. Use `WorldRoot:BulkMoveTo` for many independent `BasePart`s with poses ready together. Reuse the two arrays with matching part and CFrame indices. Keep individual moves when the behavior depends on their pivots, ordering or intermediate state.
- Use `FireAllEvents` if listeners need `Position` or `Orientation` change notifications. Use `FireCFrameChanged` when CFrame notifications suffice.

## Preserve the pose and geometry contracts

- `Bone.Transform` is a rest-space animation offset local to each peer. Use `TransformedWorldCFrame` when readback needs the animated pose. Share the visual inputs and clock across clients where necessary. Use the same analytic surface function for a visual wave and authoritative height queries such as buoyancy. Apply a procedural override in `PreSimulation` when an Animator writes the same bones and the procedural pose must take precedence. Verify on the rig.
- Use `Motor6D.Transform` for procedural joint animation that offsets a rest pose. Keep `C0` and `C1` for changes to the joint's attachment frames.
- For waves whose lighting should follow the surface, include slope rotation in the same `Bone.Transform` write. Use the normal proportional to `(-dh/dx, 1, -dh/dz)` and convert the desired axes and offset to rest space before building the pose with `CFrame.fromMatrix`. Reuse row/column terms when the wave and grid coordinates separate. Validate lighting, seams and deformation error in a rendered scene.
- For generated skinning, set vertex bone IDs before the corresponding weights. Match mesh bone names and bind transforms to the Bone hierarchy. Verify rotation as well as translation. If collision must follow editable vertex motion, plan a deliberate geometry refresh with `AssetService:CreateMeshPartAsync` followed by `MeshPart:ApplyMesh`.

Use the actual part, bone and vertex counts in [benchmarks](measurement.md#benchmarks).

Sources: [Bone](https://create.roblox.com/docs/reference/engine/classes/Bone), [EditableMesh](https://create.roblox.com/docs/reference/engine/classes/EditableMesh), [BulkMoveTo](https://create.roblox.com/docs/reference/engine/classes/WorldRoot#BulkMoveTo).
