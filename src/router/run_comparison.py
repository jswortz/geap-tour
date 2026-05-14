"""Cost comparison — runs same prompts through configs and generates a 5-tier report."""

import asyncio
from pathlib import Path

from .complexity import classify_complexity
from .cost_tracker import estimate_cost
from .demo import DEMO_PROMPTS, MODEL_MAP, AVG_INPUT_TOKENS, AVG_OUTPUT_TOKENS

CONFIGS = {
    "All Flash Lite": lambda _level: "gemini-2.5-flash-lite",
    "All Flash": lambda _level: "gemini-2.5-flash",
    "All Pro": lambda _level: "gemini-2.5-pro",
    "All Opus": lambda _level: "claude-opus-4-6",
    "5-Tier Router": lambda level: MODEL_MAP[level],
}


async def run_comparison():
    classifications = []
    for prompt, _expected in DEMO_PROMPTS:
        result = await classify_complexity(prompt)
        classifications.append(result)

    level_counts = {}
    for c in classifications:
        level_counts[c.level] = level_counts.get(c.level, 0) + 1

    level_summary = ", ".join(f"{count} {level}" for level, count in sorted(level_counts.items()))

    lines = [
        "# Multi-Model Cost Comparison (5-Tier Router)",
        "",
        "## Architecture",
        "",
        "```",
        "User Prompt",
        "    |",
        "    v",
        "[Model Armor] -- safety screening",
        "    |",
        "    v",
        "[Router Agent] (gemini-2.5-flash-lite)",
        "    |  before_agent_callback: classify_complexity()",
        "    |  Scores prompt 0-1, maps to 5 tiers",
        "    |",
        "    |-- low ----------> [Lite Agent]   gemini-2.5-flash-lite  $0.075/M in",
        "    |-- medium_low ----> [Flash Agent]  gemini-2.5-flash       $0.15/M in",
        "    |-- medium --------> [Pro Agent]    gemini-2.5-pro         $1.25/M in",
        "    |-- medium_high ---> [Sonnet Agent] claude-sonnet-4-6      $3.00/M in",
        "    |-- high ----------> [Opus Agent]   claude-opus-4-6       $15.00/M in",
        "```",
        "",
        "## Results",
        "",
        f"**Test set:** {len(DEMO_PROMPTS)} prompts ({level_summary})",
        f"**Assumed tokens:** {AVG_INPUT_TOKENS} input, {AVG_OUTPUT_TOKENS} output per request",
        "",
        "| Configuration | Total Cost | vs All-Opus Savings |",
        "|--------------|-----------|-------------------|",
    ]

    all_opus_cost = None
    config_costs = {}
    for config_name, model_fn in CONFIGS.items():
        total = 0.0
        for (prompt, _), result in zip(DEMO_PROMPTS, classifications):
            model = model_fn(result.level)
            cost = estimate_cost(model, AVG_INPUT_TOKENS, AVG_OUTPUT_TOKENS)
            if config_name == "5-Tier Router":
                cost += estimate_cost("classifier", len(prompt.split()) * 2, 20)
            total += cost
        config_costs[config_name] = total
        if config_name == "All Opus":
            all_opus_cost = total

    for config_name, total in config_costs.items():
        savings = (1 - total / all_opus_cost) * 100 if all_opus_cost else 0
        savings_str = f"{savings:.1f}%" if config_name != "All Opus" else "baseline"
        lines.append(f"| {config_name} | ${total:.6f} | {savings_str} |")

    lines.extend([
        "",
        "## Per-Prompt Routing Decisions (5-Tier Router)",
        "",
        "| # | Prompt (truncated) | Score | Level | Model |",
        "|---|-------------------|-------|-------|-------|",
    ])
    for i, ((prompt, _), result) in enumerate(zip(DEMO_PROMPTS, classifications), 1):
        model = MODEL_MAP[result.level]
        lines.append(
            f"| {i} | {prompt[:50]}... | {result.score:.2f} | "
            f"{result.level} | {model.split('/')[-1]} |"
        )

    lines.extend([
        "",
        "## At Scale (monthly projections)",
        "",
        "| Scenario | Requests/mo | All-Opus | 5-Tier Router | Savings |",
        "|----------|------------|----------|--------------|---------|",
    ])
    opus_per_req = estimate_cost("claude-opus-4-6", AVG_INPUT_TOKENS, AVG_OUTPUT_TOKENS)
    lite_per_req = estimate_cost("gemini-2.5-flash-lite", AVG_INPUT_TOKENS, AVG_OUTPUT_TOKENS)
    flash_per_req = estimate_cost("gemini-2.5-flash", AVG_INPUT_TOKENS, AVG_OUTPUT_TOKENS)
    pro_per_req = estimate_cost("gemini-2.5-pro", AVG_INPUT_TOKENS, AVG_OUTPUT_TOKENS)
    sonnet_per_req = estimate_cost("claude-sonnet-4-6", AVG_INPUT_TOKENS, AVG_OUTPUT_TOKENS)

    for name, count, low_pct, mlow_pct, med_pct, mhigh_pct, high_pct in [
        ("Light usage", 1_000, 0.40, 0.25, 0.20, 0.10, 0.05),
        ("Medium usage", 10_000, 0.30, 0.25, 0.25, 0.12, 0.08),
        ("Heavy usage", 100_000, 0.25, 0.25, 0.25, 0.15, 0.10),
    ]:
        all_opus = count * opus_per_req
        routed = count * (
            low_pct * lite_per_req
            + mlow_pct * flash_per_req
            + med_pct * pro_per_req
            + mhigh_pct * sonnet_per_req
            + high_pct * opus_per_req
        )
        savings = (1 - routed / all_opus) * 100
        lines.append(
            f"| {name} | {count:,} | ${all_opus:,.2f} | ${routed:,.2f} | {savings:.0f}% |"
        )

    report = "\n".join(lines)
    output_path = Path("docs/multi_model_cost_comparison.md")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report)
    print(report)
    print(f"\nReport saved to {output_path}")


if __name__ == "__main__":
    asyncio.run(run_comparison())
