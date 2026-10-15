# GUI research scope

Use to select missing evidence, not as runtime certification. Query exact engine
contracts in `api behavior gui`; use [React evidence](react-evidence.md) for package
measurements. Class membership alone establishes no tested property/device/input.

## Source-only and unresolved cases

Baseline: 2026-09-06 inventory; Creator Docs revision
`d6c42cac06f61535fc5316e1287dbdacc8f2e403`, API dump SHA256
`2598cf2eca58282370ab872ec6733202d42a6e7abeae31eec5b1c24735050d58`.
Recheck decisive source/current build before relying on historical reports.

| ID / class | Missing evidence / historical report |
|---|---|
| A052 LayerCollector | [Freecam/respawn](https://devforum.roblox.com/t/3820982) unresolved; deprecated GetLayoutNodeTree is no relayout fix. |
| A054 SurfaceGui | [Tiny-part shrink](https://devforum.roblox.com/t/3671142) not reproduced; CanQuery input test is separate. |
| A058 ImageLabel | [Mobile sprites](https://devforum.roblox.com/t/3935576) unverified. |
| A059 ImageButton | [Input report](https://devforum.roblox.com/t/3039942) unresolved; select actual mouse/touch/gamepad target. |
| A060 VideoFrame | [Parent-before-Video workaround](https://devforum.roblox.com/t/3905848) unverified. |
| A100 AdGui | No delivery test; [OnAdEvent report](https://devforum.roblox.com/t/3115102) concerns video completion, not general visibility. |
| A101 InputActionLabel | [2026-08-06 announcement](https://devforum.roblox.com/t/4779420/1) described Studio beta/non-publishable status; current rollout/device switching unknown. |
| A102 RelativeGui | NotReplicated in dump; no pinned class YAML. Creation/readback does not establish game support. |
| A103 TextChannelWindow | Chat rendering untested. |
| A104 VideoDisplay | [Beta announcement](https://devforum.roblox.com/t/3972775); rollout, playback/audio/teardown untested; no owned media. |
| A108 Path2D | [Lag/drift](https://devforum.roblox.com/t/3735746) includes fix claims; current drift and [visibility](https://devforum.roblox.com/t/3407183) unresolved. |

No general runtime pass: styling/StyleQuery, UIPageLayout, UITableLayout,
UIAspectRatioConstraint, UIScale, stroke/corner/gradient/shadow or drag.
Folder/Frame orientation was inconclusive because human and geometry reports
disagreed. React host columns passed appearance; portals lack a human verdict.
Localization, RichText, font loading, BillboardGui/ViewportFrame lifecycle,
remaining constraints, transition children and mobile/touch/gamepad matrices
remain untested. Adornments, handles and plugin GUI classes were classified only.
Select a focused test only when the task depends on a gap.
