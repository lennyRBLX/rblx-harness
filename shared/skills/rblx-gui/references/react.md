# React Lua

Resolve installed host/package APIs. Use React JS semantics with Luau syntax. ReactFlow is the default animator unless the user/project chooses otherwise; check compatibility before dependency changes.

- Use `React.Event`/`React.Change` for signals. Keep targets/structure in state and intermediate animation values in bindings.
- Fragment creates no host; Folder does. Keep layout items as host siblings; portals need an owned Instance parent. Unmount roots and clear refs/animation work at teardown. Effect completion does not prove settled engine layout.

## ReactFlow source checks

Resolve README conflicts using installed type declarations and implementation. Verify value support, defaults, hook dependencies and cleanup there. [React Lua](https://github.com/jsdotlua/react-lua) · [ReactFlow](https://github.com/OutOfBears/react-flow)

- `Spring`/`Tween` build definitions; `useSpring`/`useTween` return binding/start/stop. Value hooks return a binding.
- Check `src/Types.luau` and `Utility/LinearValue.luau` for both type and interpolation support before using Ray, Region3 or Region3int16. Initialize non-nil values.
- `Utility/SpringValue.luau`: speed/damper default to `1/1`, despite README speed `10`. Set intended values. `useSpringValue` watches target/speed/damper; start is mount-only.
- `Animations/Types/Tween.luau` needs start/from, target and info. TweenInfo requires RepeatCount `0`, Reverses `false`, DelayTime `0`; separate delay/startImmediate fields differ. `useTweenValue` watches only target; same-target info/delay edits do not replay. Truthy fallbacks mean nil/omitted options do not clear old values.
- Higher-order hooks lack unmount cleanup; wire stop to owner teardown. Probe installed-package delayed cancellation, retarget and completion as needed. TransitionFragment/DynamicList retain leaving children until completion callback.

For measured binding/stop behavior, load [react-evidence.md](react-evidence.md).
