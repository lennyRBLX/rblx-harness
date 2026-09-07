# Visual checks

Stage cards before a human run: ID, hypothesis, setup, action, expected
distinction, result & capture. Select only affected cases:

- Hierarchy/layout: direct children vs Folder/wrapper; retain sibling controls. Check padding, constraints, empty/one/many items, add/remove/hide/reorder, resize & scroll end.
- Text: fix width for Y wrapping; check long/localized/RichText content, font limits, clipping & readability.
- Roots/input: device insets, clipping/Z order, mouse/touch/gamepad, world UI occlusion/input & ViewportFrame camera/content.
- React/motion: equal host-tree control, keys/portals, mount/unmount/remount, rapid retarget, completion & cleanup; interact during transitions.

For unresolved engine/library behavior use
[controlled probes](../../rblx-debug/references/probes.md). Record build,
package/fixture revisions, client mode/device/viewport, tree & properties.
Measure object bounds, layout content, canvas & viewport separately. Sample
bounded frames; record read timing, stability or timeout. Logs do not pass
visual checks. Separate fixture failure from engine behavior; recheck a
workaround against its failing case & control.

For fractional geometry at different screen origins, compare numeric deltas
with an explicit subpixel tolerance; exact serialized equality can fail from
coordinate precision. Keep assigned properties and host counts exact. Record
the maximum delta and failing item/sample; reject nonfinite values and verify
that a displacement above the tolerance fails. Human appearance still needs
confirmation. P-react on Studio 0.737.0.7371584 used 0.001 px; its observed
origin-dependent error reached 0.0000763 px. Recheck the bound for other scales.
