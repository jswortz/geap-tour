"""Generate cross-model experiment analysis report with visualizations.

Reads experiment results JSON and produces charts + markdown report.

Usage:
    uv run python scripts/generate_cross_model_report.py
    uv run python scripts/generate_cross_model_report.py --input eval_outputs/cross_model_*.json
"""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

DOCS_DIR = Path("docs")
CHARTS_DIR = DOCS_DIR / "charts" / "experiment"
EVAL_DIR = Path("eval_outputs")

AGENTS = ["lite_agent", "flash_agent", "pro_agent", "sonnet_agent", "opus_agent"]
AGENT_LABELS = ["Lite", "Flash", "Pro", "Sonnet", "Opus"]
TIERS = ["low", "medium", "high"]

AGENT_COSTS = {
    "lite_agent": 0.30,
    "flash_agent": 0.60,
    "pro_agent": 10.00,
    "sonnet_agent": 15.00,
    "opus_agent": 75.00,
}

AGENT_COLORS = {
    "lite_agent": "#A8D5BA",
    "flash_agent": "#4285F4",
    "pro_agent": "#34A853",
    "sonnet_agent": "#FF6B35",
    "opus_agent": "#EA4335",
}

METRIC_LABELS = {
    "final_response_quality_v1": "Quality",
    "hallucination_v1": "Hallucination",
    "safety_v1": "Safety",
    "tool_use_quality_v1": "Tool Use",
    "instruction_following_v1": "Instruction",
    "final_response_match_v2": "Response Match",
}


def load_results(input_path: str = None) -> dict:
    """Load experiment results from JSON."""
    if input_path:
        with open(input_path) as f:
            return json.load(f)
    files = sorted(EVAL_DIR.glob("cross_model_*.json"))
    if not files:
        raise FileNotFoundError("No cross_model_*.json files found in eval_outputs/")
    with open(files[-1]) as f:
        return json.load(f)


def get_score(results: dict, agent: str, tier: str, metric: str) -> float:
    """Extract a specific score from results."""
    key = f"{agent}_{tier}"
    run = results.get("runs", {}).get(key, {})
    metrics = run.get("metrics", {})
    for k, v in metrics.items():
        if metric in k:
            return float(v)
    return 0.0


def get_avg_score(results: dict, agent: str, tier: str) -> float:
    """Get average score across all metrics for an agent-tier combo."""
    key = f"{agent}_{tier}"
    run = results.get("runs", {}).get(key, {})
    metrics = run.get("metrics", {})
    vals = [float(v) for v in metrics.values() if float(v) > 0]
    return sum(vals) / len(vals) if vals else 0.0


def generate_tier_heatmap(results: dict):
    """5×3 heatmap: models × tiers, colored by avg quality."""
    data = np.zeros((len(AGENTS), len(TIERS)))
    for i, agent in enumerate(AGENTS):
        for j, tier in enumerate(TIERS):
            data[i, j] = get_avg_score(results, agent, tier)

    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(data, cmap="RdYlGn", aspect="auto", vmin=0, vmax=1)

    ax.set_xticks(range(len(TIERS)))
    ax.set_yticks(range(len(AGENTS)))
    ax.set_xticklabels([t.title() for t in TIERS])
    ax.set_yticklabels(AGENT_LABELS)

    for i in range(len(AGENTS)):
        for j in range(len(TIERS)):
            color = "black" if data[i, j] > 0.4 else "white"
            ax.text(j, i, f"{data[i, j]:.2f}", ha="center", va="center", color=color, fontsize=12)

    ax.set_title("Average Quality Score — Models × Complexity Tiers")
    fig.colorbar(im, ax=ax, label="Avg Score")
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "tier_comparison_heatmap.png", dpi=150)
    plt.close()
    print(f"  Generated: tier_comparison_heatmap.png")


def generate_tier_bar_chart(results: dict, tier: str):
    """Grouped bar chart for a single tier across all models."""
    metrics = list(METRIC_LABELS.keys())
    n_metrics = len(metrics)
    n_agents = len(AGENTS)

    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(n_agents)
    width = 0.12
    colors = plt.cm.Set2(np.linspace(0, 1, n_metrics))

    for i, metric in enumerate(metrics):
        values = [get_score(results, a, tier, metric) for a in AGENTS]
        ax.bar(x + i * width, values, width, label=METRIC_LABELS[metric], color=colors[i])

    ax.set_xlabel("Model")
    ax.set_ylabel("Score")
    ax.set_title(f"{tier.title()} Complexity — All Models")
    ax.set_xticks(x + width * (n_metrics - 1) / 2)
    ax.set_xticklabels(AGENT_LABELS)
    ax.legend(fontsize=8)
    ax.set_ylim(0, 1.15)
    ax.axhline(y=0.6, color="red", linestyle="--", alpha=0.3)
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    plt.savefig(CHARTS_DIR / f"tier_{tier}_bar.png", dpi=150)
    plt.close()
    print(f"  Generated: tier_{tier}_bar.png")


def generate_quality_degradation(results: dict):
    """Line chart: quality by tier for each model."""
    fig, ax = plt.subplots(figsize=(10, 6))

    for agent in AGENTS:
        scores = [get_avg_score(results, agent, tier) for tier in TIERS]
        label = agent.replace("_agent", "").title()
        ax.plot(TIERS, scores, "o-", linewidth=2, markersize=8,
                label=f"{label} (${AGENT_COSTS[agent]}/M)", color=AGENT_COLORS[agent])

    ax.set_xlabel("Complexity Tier")
    ax.set_ylabel("Average Quality Score")
    ax.set_title("Quality Degradation Across Complexity Tiers")
    ax.legend()
    ax.set_ylim(0, 1.05)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "quality_degradation.png", dpi=150)
    plt.close()
    print(f"  Generated: quality_degradation.png")


def generate_cost_quality_per_tier(results: dict):
    """Cost vs quality scatter, one series per tier."""
    fig, ax = plt.subplots(figsize=(10, 7))

    tier_colors = {"low": "#34A853", "medium": "#FBBC04", "high": "#EA4335"}

    for tier in TIERS:
        for agent in AGENTS:
            cost = AGENT_COSTS[agent]
            quality = get_avg_score(results, agent, tier)
            ax.scatter(cost, quality, s=150, c=tier_colors[tier], zorder=5,
                      edgecolors="black", linewidth=0.5)
            if tier == "low":
                ax.annotate(agent.replace("_agent", "").title(), (cost, quality),
                           textcoords="offset points", xytext=(8, 5), fontsize=8)

    from matplotlib.patches import Patch
    legend = [Patch(facecolor=c, label=t.title()) for t, c in tier_colors.items()]
    ax.legend(handles=legend, title="Complexity Tier")

    ax.set_xlabel("Output Cost ($/M tokens)")
    ax.set_ylabel("Average Quality Score")
    ax.set_title("Cost vs Quality by Complexity Tier")
    ax.set_xscale("log")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "cost_quality_per_tier.png", dpi=150)
    plt.close()
    print(f"  Generated: cost_quality_per_tier.png")


def generate_diminishing_returns(results: dict):
    """Quality gain per dollar for each tier."""
    fig, ax = plt.subplots(figsize=(10, 6))

    for tier in TIERS:
        costs = [AGENT_COSTS[a] for a in AGENTS]
        qualities = [get_avg_score(results, a, tier) for a in AGENTS]
        qpd = [q / c if c > 0 else 0 for q, c in zip(qualities, costs)]
        ax.plot(costs, qpd, "o-", linewidth=2, markersize=8, label=tier.title())

    ax.set_xlabel("Output Cost ($/M tokens)")
    ax.set_ylabel("Quality per Dollar")
    ax.set_title("Diminishing Returns — Quality per Dollar by Tier")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "diminishing_returns.png", dpi=150)
    plt.close()
    print(f"  Generated: diminishing_returns.png")


def generate_report(results: dict):
    """Generate markdown report."""
    lines = []
    lines.append("# Cross-Model Complexity Experiment\n")
    lines.append("## Experiment Overview\n")
    lines.append(
        "This experiment tests all 5 model-tier agents on all 3 complexity levels "
        "to measure how each model handles queries above and below its intended tier.\n"
    )
    lines.append("**Matrix:** 5 models x 3 tiers = 15 eval runs\n")
    lines.append("**Questions:**")
    lines.append("- Can cheap models handle complex queries adequately?")
    lines.append("- Do expensive models waste capability on simple queries?")
    lines.append("- Which model offers the best quality-per-dollar at each tier?")
    lines.append("- Where are the diminishing returns?\n")

    lines.append("## Overall Heatmap\n")
    lines.append("![Tier Heatmap](charts/experiment/tier_comparison_heatmap.png)\n")

    for tier in TIERS:
        lines.append(f"## {tier.title()} Complexity Results\n")
        lines.append(f"![{tier.title()} Bar Chart](charts/experiment/tier_{tier}_bar.png)\n")

        lines.append(f"| Model | Quality | Hallucination | Safety | Tool Use | Instruction | Match | Avg |")
        lines.append(f"|-------|---------|---------------|--------|----------|-------------|-------|-----|")
        for agent in AGENTS:
            label = agent.replace("_agent", "").title()
            scores = [get_score(results, agent, tier, m) for m in METRIC_LABELS.keys()]
            avg = get_avg_score(results, agent, tier)
            row = " | ".join(f"{s:.2f}" for s in scores)
            lines.append(f"| {label} | {row} | {avg:.2f} |")
        lines.append("")

    lines.append("## Quality Degradation\n")
    lines.append("![Quality Degradation](charts/experiment/quality_degradation.png)\n")

    lines.append("## Cost-Quality by Tier\n")
    lines.append("![Cost Quality Per Tier](charts/experiment/cost_quality_per_tier.png)\n")

    lines.append("## Diminishing Returns\n")
    lines.append("![Diminishing Returns](charts/experiment/diminishing_returns.png)\n")

    lines.append("## Model Selection Guide\n")
    lines.append("| Complexity | Recommended Model | Rationale |")
    lines.append("|------------|-------------------|-----------|")

    for tier in TIERS:
        best_agent = max(AGENTS, key=lambda a: get_avg_score(results, a, tier))
        best_score = get_avg_score(results, best_agent, tier)
        best_label = best_agent.replace("_agent", "").title()
        best_cost = AGENT_COSTS[best_agent]

        cheapest_adequate = None
        for agent in AGENTS:
            if get_avg_score(results, agent, tier) >= best_score * 0.9:
                if cheapest_adequate is None or AGENT_COSTS[agent] < AGENT_COSTS[cheapest_adequate]:
                    cheapest_adequate = agent

        if cheapest_adequate and cheapest_adequate != best_agent:
            rec = cheapest_adequate.replace("_agent", "").title()
            rec_cost = AGENT_COSTS[cheapest_adequate]
            lines.append(
                f"| {tier.title()} | **{rec}** (${rec_cost}/M) | "
                f"Within 90% of best ({best_label}) at {rec_cost/best_cost:.0%} the cost |"
            )
        else:
            lines.append(
                f"| {tier.title()} | **{best_label}** (${best_cost}/M) | Highest score ({best_score:.2f}) |"
            )
    lines.append("")

    lines.append("## Findings\n")
    lines.append("*(Auto-generated — review and refine based on chart analysis)*\n")

    report_path = DOCS_DIR / "cross_model_experiment.md"
    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    print(f"\nReport saved to: {report_path}")


def main(input_path: str = None):
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading experiment results...")
    results = load_results(input_path)
    n_runs = len(results.get("runs", {}))
    print(f"  Loaded {n_runs} eval runs\n")

    print("Generating charts...")
    generate_tier_heatmap(results)
    for tier in TIERS:
        generate_tier_bar_chart(results, tier)
    generate_quality_degradation(results)
    generate_cost_quality_per_tier(results)
    generate_diminishing_returns(results)

    print("\nGenerating report...")
    generate_report(results)

    print("\nDone!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, default=None, help="Path to results JSON")
    args = parser.parse_args()
    main(args.input)
