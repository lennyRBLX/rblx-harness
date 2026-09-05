# Model evaluation

For role/model changes or evaluation, read current `openai/agents/*.toml`.
The session selects the primary model. Role assignments express fit, not measured
Roblox accuracy; require sources & exact MISS results.

- Check benchmark version, uncertainty intervals & scoring. pass@4 is not single-attempt accuracy. More reasoning/output does not prove accuracy; more steps do not prove higher latency. Cumulative input is not peak context.
- Keep current displayed costs separate from older artifacts. Benchmark costs are not session bills; account for API tiers, cache, long context & Fast settings. Recheck when roles, models, prices or tasks change.
- Local comparisons must count retries, orchestration, repairs, missed restrictions, test defects & human reruns. Record input, cached input, output & reasoning separately; avoid double-counting reasoning.
- Missing baseline, latency, usage or actual cost stays unknown. Updated evidence needs no session restart.
