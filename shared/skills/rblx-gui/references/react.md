# React Lua

Resolve installed host/package APIs. Use React JS semantics with Luau syntax.
ReactFlow is the default animator unless the user/project chooses otherwise;
check compatibility before dependency changes.

- Use `React.Event`/`React.Change` for signals. Keep targets/structure in state and
  intermediate animation values in bindings.
- Fragment creates no host; Folder does. Keep layout items as host siblings;
  portals need an owned Instance parent. Unmount roots and clear refs/animation
  work at teardown. Effect completion does not prove settled engine layout.

## ReactFlow 0.5.0 source contracts

Baseline: [React Lua 17.2.1](https://github.com/jsdotlua/react-lua/tree/2e652e7ecf269b2611f5b58642c6740fc616f858),
[ReactFlow](https://github.com/OutOfBears/react-flow/tree/a7975e9ce3f36ec54e576a87a079921c73db531a),
React/ReactRoblox 17.2.1 and Promise 4.0.0. Recheck changed versions; use symbol
source over README examples.

- `Spring`/`Tween` build definitions; `useSpring`/`useTween` return binding/start/stop.
  Value hooks return a binding.
- `src/Types.luau` and `Utility/LinearValue.luau` define supported values;
  README-only Ray/Region3/Region3int16 are unsupported. Initialize non-nil values.
- `Utility/SpringValue.luau`: speed/damper default to `1/1`, despite README speed
  `10`. Set intended values. `useSpringValue` watches target/speed/damper; start
  is mount-only.
- `Animations/Types/Tween.luau` needs start/from, target and info. TweenInfo requires
  RepeatCount `0`, Reverses `false`, DelayTime `0`; separate delay/startImmediate
  fields differ. `useTweenValue` watches only target; same-target info/delay edits
  do not replay. Truthy fallbacks mean nil/omitted options do not clear old values.
- Higher-order hooks lack unmount cleanup; wire stop to owner teardown. Probe
  installed-package delayed cancellation, retarget and completion as needed.
  TransitionFragment/DynamicList retain leaving children until completion callback.

For measured binding/stop behavior, load [react-evidence.md](react-evidence.md).
