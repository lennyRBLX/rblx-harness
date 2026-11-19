# FastCluster renderer evidence

Use Edit and client fixture observations to select controls. Check the target renderer for timing, feature eligibility and capture coverage. [Capture guidance](fast-clusters.md#diagnose-a-capture)

## Property and membership checks

| Suspected change | What to isolate |
|---|---|
| Scale tools, `Model:ScaleTo()`, size tweens or Humanoid scale values | Read actual part `Size` on the rendering peer. `BodyHeightScale` changed the torso in Edit. In the local client trial the torso stayed the same size until `AutomaticScalingEnabled` was re-enabled. |
| Move, rotate, anchor or wake an assembly | Separate a static cluster's direct CFrame callback from spatial migration for a grid-owned skinned mesh. Compare intact rigs and standalone meshes. A stationary-state transition can regroup a grid-owned part even when the direct `Anchored` callback returns early. Track both groups if it migrates. |
| Duplicate, paste, destroy, group, reparent, undo/redo or stream | Track Workspace membership, Humanoid owner, wrap binding and skinned grouping. Separate off-tree construction from first attachment, last-member teardown and reattachment. In the history fixture, undo/redo changed membership while the retained `Size` stayed the same. For streaming, distinguish a focus/request change, arrival, departure and re-entry. |
| `BasePart` appearance and primitive or CSG shape | Check `Size`, `CastShadow`, `Material`, `MaterialVariant`, `Reflectance`, face surfaces, `Part.Shape`, `TrussPart.Style`, CSG payload/fidelity and `UsePartColor`. For `Color`/`BrickColor`, match Humanoid ownership, material and cached representation. The tested body tint rebuilt, while the accessory handle and union took update-only paths. |
| `MeshPart` swap or fidelity | Check mesh and texture asset/content, `DoubleSided`, `ApplyMesh()`, render and collision fidelity. Read back actual changes and allow time for collision recooking. The dispatcher also has internal mesh hash, fidelity and solid mesh descriptors, plus a gated convex-decomposition path. |
| `SpecialMesh`/`DataModelMesh` or a direct child `MeshPart` of a watched part | Include metadata writes in the suspect set. Their callbacks ignore the property descriptor. `Name`, `Archivable` and attributes reached rebuilds in the tested child meshes. |
| `SurfaceAppearance` | Isolate child insertion/removal, `Color` tint, `AlphaMode`, texture packs, maps and Content forms, and emissive mask, strength and tint. The tested tint was update-only. Replacing a child can rebuild with identical maps. Resampling depends on feature configuration. |
| `Decal` or `Texture` | Isolate child binding, face, tint, both transparency fields, texture and PBR maps and Content forms, pack metadata, emissive fields, UV scale/offset and rotation. Test `Decal.ZIndex` separately from `Texture.ZIndex`. Check Texture tiling and stud offsets. Both classes filter descriptors and gate resampling. Renaming either was quiet in the tested windows. |
| Outfit and wrap configuration | Separate `HumanoidDescription`, accessories, classic `Shirt`/`Pants`/`ShirtGraphic`/`BodyColors`, `CharacterMesh` and body proportions. On populated clothing, test `WrapLayer.Order`, `Puffiness`, `Enabled`, `CageOrigin`, `ReferenceOrigin`, `WrapTarget.Stiffness` and `CageOrigin`, and layer membership. A wrap subscription may be gated. `WrapTextureTransfer` Decal children also have a separate subscription. |
| Shared render settings | Inspect variant users, base-material users and scene-wide rebuilds separately. Compare effective `LightingStyle`, layered-clothing render mode and internal material-table reloads with ordinary lighting updates. `Lighting.ClockTime` was quiet in the fixture. `ShowDecompositionGeometry` and `Use2022Materials` have configuration-dependent paths. |

## Skeleton checks

- Use the actual live binding, watcher eligibility and bone mapping. The traced Bone watcher checks rest `CFrame` and `Name`. The JointInstance watcher checks rest `C0`/`C1` and structural `Part0`/`Part1`/`Enabled`. Pose writes through `Transform` bypass these descriptor checks. The MeshPart skeleton watcher can check `Name`, `Size`, gated `MeshId` and `FaceControls` child insertion.
- For constraints, isolate endpoint and `Enabled` changes, then `CFrame` and `Parent` changes on connected Attachments and their Attachment ancestors. Compare with moving an unused marker. Descendant insertion or reparenting of a bone, joint, constraint, Attachment, eligible part or `FaceControls` can request a structural check, including an eligible unused Attachment insertion. Nested Models affect the traced traversal. An unchanged mapping can end the geometry check early. Compare the actual joint class and linkage.

## Measured controls

| To distinguish | Result on the archive fixtures |
|---|---|
| Write cadence and cluster fanout | Eight distinct torso sizes before rendering gave one full build. The same eight spaced by about 0.1 s gave eight on distinct frames. Four parts resized on one rig gave one. One torso resize on each of two rigs gave two. An equal-value assignment was quiet on the simple rig. |
| Effective transparency, including a mask and net state | Both transparency fields request a check. The cached draw entry compares effective classes at `0` and `1`. Near-endpoint crossings rebuilt the R15 torso. Within-class writes and a `Transparency` change masked by `LocalTransparencyModifier = 1` took instance updates. Returning to the old transparency before rendering took an instance update in the two-rig control. A size change and restore still rebuilt. |
| Bound pixels versus bound geometry | First `EditableImage` bindings through `MeshPart.TextureContent`, `SurfaceAppearance` and `Decal` rebuilt. `DrawRectangle` on the same 64×64 image showed zero FastCluster scopes with one, two or three bindings across two rigs. Bound `EditableMesh` position, color/alpha, UV, normal, bone-weight and topology edits rebuilt, even an unused vertex addition. A position edit in storage was quiet and reattachment rebuilt. |
| Pose versus remapping | Eight spaced `Motor6D.Transform` and eight `Bone.Transform` changes were quiet in the client loops. `FaceControls.JawDrop` and `LeftEyeClosed` were quiet on the tested dynamic head. Disconnecting the connected R15 motor rebuilt. Endpoint and enable edits to the explicit accessory `Weld` and `WeldConstraint` reached geometry checks without full builds. Moving the connected nested `BallSocketConstraint` endpoint or its parent did the same. |
| Placement versus migration | The intact R15 pivot was quiet over a 200-stud move in the tested scene. The standalone head was quiet at 0.05 studs and rebuilt after a 2,048-stud move. Treat these as fixture inputs. Spatial grouping depends on starting key and classification. |
| Highlight state versus binding | `Enabled` and styling changes were quiet on the tested fixed target. `Adornee` changes could reach full builds while disabled, and repeated visits sometimes only updated the entity. Compare retarget order and starting cache. Studio selection queued an entity update. `SelectionBox` retarget, camera orbit and field of view were quiet on the settled fixtures. |
| Live garment versus empty wrap | The catalog hoodie (asset `7192553841`) had populated cage/reference IDs and incurred full builds on live Wrap edits. An earlier empty layer had quiet property windows. The hoodie logged a cage-fetch failure, and a later preload gave no per-cage result. Verify completed deformation on the target separately. |
| Named material versus base override | `StudsPerTile` on an in-use variant yielded one full build with one using rig and two with two. An unused variant map edit was quiet. In a three-rig Slate control, editing one named variant rebuilt one rig. Setting or clearing the Slate override rebuilt all three, including the other variant and plain Slate. |
| Replication versus actual membership change | A confirmed server torso resize and a confirmed `RequestStreamAroundAsync` arrival each gave one client full build in the Atomic R15 fixture. A replicated model attribute and a focus move after arrival were quiet. The return-focus window included both departure and re-entry, so its count applies to that combined window. |

The study also used quiet FastCluster controls for collision/touch/query flags, `Massless`, collision group, Humanoid `Health`/`WalkSpeed`/`DisplayName`, empty Folders and BillboardGuis, PointLight brightness, and ParticleEmitter color. Profile each affected subsystem for its own cost.

## Attribute work in later frames

When several writes hit the same binding, follow the dirty reasons through the prepare pass. The observed queue merges pending reasons including geometry, skeleton, composite material, tint and transparency. Dirty reasons, eligibility, cache misses and representation changes can turn a partial update into geometry work. One cluster can cover several edits, and one edit can affect several clusters.

| Path | Diagnostic rule |
|---|---|
| Priority and regular updates | Follow the burst past its first frame. Priority drains first. Regular work can yield between entries under a mode-dependent soft deadline that includes prior priority work. Distance and age influence pending work. A single entry can exceed the deadline. |
| Pending attachment and spatial migration | Follow later frames after insertion, stream-in, reparenting, scene reset or movement. Pending attachments can requeue across separately timed passes. Migration can defer work based on distinct spatial keys. Use actual keys and membership when analyzing fanout. |
| Asset waits and collision cooks | Separate the setter from downstream readiness. A qualifying dependency can wake a cluster, which can register waits for others. Check each wake for a full-build marker and verify actual load success. Read back completed collision fidelity and retain the frames around the cook. |
| Compositor | For outfit or texture work, inspect affected Humanoids and their qualifying body records. The compositor callback can queue broad work after the initiating action, subject to cache and feature conditions. Attribute it with a matched capture of the actual edit. |
| Materials and scene reset | Base-material scans match the base enum. Scene-reset requests can coalesce before Prepare rebuilds membership and queues attachment. Separate a change to effective global rendering settings from ordinary asset arrival. |

When queue limits or grid eligibility affect a decision, measure actual runtime timing and fanout. Treat queue deadlines as soft and migration eligibility as group-dependent.

## Read incomplete evidence

- Compare scope counts only when both captures cover the action boundaries and use the same markers. Absolute frame IDs are local to a run. A zero applies to the covered interval and marker set.
- Distinguish fixture queue/completion diagnostics from process-wide full-rebuild scopes. Mark missing or truncated counts as unknown and report observed entries within retained coverage. Spawn and long collision cooks can lose the opening frames. [Capture procedure](../../rblx-test/references/captures.md#retrieve-and-accept)
- Treat traced reflection descriptors, callbacks and native branches as leads for the target capture. Check effective feature settings, asset completion, queue behavior and marker coverage for procedural avatars or mesh failures where the decision depends on them.
