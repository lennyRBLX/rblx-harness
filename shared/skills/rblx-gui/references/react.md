# React Lua

Use React JS semantics with Luau syntax; resolve the project's host/package
APIs. ReactFlow is the default animator for React GUI; user/project choices
override it. Check compatibility before adding or changing dependencies.

Host: use `React.Event`/`React.Change` for signals and bindings for animated
properties. Use state for animation targets and UI structure; propagate
intermediate property values through bindings. Equal appearance does not
establish equal update cost. A Fragment creates no host; a Folder does. Keep layout items as
host siblings; portals need an owned Instance parent. Unmount roots and clear
external refs/animation work at owner teardown. React effect completion does
not prove engine layout has settled.

Baseline: [React Lua 17.2.1 source](https://github.com/jsdotlua/react-lua/tree/2e652e7ecf269b2611f5b58642c6740fc616f858),
[ReactFlow 0.5.0](https://github.com/OutOfBears/react-flow/tree/a7975e9ce3f36ec54e576a87a079921c73db531a)
(`React`/`ReactRoblox` 17.2.1, Promise 4.0.0). Recheck changed versions.

At that ReactFlow revision:

- `Spring`/`Tween` exports build animation definitions. `useSpring`/`useTween` return binding, start & stop; value hooks return a binding. Read the used symbol's source, not a newer README example.
- `src/Types.luau` + `Utility/LinearValue.luau` define accepted values. README-only Ray/Region3/Region3int16 are unsupported; initialize hooks with a supported non-nil value.
- `Utility/SpringValue.luau` defaults speed/damper to `1/1`; README speed `10` conflicts. Set intended values explicitly. `useSpringValue` watches target/speed/damper; start is mount-only.
- `Animations/Types/Tween.luau` requires start/from, target & info; `TweenInfo` requires RepeatCount `0`, Reverses `false`, DelayTime `0`. Its separate `delay`/`startImmediate` fields have different semantics.
- `useTweenValue` watches only target; same-target info/delay edits do not replay. Imperative updates use truthy fallbacks; omitted/nil fields do not clear prior options.
- Higher-order animation hooks memoize controllers without unmount cleanup; wire their stop handle to owner teardown. Probe delayed cancellation, retarget & completion on the installed package. Source concerns alone do not prove a leak. TransitionFragment/DynamicList retain leaving children until their completion callback.

Keep engine facts in API behavior records. Compare equal native/React host
trees; retain package wiring, refs, keys & effect timing in evidence.

P-react (Studio 0.737.0.7371584, Apple M4, React/ReactRoblox 17.2.1): 18 CPU
captures at 1/50/200 dots compared 48 synchronous `flushSync` updates with
equal host trees and human-confirmed motion. State update scope totals were
7.53–10.79 times binding totals; CPU frame p95 ranges overlapped. This supports
bindings for intermediate values in that workload, not an FPS estimate or
a result for default concurrent scheduling. Recheck changed packages/workloads.

P-cleanup (same build/packages): 100 mount/removal cycles per policy, with
200 `useAnimation` controllers per cycle, covered delayed and active tweens.
All 20,000 unstopped controllers continued listener activity after removal;
explicit owner stop prevented callbacks and value changes after removal or
stop return. Hosts/refs detached and stopped idle checks passed. This measures
owned listeners and values, not internal tasks, connections, GC or leak status.
