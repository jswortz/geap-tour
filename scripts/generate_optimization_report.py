"""Generate GEPA optimization analysis report with visualizations.

Reads eval results, generates matplotlib charts, and produces a markdown report.

Usage:
    uv run python scripts/generate_optimization_report.py
"""

import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

DOCS_DIR = Path("docs")
CHARTS_DIR = DOCS_DIR / "charts"
EVAL_DIR = Path("eval_outputs")

AGENTS = {
    "lite_agent": {
        "model": "gemini-3.1-flash-lite",
        "provider": "Google",
        "input_cost": 0.075,
        "output_cost": 0.30,
        "tier": "Tier 1 — Trivial",
        "engine_id": os.environ.get("LITE_ENGINE_ID", ""),
    },
    "flash_agent": {
        "model": "gemini-3.5-flash",
        "provider": "Google",
        "input_cost": 0.15,
        "output_cost": 0.60,
        "tier": "Tier 2 — Simple",
        "engine_id": os.environ.get("FLASH_ENGINE_ID", ""),
    },
    "pro_agent": {
        "model": "gemini-3.1-pro-preview",
        "provider": "Google",
        "input_cost": 1.25,
        "output_cost": 10.00,
        "tier": "Tier 3 — Moderate",
        "engine_id": os.environ.get("PRO_ENGINE_ID", ""),
    },
    "sonnet_agent": {
        "model": "claude-sonnet-4-6",
        "provider": "Anthropic",
        "input_cost": 3.00,
        "output_cost": 15.00,
        "tier": "Tier 4 — Complex",
        "engine_id": os.environ.get("SONNET_ENGINE_ID", ""),
    },
    "opus_agent": {
        "model": "claude-opus-4-6",
        "provider": "Anthropic",
        "input_cost": 15.00,
        "output_cost": 75.00,
        "tier": "Tier 5 — Expert",
        "engine_id": os.environ.get("OPUS_ENGINE_ID", ""),
    },
}

METRICS = [
    "final_response_quality_v1",
    "hallucination_v1",
    "safety_v1",
    "tool_use_quality_v1",
    "instruction_following_v1",
    "final_response_match_v2",
]

METRIC_LABELS = {
    "final_response_quality_v1": "Response Quality",
    "hallucination_v1": "Hallucination",
    "safety_v1": "Safety",
    "tool_use_quality_v1": "Tool Use",
    "instruction_following_v1": "Instruction Following",
    "final_response_match_v2": "Response Match",
}

ORIGINAL_INSTRUCTIONS = {
    "lite_agent": (
        "You are a fast corporate assistant for simple queries. "
        "Give direct, concise answers. Use tools when needed. "
        "Use recalled memories to personalize responses when available."
    ),
    "flash_agent": (
        "You are a capable corporate assistant for straightforward requests. "
        "Use tools as needed and provide clear, formatted answers. "
        "Use recalled memories to personalize responses when available."
    ),
    "pro_agent": (
        "You are a thorough corporate assistant for moderately complex requests. "
        "Break down the problem, use multiple tools as needed, and provide structured answers. "
        "Use recalled memories to personalize responses when available."
    ),
    "sonnet_agent": (
        "You are an advanced corporate assistant for complex requests. "
        "Analyze across multiple domains, use several tools, and provide detailed structured output. "
        "Use recalled memories to personalize responses when available."
    ),
    "opus_agent": (
        "You are an expert corporate assistant for the most complex, high-stakes requests. "
        "Provide thorough analysis with multi-step planning. "
        "Cross-reference information across tools and present a comprehensive response. "
        "Use recalled memories to personalize responses when available."
    ),
}


def _load_scores_from_files(agent_name: str) -> list[dict[str, float]]:
    """Load all eval score sets for an agent from JSON files, sorted by timestamp."""
    results = []
    for f in sorted(EVAL_DIR.glob("batch_results_*.json")):
        with open(f) as fh:
            data = json.load(fh)
        agents = data.get("agents", {})
        if agent_name not in agents:
            continue
        metrics = agents[agent_name].get("metrics", {})
        scores = {}
        for key, detail in metrics.items():
            for m in METRICS:
                if m in key:
                    scores[m] = detail.get("score", 0.0)
        if scores:
            results.append({"timestamp": data.get("timestamp", ""), "scores": scores})
    return results


# Sonnet baseline was captured manually (eval timed out before saving)
_SONNET_BASELINE = {
    "final_response_quality_v1": 0.85,
    "hallucination_v1": 0.72,
    "safety_v1": 0.92,
    "tool_use_quality_v1": 0.31,
    "instruction_following_v1": 0.48,
    "final_response_match_v2": 0.50,
}

# GEPA cutoff: evals before this are "before", after are "after"
GEPA_CUTOFF = "2026-05-22T00:00:00"


def _split_before_after(agent_name: str) -> tuple[dict, dict]:
    """Split eval scores into before/after GEPA based on timestamp."""
    all_scores = _load_scores_from_files(agent_name)
    before = [s for s in all_scores if s["timestamp"] < GEPA_CUTOFF]
    after = [s for s in all_scores if s["timestamp"] >= GEPA_CUTOFF]

    before_scores = before[-1]["scores"] if before else {}
    after_scores = after[-1]["scores"] if after else {}

    if agent_name == "sonnet_agent" and not before_scores:
        before_scores = _SONNET_BASELINE

    return before_scores, after_scores


def load_eval_scores(agent_name: str, phase: str = "before") -> dict[str, float]:
    """Load eval scores from JSON files. Returns {metric: score}."""
    before, after = _split_before_after(agent_name)
    if phase == "before":
        return before
    return after
    scores = {}
    for f in sorted(EVAL_DIR.glob("batch_results_*.json")):
        with open(f) as fh:
            data = json.load(fh)
        agents = data.get("agents", {})
        if agent_name in agents:
            metrics = agents[agent_name].get("metrics", {})
            for key, detail in metrics.items():
                for m in METRICS:
                    if m in key:
                        scores[m] = detail.get("score", 0.0)
    return scores


def generate_baseline_comparison_chart(before_scores: dict[str, dict[str, float]]):
    """Generate grouped bar chart of baseline scores across all agents."""
    agents = list(before_scores.keys())
    n_metrics = len(METRICS)
    n_agents = len(agents)

    fig, ax = plt.subplots(figsize=(14, 7))
    x = np.arange(n_agents)
    width = 0.12

    colors = plt.cm.Set2(np.linspace(0, 1, n_metrics))

    for i, metric in enumerate(METRICS):
        values = [before_scores[a].get(metric, 0) for a in agents]
        bars = ax.bar(x + i * width, values, width, label=METRIC_LABELS[metric], color=colors[i])

    ax.set_xlabel("Agent")
    ax.set_ylabel("Score (0-1)")
    ax.set_title("Baseline Eval Scores — All Model Tiers")
    ax.set_xticks(x + width * (n_metrics - 1) / 2)
    ax.set_xticklabels([a.replace("_agent", "").title() for a in agents], rotation=0)
    ax.legend(loc="upper right", fontsize=8)
    ax.set_ylim(0, 1.15)
    ax.axhline(y=0.6, color="red", linestyle="--", alpha=0.3, label="Threshold (0.6)")
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "baseline_comparison.png", dpi=150)
    plt.close()
    print(f"  Generated: baseline_comparison.png")


def generate_before_after_chart(before: dict, after: dict):
    """Generate grouped bar chart comparing before/after scores per agent."""
    agents = list(before.keys())
    n = len(agents)

    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    axes = axes.flatten()

    for i, metric in enumerate(METRICS):
        ax = axes[i]
        b_vals = [before[a].get(metric, 0) for a in agents]
        a_vals = [after[a].get(metric, 0) for a in agents]
        x = np.arange(n)
        width = 0.35
        ax.bar(x - width/2, b_vals, width, label="Before", color="#4285F4", alpha=0.8)
        ax.bar(x + width/2, a_vals, width, label="After", color="#34A853", alpha=0.8)
        ax.set_title(METRIC_LABELS[metric], fontsize=11)
        ax.set_xticks(x)
        ax.set_xticklabels([a.replace("_agent", "").title() for a in agents], fontsize=8)
        ax.set_ylim(0, 1.1)
        ax.axhline(y=0.6, color="red", linestyle="--", alpha=0.3)
        ax.legend(fontsize=7)
        ax.grid(axis="y", alpha=0.3)

    plt.suptitle("GEPA Optimization: Before vs After", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "before_after_comparison.png", dpi=150)
    plt.close()
    print(f"  Generated: before_after_comparison.png")


def generate_improvement_delta_chart(before: dict, after: dict):
    """Generate bar chart showing score improvement per agent per metric."""
    agents = list(before.keys())
    n_metrics = len(METRICS)
    n_agents = len(agents)

    fig, ax = plt.subplots(figsize=(14, 7))
    x = np.arange(n_agents)
    width = 0.12
    colors = plt.cm.Set2(np.linspace(0, 1, n_metrics))

    for i, metric in enumerate(METRICS):
        deltas = [after[a].get(metric, 0) - before[a].get(metric, 0) for a in agents]
        ax.bar(x + i * width, deltas, width, label=METRIC_LABELS[metric], color=colors[i])

    ax.set_xlabel("Agent")
    ax.set_ylabel("Score Change")
    ax.set_title("GEPA Optimization Impact (After - Before)")
    ax.set_xticks(x + width * (n_metrics - 1) / 2)
    ax.set_xticklabels([a.replace("_agent", "").title() for a in agents])
    ax.legend(loc="lower left", fontsize=8)
    ax.axhline(y=0, color="black", linewidth=0.5)
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "improvement_delta.png", dpi=150)
    plt.close()
    print(f"  Generated: improvement_delta.png")


def generate_cost_quality_chart(scores: dict[str, dict[str, float]]):
    """Generate cost vs quality scatter plot."""
    fig, ax = plt.subplots(figsize=(10, 7))

    for agent_name, info in AGENTS.items():
        agent_scores = scores.get(agent_name, {})
        avg_quality = np.mean([v for v in agent_scores.values() if v > 0]) if agent_scores else 0
        cost = info["output_cost"]
        color = "#4285F4" if info["provider"] == "Google" else "#FF6B35"
        ax.scatter(cost, avg_quality, s=200, c=color, zorder=5, edgecolors="black", linewidth=0.5)
        ax.annotate(
            agent_name.replace("_agent", "").title(),
            (cost, avg_quality),
            textcoords="offset points",
            xytext=(10, 5),
            fontsize=9,
        )

    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor="#4285F4", label="Google (Gemini)"),
        Patch(facecolor="#FF6B35", label="Anthropic (Claude)"),
    ]
    ax.legend(handles=legend_elements, loc="lower right")

    ax.set_xlabel("Output Cost ($/M tokens)")
    ax.set_ylabel("Average Quality Score")
    ax.set_title("Cost-Quality Tradeoff — Model Tiers")
    ax.set_xscale("log")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "cost_quality_tradeoff.png", dpi=150)
    plt.close()
    print(f"  Generated: cost_quality_tradeoff.png")


def generate_heatmap(scores: dict[str, dict[str, float]], title: str, filename: str):
    """Generate heatmap of agents × metrics."""
    agents = list(scores.keys())
    data = []
    for agent in agents:
        row = [scores[agent].get(m, 0) for m in METRICS]
        data.append(row)

    data = np.array(data)
    fig, ax = plt.subplots(figsize=(12, 6))
    im = ax.imshow(data, cmap="RdYlGn", aspect="auto", vmin=0, vmax=1)

    ax.set_xticks(np.arange(len(METRICS)))
    ax.set_yticks(np.arange(len(agents)))
    ax.set_xticklabels([METRIC_LABELS[m] for m in METRICS], rotation=45, ha="right")
    ax.set_yticklabels([a.replace("_agent", "").title() for a in agents])

    for i in range(len(agents)):
        for j in range(len(METRICS)):
            text = ax.text(j, i, f"{data[i, j]:.2f}", ha="center", va="center",
                          color="black" if data[i, j] > 0.4 else "white", fontsize=10)

    ax.set_title(title)
    fig.colorbar(im, ax=ax, label="Score")
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / filename, dpi=150)
    plt.close()
    print(f"  Generated: {filename}")


def generate_radar_chart(agent_name: str, before: dict, after: dict = None):
    """Generate radar/spider chart for a single agent."""
    metrics = list(METRIC_LABELS.values())
    n = len(metrics)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))

    values = [before.get(m, 0) for m in METRICS]
    values += values[:1]
    ax.plot(angles, values, "o-", linewidth=2, label="Before", color="#4285F4")
    ax.fill(angles, values, alpha=0.15, color="#4285F4")

    if after:
        values_after = [after.get(m, 0) for m in METRICS]
        values_after += values_after[:1]
        ax.plot(angles, values_after, "o-", linewidth=2, label="After", color="#34A853")
        ax.fill(angles, values_after, alpha=0.15, color="#34A853")

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(metrics, size=9)
    ax.set_ylim(0, 1)
    ax.set_title(f"{agent_name.replace('_agent', '').title()} Agent", size=14, pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1))

    plt.tight_layout()
    plt.savefig(CHARTS_DIR / f"radar_{agent_name}.png", dpi=150)
    plt.close()
    print(f"  Generated: radar_{agent_name}.png")


def generate_report(before_scores: dict, after_scores: dict = None):
    """Generate the markdown report."""
    lines = []
    lines.append("# GEPA Optimization Analysis — Multi-Model Agent Tier\n")
    lines.append("## Executive Summary\n")
    lines.append(
        "This report analyzes the impact of GEPA (Gemini Evolutionary Prompt Algorithm) "
        "optimization on 5 standalone agents spanning a 250x cost range across Google Gemini "
        "and Anthropic Claude model families. Each agent was evaluated with 6 metrics across "
        "20 test cases (10 travel + 10 expense) before and after prompt optimization.\n"
    )

    lines.append("## Agent Overview\n")
    lines.append("| Agent | Model | Provider | Output $/M | Tier | Engine ID |")
    lines.append("|-------|-------|----------|-----------|------|-----------|")
    for name, info in AGENTS.items():
        lines.append(
            f"| {name.replace('_agent','').title()} | `{info['model']}` | {info['provider']} "
            f"| ${info['output_cost']:.2f} | {info['tier']} | `{info['engine_id']}` |"
        )
    lines.append("")

    lines.append("## Baseline Eval Scores\n")
    lines.append("![Baseline Comparison](charts/baseline_comparison.png)\n")
    lines.append("| Agent | Quality | Hallucination | Safety | Tool Use | Instruction | Response Match |")
    lines.append("|-------|---------|---------------|--------|----------|-------------|----------------|")
    for name in AGENTS:
        s = before_scores.get(name, {})
        lines.append(
            f"| {name.replace('_agent','').title()} "
            f"| {s.get('final_response_quality_v1', 0):.2f} "
            f"| {s.get('hallucination_v1', 0):.2f} "
            f"| {s.get('safety_v1', 0):.2f} "
            f"| {s.get('tool_use_quality_v1', 0):.2f} "
            f"| {s.get('instruction_following_v1', 0):.2f} "
            f"| {s.get('final_response_match_v2', 0):.2f} |"
        )
    lines.append("")

    lines.append("## Cost-Quality Tradeoff\n")
    lines.append("![Cost-Quality Tradeoff](charts/cost_quality_tradeoff.png)\n")

    cost_data = []
    for name, info in AGENTS.items():
        s = before_scores.get(name, {})
        avg = np.mean([v for v in s.values() if v > 0]) if s else 0
        quality_per_dollar = avg / info["output_cost"] if info["output_cost"] > 0 else 0
        cost_data.append((name, info["output_cost"], avg, quality_per_dollar))

    lines.append("| Agent | Output $/M | Avg Quality | Quality/$ |")
    lines.append("|-------|-----------|-------------|-----------|")
    for name, cost, avg, qpd in sorted(cost_data, key=lambda x: x[1]):
        lines.append(f"| {name.replace('_agent','').title()} | ${cost:.2f} | {avg:.2f} | {qpd:.4f} |")
    lines.append("")

    lines.append("## Metric Heatmap (Before)\n")
    lines.append("![Metric Heatmap Before](charts/metric_heatmap_baseline.png)\n")

    if after_scores:
        lines.append("## Metric Heatmap (After GEPA)\n")
        lines.append("![Metric Heatmap After](charts/metric_heatmap_after.png)\n")

        lines.append("## Before vs After Comparison\n")
        lines.append("![Before After Comparison](charts/before_after_comparison.png)\n")

        lines.append("## Improvement Delta\n")
        lines.append("![Improvement Delta](charts/improvement_delta.png)\n")

        lines.append("### Before vs After Scores\n")
        lines.append("| Agent | Metric | Before | After | Delta | Change |")
        lines.append("|-------|--------|--------|-------|-------|--------|")
        for name in AGENTS:
            for m in METRICS:
                b = before_scores.get(name, {}).get(m, 0)
                a = after_scores.get(name, {}).get(m, 0)
                delta = a - b
                pct = f"{delta/b*100:+.0f}%" if b > 0 else "N/A"
                indicator = "+" if delta > 0 else ""
                lines.append(
                    f"| {name.replace('_agent','').title()} | {METRIC_LABELS[m]} "
                    f"| {b:.2f} | {a:.2f} | {indicator}{delta:.2f} | {pct} |"
                )
        lines.append("")

    lines.append("## Per-Agent Radar Charts (Before vs After)\n")
    for name in AGENTS:
        lines.append(f"### {name.replace('_agent','').title()} Agent\n")
        lines.append(f"![{name} Radar](charts/radar_{name}.png)\n")

    lines.append("## Before/After Instruction Comparison\n")
    for name in AGENTS:
        lines.append(f"### {name.replace('_agent','').title()} Agent\n")
        lines.append("**Before (generic):**")
        lines.append(f"```\n{ORIGINAL_INSTRUCTIONS[name]}\n```\n")
        lines.append("**After (GEPA-optimized):**")
        lines.append("```\n(Pending optimization results)\n```\n")

    lines.append("## Recommendations\n")
    lines.append("- Agents with the largest instruction improvements should be redeployed with GEPA-optimized prompts")
    lines.append("- Re-run optimization after any changes to MCP tool schemas or policy limits")
    lines.append("- Consider running GEPA with more eval cases (20+) for agents that returned baseline instructions\n")

    report_path = DOCS_DIR / "gepa_optimization_analysis.md"
    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    print(f"\nReport saved to: {report_path}")


def main():
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading baseline eval scores...")
    before_scores = {}
    for name in AGENTS:
        scores = load_eval_scores(name)
        before_scores[name] = scores
        print(f"  {name}: {len(scores)} metrics loaded")

    print("\nLoading post-GEPA eval scores...")
    after_scores = {}
    for name in AGENTS:
        scores = load_eval_scores(name, phase="after")
        after_scores[name] = scores
        print(f"  {name}: {len(scores)} metrics loaded")

    print("\nGenerating charts...")
    generate_baseline_comparison_chart(before_scores)
    generate_cost_quality_chart(after_scores)
    generate_heatmap(before_scores, "Baseline Eval Scores (Before GEPA)", "metric_heatmap_baseline.png")
    generate_heatmap(after_scores, "Post-GEPA Eval Scores (After)", "metric_heatmap_after.png")
    generate_before_after_chart(before_scores, after_scores)
    generate_improvement_delta_chart(before_scores, after_scores)

    for name in AGENTS:
        generate_radar_chart(name, before_scores.get(name, {}), after_scores.get(name))

    print("\nGenerating report...")
    generate_report(before_scores, after_scores)

    print("\nDone!")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    main()
