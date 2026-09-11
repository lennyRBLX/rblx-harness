# Model evaluation

The primary and specialist agents inherit session model settings unless the user
configures an override. Read `openai/agents/*.toml` for role constraints. Use
[current Codex guidance](https://learn.chatgpt.com/docs/agent-configuration/subagents)
when changing model or reasoning settings.

For comparisons, record workload, model/version, retries, missed restrictions,
repairs, and human reruns. Keep input, cached input, output, reasoning, latency,
and cost separate. Benchmark costs are not session bills; pass@4 is not
single-attempt accuracy. Missing measurements remain unknown.
