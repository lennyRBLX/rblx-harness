# Visual acceptance

Use only for unresolved appearance/input. For each case, record question, setup,
action, expected distinction and result; capture only decisive evidence.

| Risk | Select affected cases |
|---|---|
| Layout | Direct children vs Folder/wrapper; sibling controls, padding, constraints, empty/one/many items, add/remove/hide/reorder, resize, scroll end |
| Text | Fixed-width Y wrapping; long/localized/RichText, font limits, clipping, readability |
| Root/input | Insets, clipping/Z order, mouse/touch/gamepad, world-UI occlusion/input, ViewportFrame camera/content |
| React/motion | Equal host control, keys/portals, mount/unmount/remount, rapid retarget, completion, cleanup, interaction during transitions |

For engine/package uncertainty use [probes](../../rblx-debug/references/probes.md).
Record build, package/fixture revisions, device/mode/viewport, tree and properties.
Measure bounds, layout content, canvas and viewport separately; sample bounded
frames and record timing, stability or timeout. Separate fixture defects from
engine behavior; test workarounds against failing and control cases.

For fractional geometry across screen origins, compare deltas with explicit
subpixel tolerance. Keep assigned properties/host counts exact; reject nonfinite
values and verify above-tolerance displacement fails. Record maximum delta and
failing item/sample. P-react used `0.001 px` on Studio `0.737.0.7371584`; observed
origin error reached `0.0000763 px`. Recheck when relying on an untested scale.
