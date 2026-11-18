# Luau hot paths

- Own and reset memory categories in shared threads. Use the
  [retention checks](engine-costs.md#runtime-workload) to investigate growth.
- In allocation-heavy loops, reuse owned scratch tables, return multiple values
  for short-lived results and hoist loop-invariant closures when lifetimes allow.
  Batch work instead of spawning one task per item where ordering permits.
  Precompute invariant strings and [keys](keys.md). Use a buffer for bulk byte
  output. Use the writer's [interpolation and assembly rules](../../rblx-writer/references/luau.md)
  when the output format permits.
  Preallocate large known-size arrays when growth matters. Initialize repeated
  record shapes consistently so constant field lookups can reuse slots. Preserve
  aliases, order, lifetime and precision. Use `Vector3` for temporary 3D values
  when vector semantics fit. Verify allocation or closure identity when the
  change depends on compiler behavior.
- Use direct fastcall-eligible builtins such as `string.byte(s, i)` in hot paths.
  Keep internal hot helpers local when they can be inlined. Keep direct global
  calls where imports already resolve them, and avoid dynamic environments
  (`getfenv`, `setfenv`, `loadstring`) in hot modules. Choose loops by traversal
  semantics and retain required error handling. Keep `#array` in a numeric `for`
  bound when its only use is the bound. Change distance formulas or loop syntax
  for speed only with target data.
- Apply native compilation to measured compute-bound numeric work on supported
  targets. Type hot numeric and vector arguments. Use `@native` for a single hot
  function and reserve `--!native` for modules dominated by that work. Keep
  engine-call, allocation and string-heavy paths in the normal mode unless target
  measurements show a gain. Include startup and code memory. Remove breakpoints
  and confirm `<native>` in Script Profiler.
  Inspect `debug.dumpcodesize()` in the server Command Bar when compiled size
  matters and access is available.

Use [runtime.md](../../rblx-writer/references/runtime.md) for profile/parallel scope
checks and their limits.

Sources: [Luau optimization](https://luau.org/performance/),
[Roblox native code generation](https://create.roblox.com/docs/luau/native-code-gen).
