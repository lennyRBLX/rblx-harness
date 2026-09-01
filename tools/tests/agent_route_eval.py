#!/usr/bin/env python3
"""Compare current Claude role routes with approved Opus candidates."""

import argparse
import json
import os
import shlex
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
GATES = os.path.join(ROOT, "shared", "gates")
sys.path.insert(0, GATES)
import record_check  # noqa: E402

BASELINE = {
    "researcher": ("sonnet", "max"),
    "maintainer": ("sonnet", "high"),
    "optimizer": ("opus", "high"),
    "debugger": ("opus", "xhigh"),
    "reviewer": ("opus", "high"),
}
CANDIDATE = {
    "researcher": ("opus", "medium"),
    "maintainer": ("opus", "low"),
    "optimizer": ("opus", "medium"),
    "debugger": ("opus", "medium"),
    "reviewer": ("opus", "low"),
}


def agent_body(role):
    path = os.path.join(ROOT, "claude", "agents", role + ".md")
    text = open(path, encoding="utf-8").read()
    return text.split("\n---\n", 1)[1].strip()


def usage_fields(payload):
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    model_usage = payload.get("modelUsage") if isinstance(payload.get("modelUsage"), dict) else {}
    if model_usage:
        usage = next(iter(model_usage.values())) if len(model_usage) == 1 else usage
    aliases = {
        "input_tokens": ("input_tokens", "inputTokens"),
        "output_tokens": ("output_tokens", "outputTokens"),
        "cache_read_tokens": ("cache_read_input_tokens", "cacheReadInputTokens"),
        "cache_write_tokens": ("cache_creation_input_tokens", "cacheCreationInputTokens"),
    }
    return {
        label: next((int(usage[key]) for key in keys if isinstance(usage.get(key), (int, float))), 0)
        for label, keys in aliases.items()
    }


def run_route(command, case, label, route):
    model, effort = route
    prompt = (
        case["prompt"]
        + "\nPreserve all required facts. Obey the role Return schema exactly; emit no extra text."
    )
    argv = command + [
        "--bare",
        "-p",
        "--model",
        model,
        "--effort",
        effort,
        "--tools",
        "",
        "--no-session-persistence",
        "--output-format",
        "json",
        "--system-prompt",
        agent_body(case["role"]),
        prompt,
    ]
    started = time.monotonic()
    proc = subprocess.run(argv, cwd=ROOT, text=True, capture_output=True, timeout=300)
    wall_ms = round((time.monotonic() - started) * 1000)
    try:
        payload = json.loads(proc.stdout)
    except (TypeError, ValueError):
        payload = {}
    output = str(payload.get("result") or "").strip()
    problems, _ = record_check.parse_return(case["role"], output)
    required = {fact: fact.casefold() in output.casefold() for fact in case["required"]}
    verdict = output.startswith("%s: %s" % (case["role"], case["verdict"]))
    result = {
        "label": label,
        "model": model,
        "effort": effort,
        "exit": proc.returncode,
        "latency_ms": wall_ms,
        "schema": not problems,
        "verdict": verdict,
        "required": required,
        "accepted": proc.returncode == 0 and not problems and verdict and all(required.values()),
        "retries": 0,
        "cost_usd": payload.get("total_cost_usd", payload.get("totalCostUSD", 0)),
        "output": output,
    }
    result.update(usage_fields(payload))
    if proc.returncode:
        result["error"] = (proc.stderr or proc.stdout).strip()[:2000]
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--command", default=os.environ.get("CLAUDE_COMMAND", "claude"))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    corpus = json.load(open(os.path.join(HERE, "agent_route_corpus.json"), encoding="utf-8"))
    command = shlex.split(args.command)
    results = []
    for case in corpus["cases"]:
        role = case["role"]
        baseline = run_route(command, case, "baseline", BASELINE[role])
        candidate = run_route(command, case, "candidate", CANDIDATE[role])
        improved = any(
            candidate[key] < baseline[key]
            for key in ("output_tokens", "latency_ms", "cost_usd")
            if isinstance(candidate.get(key), (int, float)) and isinstance(baseline.get(key), (int, float))
        )
        promote = candidate["accepted"] and (not baseline["accepted"] or improved)
        results.append({"role": role, "baseline": baseline, "candidate": candidate, "promote": promote})
    report = {"schema": 1, "corpus": "agent_route_corpus.json", "results": results}
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({item["role"]: item["promote"] for item in results}, sort_keys=True))
    return 0 if all(item["candidate"]["accepted"] for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
