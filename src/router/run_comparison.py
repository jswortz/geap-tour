"""Cost comparison — runs same prompts through 3 configs and generates a report."""

import asyncio
from pathlib import Path

from .complexity import classify_complexity
from .cost_tracker import estimate_cost
from .demo import DEMO_PROMPTS, AVG_INPUT_TOKENS, AVG_OUTPUT_TOKENS

CONFIGS = {
    "All Flash Lite": lambda _level: "gemini-2.5-flash-lite",
    "All Flash": lambda _level: "gemini-2.5-flash",
    "All Opus": lambda _level: "vertex_ai/claude-opus-4-7",
    "Smart Router": lambda level: {
        "low": "gemini-2.5-flash-lite",
        "medium": "gemini-2.5-flash",
        "high": "vertex_ai/claude-opus-4-7",
    }[level],
}


async def run_comparison():
    classifications = []
    for prompt, _expected in DEMO_PROMPTS:
        result = await classify_complexity(prompt)
        classifications.append(result)

    lines = [
        "# Multi-Model Cost Comparison",
        "",
        "## Thesis",
        "",
        '> "The future is multi-model — right model for right task and needs at hand."',
        "> — [gemini-model-router](https://github.com/jswortz/gemini-model-router)",
        "",
        "This demo routes prompts by complexity to the most cost-effective model:",
        "- **Low** (simple lookups) → Gemini 2.0 Flash Lite ($0.075/M input)",
        "- **Medium** (moderate reasoning) → Gemini 2.5 Flash ($0.15/M input)",
        "- **High** (deep analysis) → Claude Opus 4-7 via Vertex AI ($15/M input)",
        "",
        "## Architecture",
        "",
        "```",
        "User Prompt",
        "    |",
        "    v",
        "[Model Armor] -- safety screening (RAI, PI, jailbreak)",
        "    |",
        "    v",
        "[Router Agent] (gemini-2.5-flash-lite)",
        "    |  before_agent_callback: classify_complexity()",
        "    |  Gemini Flash Lite scores prompt 0-1, maps to low/med/high",
        "    |",
        "    |-- low ----> [Lite Agent]  gemini-2.5-flash-lite  $0.075/M in",
        "    |-- medium -> [Flash Agent] gemini-2.5-flash       $0.15/M in",
        "    |-- high ---> [Opus Agent]  claude-opus-4-7        $15.00/M in",
        "```",
        "",
        "**Why not Model Armor for complexity?** Model Armor only provides safety filters",
        "(RAI, PI detection, jailbreak, malicious URI). It has no prompt complexity scoring.",
        "We use Gemini Flash Lite as a micro-classifier (~$0.00002/call).",
        "",
        "**Why not AI Gateway for routing?** The Agent Gateway operates at the network level",
        "(CLIENT_TO_AGENT / AGENT_TO_ANYWHERE) with IAM and SGP policies. It cannot select",
        "models based on prompt content. Routing happens at the ADK orchestration layer.",
        "",
        "## Results",
        "",
        f"**Test set:** {len(DEMO_PROMPTS)} prompts "
        f"({sum(1 for c in classifications if c.level == 'low')} low, "
        f"{sum(1 for c in classifications if c.level == 'medium')} medium, "
        f"{sum(1 for c in classifications if c.level == 'high')} high)",
        "",
        f"**Assumed tokens:** {AVG_INPUT_TOKENS} input, {AVG_OUTPUT_TOKENS} output per request",
        "",
        "| Configuration | Model(s) | Total Cost | vs All-Opus Savings |",
        "|--------------|----------|-----------|-------------------|",
    ]

    all_opus_cost = None
    config_costs = {}
    for config_name, model_fn in CONFIGS.items():
        total = 0.0
        for (prompt, _), result in zip(DEMO_PROMPTS, classifications):
            level = result.level if config_name == "Smart Router" else "low"
            model = model_fn(result.level)
            cost = estimate_cost(model, AVG_INPUT_TOKENS, AVG_OUTPUT_TOKENS)
            if config_name == "Smart Router":
                cost += estimate_cost("classifier", len(prompt.split()) * 2, 20)
            total += cost
        config_costs[config_name] = total
        if config_name == "All Opus":
            all_opus_cost = total

    for config_name, total in config_costs.items():
        savings = (1 - total / all_opus_cost) * 100 if all_opus_cost else 0
        savings_str = f"{savings:.1f}%" if config_name != "All Opus" else "baseline"
        lines.append(f"| {config_name} | mixed | ${total:.6f} | {savings_str} |")

    lines.extend([
        "",
        "## Per-Prompt Routing Decisions (Smart Router)",
        "",
        "| # | Prompt (truncated) | Score | Level | Model |",
        "|---|-------------------|-------|-------|-------|",
    ])
    for i, ((prompt, _), result) in enumerate(zip(DEMO_PROMPTS, classifications), 1):
        model = CONFIGS["Smart Router"](result.level)
        lines.append(
            f"| {i} | {prompt[:50]}... | {result.score:.2f} | "
            f"{result.level} | {model.split('/')[-1]} |"
        )

    lines.extend([
        "",
        "## At Scale (monthly projections)",
        "",
        "| Scenario | Requests/mo | All-Opus | Smart Router | Savings |",
        "|----------|------------|----------|-------------|---------|",
    ])
    opus_per_req = estimate_cost("vertex_ai/claude-opus-4-7", AVG_INPUT_TOKENS, AVG_OUTPUT_TOKENS)
    lite_per_req = estimate_cost("gemini-2.5-flash-lite", AVG_INPUT_TOKENS, AVG_OUTPUT_TOKENS)
    flash_per_req = estimate_cost("gemini-2.5-flash", AVG_INPUT_TOKENS, AVG_OUTPUT_TOKENS)

    for name, count, low_pct, med_pct, high_pct in [
        ("Light usage", 1_000, 0.70, 0.20, 0.10),
        ("Medium usage", 10_000, 0.60, 0.25, 0.15),
        ("Heavy usage", 100_000, 0.50, 0.30, 0.20),
    ]:
        all_opus = count * opus_per_req
        routed = count * (
            low_pct * lite_per_req
            + med_pct * flash_per_req
            + high_pct * opus_per_req
        )
        savings = (1 - routed / all_opus) * 100
        lines.append(
            f"| {name} | {count:,} | ${all_opus:,.2f} | ${routed:,.2f} | {savings:.0f}% |"
        )

    lines.extend([
        "",
        "## Limitations",
        "",
        "- Model Armor's `ModelArmorConfig` only works with Gemini models; "
        "the Opus agent uses client-side guardrails only",
        "- Claude Opus 4-7 availability may vary by region (us-east5, global endpoint)",
        "- Classifier adds ~100-200ms latency per request",
        "- Cost comparison uses list pricing; enterprise discounts change ratios",
        "- Token counts are estimated averages, not measured from actual API responses",
        "",
        "## Connection to gemini-model-router",
        "",
        "The [gemini-model-router](https://github.com/jswortz/gemini-model-router) demonstrated",
        "35% cost savings with a 4-backend router (Gemma4, Gemini, Claude, Vertex API) using",
        "embedding-based classification. This demo validates the same thesis using GCP-native",
        "infrastructure (ADK + Model Armor + Gateway) with an LLM-as-classifier approach.",
        "The key insight is identical: **you pay for what you need** — most prompts don't",
        "require frontier-model reasoning.",
    ])

    report = "\n".join(lines)
    output_path = Path("docs/multi_model_cost_comparison.md")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report)
    print(report)
    print(f"\nReport saved to {output_path}")


if __name__ == "__main__":
    asyncio.run(run_comparison())
