# Agent model comparisons

Inherit session settings unless the user configures overrides. Read role constraints
in `openai/agents/*.toml` or `anthropic/agents/*.md`. For setting changes, use current
[Codex](https://learn.chatgpt.com/docs/agent-configuration/subagents) or
[Claude Code](https://code.claude.com/docs/en/sub-agents) guidance.

Compare equal workloads; record model/version, retries, missed rules, repairs and
human reruns. Separate input/cached/output/reasoning usage, latency and cost.
Benchmark cost is not a session bill; pass@4 is not single-attempt accuracy.
