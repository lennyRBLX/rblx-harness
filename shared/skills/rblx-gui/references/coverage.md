# Research coverage

Load for class coverage, evidence limits or a new test scope. This is a dated
research disposition, not a runtime certification. Shared engine decisions
live in `tools/api_dump/behavior.json`; query the exact API or record. Package
decisions live in [react.md](react.md). Broad class membership does not imply
that every property, device or interaction was tested.

## Inventory

The 2026-09-06 API inventory covers 80 classes. Scope exclusions do not mean
that an API is unsupported.

| Group | Classes |
|---|---|
| Native roots/content (19) | AdGui, BillboardGui, CanvasGroup, Frame, ImageButton, ImageLabel, InputActionLabel, Path2D, RelativeGui, ScreenGui, ScrollingFrame, SurfaceGui, TextBox, TextButton, TextChannelWindow, TextLabel, VideoDisplay, VideoFrame, ViewportFrame |
| Layout/modifiers (15) | UIAspectRatioConstraint, UICorner, UIDragDetector, UIFlexItem, UIGradient, UIGridLayout, UIListLayout, UIPadding, UIPageLayout, UIScale, UIShadow, UISizeConstraint, UIStroke, UITableLayout, UITextSizeConstraint |
| Styling (5) | StyleDerive, StyleLink, StyleQuery, StyleRule, StyleSheet |
| Inherited/base access (12) | GuiBase2d, GuiButton, GuiLabel, GuiObject, LayerCollector, StyleBase, SurfaceGuiBase, UIBase, UIComponent, UIConstraint, UIGridStyleLayout, UILayout |
| Outside game-GUI research (29) | ArcHandles, BoxHandleAdornment, ConeHandleAdornment, CylinderHandleAdornment, DockWidgetPluginGui, FloorWire, GuiBase, GuiBase3d, GuiMain, HandleAdornment, Handles, HandlesBase, ImageHandleAdornment, InstanceAdornment, LineHandleAdornment, PVAdornment, ParabolaAdornment, PartAdornment, PluginGui, PyramidHandleAdornment, QWidgetPluginGui, SelectionBox, SelectionLasso, SelectionPartLasso, SelectionPointLasso, SelectionSphere, SphereHandleAdornment, SurfaceSelection, WireframeHandleAdornment |

The inherited group was inspected for access and ownership contracts. The
outside-scope group was classified only. Native/layout/style classes have
source dispositions; runtime evidence is limited to the tests below and the
scoped `tested_behavior` records. Styling, UIPageLayout, UITableLayout,
UIAspectRatioConstraint, UIScale, strokes/corners/gradients/shadows and drag
have no general runtime pass from this research.

## Source-only decisions and open reports

Sources were inspected at Creator Docs revision
`d6c42cac06f61535fc5316e1287dbdacc8f2e403` and API dump SHA256
`2598cf2eca58282370ab872ec6733202d42a6e7abeae31eec5b1c24735050d58`.
The class links below pin the relevant YAML. Forum links are historical
reports retrieved 2026-09-06; a promised fix or beta announcement does not
establish the current contract. Recheck the decisive source and current build
before relying on an open report.

| ID / class | Decision and boundary |
|---|---|
| A052 [LayerCollector](https://github.com/Roblox/creator-docs/blob/d6c42cac06f61535fc5316e1287dbdacc8f2e403/content/en-us/reference/engine/classes/LayerCollector.yaml) | Enabled, ResetOnSpawn and ZIndexBehavior have separate purposes. Deprecated GetLayoutNodeTree is not a relayout fix. [Freecam/respawn report](https://devforum.roblox.com/t/3820982) remains unresolved here. |
| A054 [SurfaceGui](https://github.com/Roblox/creator-docs/blob/d6c42cac06f61535fc5316e1287dbdacc8f2e403/content/en-us/reference/engine/classes/SurfaceGui.yaml) | Select SizingMode, PixelsPerStud and CanvasSize for the face-resolution policy. [Tiny-part shrink report](https://devforum.roblox.com/t/3671142) was not reproduced; the CanQuery input test is separate. |
| A058 [ImageLabel](https://github.com/Roblox/creator-docs/blob/d6c42cac06f61535fc5316e1287dbdacc8f2e403/content/en-us/reference/engine/classes/ImageLabel.yaml) | IsLoaded is read-only and not replicated. Crop, slice and tile settings use distinct units. [Mobile sprite report](https://devforum.roblox.com/t/3935576) is unverified. |
| A059 [ImageButton](https://github.com/Roblox/creator-docs/blob/d6c42cac06f61535fc5316e1287dbdacc8f2e403/content/en-us/reference/engine/classes/ImageButton.yaml) | Combine image-rendering rules with inherited GuiButton input. Test the actual mouse/touch/gamepad target. [Input report](https://devforum.roblox.com/t/3039942) remains unresolved. |
| A060 [VideoFrame](https://github.com/Roblox/creator-docs/blob/d6c42cac06f61535fc5316e1287dbdacc8f2e403/content/en-us/reference/engine/classes/VideoFrame.yaml) | Use IsLoaded/Loaded and own playback lifetime. Recheck current concurrent-video limits. [Parent-before-Video workaround](https://devforum.roblox.com/t/3905848) is unverified. |
| A100 [AdGui](https://github.com/Roblox/creator-docs/blob/d6c42cac06f61535fc5316e1287dbdacc8f2e403/content/en-us/reference/engine/classes/AdGui.yaml) | Requires an eligible block Part in Workspace and an exclusive face; provide FallbackImage for no fill. [OnAdEvent discussion](https://devforum.roblox.com/t/3115102) concerns video completion, not a general visibility callback. No ad-delivery test. |
| A101 [InputActionLabel](https://github.com/Roblox/creator-docs/blob/d6c42cac06f61535fc5316e1287dbdacc8f2e403/content/en-us/reference/engine/classes/InputActionLabel.yaml) | InputAction is writable; resolved hint text/image are read-only. [2026-08-06 announcement](https://devforum.roblox.com/t/4779420/1) described Studio beta/non-publishable availability. Current rollout and device switching were not established. |
| A102 RelativeGui | Dump says NotReplicated; the pinned docs have no class YAML. Ordinary game behavior remains unresolved. Do not infer a supported contract from creation/readback. |
| A103 [TextChannelWindow](https://github.com/Roblox/creator-docs/blob/d6c42cac06f61535fc5316e1287dbdacc8f2e403/content/en-us/reference/engine/classes/TextChannelWindow.yaml) | Allowed children include UICorner, UIAspectRatioConstraint, UISizeConstraint and scripts. NotBrowsable; TargetTextChannel is writable. Chat rendering was not tested. |
| A104 [VideoDisplay](https://github.com/Roblox/creator-docs/blob/d6c42cac06f61535fc5316e1287dbdacc8f2e403/content/en-us/reference/engine/classes/VideoDisplay.yaml) | VideoPlayer → Wire → display Input. [Announcement](https://devforum.roblox.com/t/3972775) described Studio beta. Live rollout and playback/audio/teardown remain untested; no owned media was supplied. |
| A108 [Path2D](https://github.com/Roblox/creator-docs/blob/d6c42cac06f61535fc5316e1287dbdacc8f2e403/content/en-us/reference/engine/classes/Path2D.yaml) | Use at least two control points; use arc-length sampling for even spacing. [Lag/drift report](https://devforum.roblox.com/t/3735746) includes an original fix and a later promised fix; current drift was not checked. [Visibility report](https://devforum.roblox.com/t/3407183) remains unresolved. |

Source SHA256, in table order excluding RelativeGui:

```text
LayerCollector 40cb871235e052431f776b8ca0b00c4ca5e2a5a7847377693a74516324d0c723
SurfaceGui f81867f935a2f332b8688372ff6e6217ba85bd025c5b0868bd4072e7de2a7d6e
ImageLabel c6d304503c990788624a92f8a2f389e2133a1b573748bbb8fa4a894aa43f33c5
ImageButton a759144ea458d57ceacd82724571b2370e299c670c8123af1031b8e82e5f40c9
VideoFrame 0a1984d9b1148bddea21705f52789d59eeadbc381d9bb29b2f1b4486bd751c67
AdGui 5596a996faf81c8268aaf4e18bbfadd1e805e147ef7aee2b2819ced59598a514
InputActionLabel 1fddd86f36b3355759084bed02ea36803972f28b4fc82dc43928897d49b9632e
TextChannelWindow 9495c9d23d4436b849a44cbcfb2d113662c49a0b44e932a4d2e4655481f2c1b5
VideoDisplay 235aa61ab0595c445a8f0066abdcfaab9b51c975cf64bde2f23443bdc5b74ca0
Path2D b0394274e6fb7bae16d29896d4ce5d75e7a44bd101f62aa5263e0a74a1764e49
```

StyleQuery has a source disposition covering selector/feedback risks; no
runtime style-system test was performed. Native Folder/Frame-wrapper layout
orientation was inconclusive where the human description and geometry record
disagreed. React host-column appearance passed, but portal appearance has no
human verdict. Localization, RichText, font loading, BillboardGui and
ViewportFrame lifecycle, remaining size/constraint combinations, transition
children and mobile/touch/gamepad matrices remain untested. Select a focused
test when a new task depends on these cases.
