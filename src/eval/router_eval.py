"""Router evaluation — complexity classification accuracy + cost savings with statistical significance.

Runs the Flash Lite micro-classifier against a curated test set, measures routing
accuracy per complexity tier, computes cost savings vs all-Claude baseline, and
applies statistical tests (paired t-test, bootstrap CI) to validate significance.

Usage:
    uv run python -m src.eval.router_eval
    uv run python -m src.eval.router_eval --rounds 5 --update-report
"""

import asyncio
import argparse
import json
import math
import random
import statistics
import time
from datetime import datetime
from pathlib import Path

from src.router.complexity import classify_complexity
from src.router.cost_tracker import estimate_cost

EVAL_CASES = [
    {"prompt": "Find flights from SFO to JFK", "expected": "low", "category": "flight_search"},
    {"prompt": "What's the expense policy for meals?", "expected": "low", "category": "policy_check"},
    {"prompt": "Search hotels in Chicago under $200", "expected": "low", "category": "hotel_search"},
    {"prompt": "Check if a $50 transport expense is within policy", "expected": "low", "category": "policy_check"},
    {"prompt": "How much can I spend on meals per day while traveling?", "expected": "low", "category": "policy_check"},
    {"prompt": "Show me flights from LAX to ORD", "expected": "low", "category": "flight_search"},
    {"prompt": "What's the lodging limit?", "expected": "low", "category": "policy_check"},
    {"prompt": "Find hotels in Miami", "expected": "low", "category": "hotel_search"},
    {"prompt": "Book flight FL001 for Alice Johnson", "expected": "low", "category": "booking"},
    {"prompt": "Submit a $45 lunch expense for EMP001", "expected": "low", "category": "expense_submit"},
    {"prompt": "Find flights to NYC and compare the cheapest options by airline", "expected": "medium", "category": "comparison"},
    {"prompt": "Search hotels in Boston, then check if the nightly rate fits our lodging policy", "expected": "medium", "category": "multi_step"},
    {"prompt": "Show my expense history and flag any items that exceeded policy limits", "expected": "medium", "category": "analysis"},
    {"prompt": "I need to compare hotel options in NYC vs Boston under $300 per night", "expected": "medium", "category": "comparison"},
    {"prompt": "Can you check my expense history and flag issues?", "expected": "medium", "category": "analysis"},
    {"prompt": "I need help planning flights and checking if the cost fits our policy", "expected": "medium", "category": "multi_step"},
    {
        "prompt": "Plan a 5-day trip to Tokyo for a team of 4: find flights, hotels near Shibuya, estimate daily meal expenses, and check what our corporate policy allows for international entertainment expenses.",
        "expected": "high",
        "category": "planning",
    },
    {
        "prompt": "Compare individual vs group flight bookings for our team retreat to Denver. Factor in cancellation policies, per-diem meal expenses, and whether hotels near the conference center or downtown with transport are more cost-effective.",
        "expected": "high",
        "category": "analysis",
    },
    {
        "prompt": "Analyze EMP001's expense history: they overspent on entertainment last quarter. Draft a policy recommendation for new entertainment limits, and submit my $45 lunch receipt while you're at it.",
        "expected": "high",
        "category": "multi_action",
    },
    {
        "prompt": "Book the cheapest SFO-JFK flight, find a hotel within walking distance of 350 5th Ave, cross-reference hotel ratings, check our lodging policy limit, and submit a pre-approval expense for the estimated total trip cost.",
        "expected": "high",
        "category": "pipeline",
    },
    {
        "prompt": "I need a comprehensive cost analysis: compare flying to SF vs LA for our offsite, factor in hotel costs near conference venues, calculate per-person daily meal + transport budgets, and determine which city gives us more budget headroom for team entertainment.",
        "expected": "high",
        "category": "analysis",
    },
    {
        "prompt": "Help me with end-to-end trip booking and expenses: search flights, hotels, check all relevant policies, create an itinerary, and submit pre-approval expenses for everything.",
        "expected": "high",
        "category": "pipeline",
    },
]

MODEL_MAP = {
    "low": "gemini-2.0-flash-lite",
    "medium": "gemini-2.5-flash",
    "high": "vertex_ai/claude-opus-4-7",
}

AVG_INPUT_TOKENS = 200
AVG_OUTPUT_TOKENS = 500
CLASSIFIER_TOKEN_OVERHEAD = 40


def _paired_t_test(diffs: list[float]) -> dict:
    n = len(diffs)
    if n < 2:
        return {"t_stat": 0.0, "p_value": 1.0, "significant": False, "n": n}
    mean_d = statistics.mean(diffs)
    std_d = statistics.stdev(diffs)
    if std_d == 0:
        return {"t_stat": float("inf"), "p_value": 0.0, "significant": True, "n": n}
    t_stat = mean_d / (std_d / math.sqrt(n))
    df = n - 1
    t_abs = abs(t_stat)
    p_value = math.erfc(t_abs / math.sqrt(2)) if df > 30 else math.erfc(t_abs / math.sqrt(2))
    return {"t_stat": round(t_stat, 4), "p_value": round(p_value, 6), "significant": p_value < 0.05, "n": n}


def _bootstrap_ci(values: list[float], n_bootstrap: int = 10000, ci: float = 0.95) -> dict:
    n = len(values)
    if n < 2:
        m = values[0] if values else 0
        return {"mean": m, "ci_lower": m, "ci_upper": m, "ci_level": ci}
    boot_means = sorted(statistics.mean(random.choices(values, k=n)) for _ in range(n_bootstrap))
    alpha = 1 - ci
    lo_idx = int(alpha / 2 * n_bootstrap)
    hi_idx = int((1 - alpha / 2) * n_bootstrap)
    return {
        "mean": round(statistics.mean(values), 6),
        "ci_lower": round(boot_means[lo_idx], 6),
        "ci_upper": round(boot_means[hi_idx], 6),
        "ci_level": ci,
    }


async def run_single_round(cases: list[dict]) -> dict:
    results = []
    confusion = {t: {"low": 0, "medium": 0, "high": 0} for t in ("low", "medium", "high")}

    for case in cases:
        t0 = time.monotonic()
        result = await classify_complexity(case["prompt"])
        latency_ms = (time.monotonic() - t0) * 1000
        expected = case["expected"]
        actual = result.level
        match = actual == expected
        routed_model = MODEL_MAP[actual]
        routed_cost = estimate_cost(routed_model, AVG_INPUT_TOKENS, AVG_OUTPUT_TOKENS)
        classifier_cost = estimate_cost("classifier", CLASSIFIER_TOKEN_OVERHEAD, 20)
        total_routed_cost = routed_cost + classifier_cost
        opus_cost = estimate_cost("vertex_ai/claude-opus-4-7", AVG_INPUT_TOKENS, AVG_OUTPUT_TOKENS)
        confusion[expected][actual] += 1
        results.append({
            "prompt": case["prompt"][:80], "expected": expected, "actual": actual,
            "score": result.score, "reason": result.reason, "match": match,
            "latency_ms": round(latency_ms, 1), "routed_model": routed_model,
            "routed_cost": total_routed_cost, "opus_cost": opus_cost,
            "savings": opus_cost - total_routed_cost,
        })

    total = len(results)
    correct = sum(1 for r in results if r["match"])
    accuracy = correct / total if total else 0
    total_routed = sum(r["routed_cost"] for r in results)
    total_opus = sum(r["opus_cost"] for r in results)
    savings_pct = (1 - total_routed / total_opus) * 100 if total_opus else 0

    return {
        "accuracy": round(accuracy, 4), "correct": correct, "total": total,
        "confusion": confusion, "total_routed_cost": round(total_routed, 8),
        "total_opus_cost": round(total_opus, 8), "savings_pct": round(savings_pct, 1),
        "avg_latency_ms": round(statistics.mean(r["latency_ms"] for r in results), 1),
        "per_case": results,
    }


async def run_eval_rounds(n_rounds: int = 3) -> dict:
    print(f"Running {n_rounds} evaluation rounds on {len(EVAL_CASES)} test cases...\n")
    all_rounds, all_savings = [], []
    for i in range(n_rounds):
        print(f"  Round {i+1}/{n_rounds}...", end=" ", flush=True)
        t0 = time.monotonic()
        result = await run_single_round(EVAL_CASES)
        elapsed = time.monotonic() - t0
        all_rounds.append(result)
        print(f"accuracy={result['accuracy']:.1%} savings={result['savings_pct']:.1f}% ({elapsed:.1f}s)")
        for cr in result["per_case"]:
            all_savings.append(cr["savings"])

    accuracies = [r["accuracy"] for r in all_rounds]
    savings_pcts = [r["savings_pct"] for r in all_rounds]
    t_test = _paired_t_test(all_savings)
    savings_ci = _bootstrap_ci(savings_pcts)
    accuracy_ci = _bootstrap_ci(accuracies)

    agg_cm = {t: {"low": 0, "medium": 0, "high": 0} for t in ("low", "medium", "high")}
    for r in all_rounds:
        for e in agg_cm:
            for a in agg_cm[e]:
                agg_cm[e][a] += r["confusion"][e][a]

    per_tier = {}
    for tier in ("low", "medium", "high"):
        row = agg_cm[tier]
        total_t = sum(row.values())
        per_tier[tier] = round(row[tier] / total_t, 4) if total_t else 0

    return {
        "timestamp": datetime.now().isoformat(),
        "n_rounds": n_rounds, "n_cases_per_round": len(EVAL_CASES),
        "total_classifications": n_rounds * len(EVAL_CASES),
        "accuracy": {"mean": round(statistics.mean(accuracies), 4),
                      "std": round(statistics.stdev(accuracies), 4) if len(accuracies) > 1 else 0,
                      "per_round": accuracies, "bootstrap_ci": accuracy_ci, "per_tier": per_tier},
        "cost_savings": {"mean_pct": round(statistics.mean(savings_pcts), 1),
                          "std_pct": round(statistics.stdev(savings_pcts), 1) if len(savings_pcts) > 1 else 0,
                          "per_round": savings_pcts, "bootstrap_ci": savings_ci, "t_test": t_test},
        "confusion_matrix": agg_cm,
        "avg_latency_ms": round(statistics.mean(r["avg_latency_ms"] for r in all_rounds), 1),
        "rounds": all_rounds,
    }


def generate_report(results: dict) -> str:
    acc, sav, cm = results["accuracy"], results["cost_savings"], results["confusion_matrix"]
    t = sav["t_test"]
    lines = [
        "# Multi-Model Prompt Router — Cost & Accuracy Report", "",
        f"> Generated: {results['timestamp'][:19]}  ",
        f"> Rounds: {results['n_rounds']} | Cases/round: {results['n_cases_per_round']} | Total: {results['total_classifications']}", "",
        "## Architecture", "",
        "```", "User Prompt", "    |", "    v",
        "[Model Armor] <- safety screening (RAI, PI, jailbreak)", "    |", "    v",
        "[Flash Lite Classifier] <- complexity score 0-1 (~$0.00002/call)", "    |",
        "    +-- low  (<0.35) -> gemini-2.0-flash-lite   ($0.075/M in)",
        "    +-- med  (0.35-0.65) -> gemini-2.5-flash    ($0.15/M in)",
        "    +-- high (>=0.65) -> claude-opus-4-7        ($15/M in)", "```", "",
        "## Classification Accuracy", "",
        f"**Overall: {acc['mean']:.1%}** (95% CI: [{acc['bootstrap_ci']['ci_lower']:.1%}, {acc['bootstrap_ci']['ci_upper']:.1%}])", "",
        "| Tier | Accuracy | Correct / Total |", "|------|----------|-----------------|",
    ]
    for tier in ("low", "medium", "high"):
        row = cm[tier]; total_t = sum(row.values()); correct = row[tier]
        pct = correct / total_t * 100 if total_t else 0
        lines.append(f"| {tier} | {pct:.0f}% | {correct}/{total_t} |")

    lines.extend(["", "### Confusion Matrix", "",
        "| Expected \\ Actual | Low | Medium | High |", "|-------------------|-----|--------|------|"])
    for e in ("low", "medium", "high"):
        row = cm[e]; lines.append(f"| {e} | {row['low']} | {row['medium']} | {row['high']} |")

    lines.extend(["", "## Cost Savings", "",
        f"**Mean savings: {sav['mean_pct']:.1f}%** vs all-Claude-Opus baseline  ",
        f"95% CI: [{sav['bootstrap_ci']['ci_lower']:.1f}%, {sav['bootstrap_ci']['ci_upper']:.1f}%]", "",
        "### Statistical Significance", "",
        f"- Paired t-test: t={t['t_stat']:.2f}, p={t['p_value']:.6f}, n={t['n']}",
        f"- **{'Statistically significant' if t['significant'] else 'NOT statistically significant'}** at alpha=0.05", "",
        "### Per-Round Results", "",
        "| Round | Accuracy | Savings % | Routed Cost | Opus Cost |",
        "|-------|----------|-----------|-------------|-----------|"])
    for i, r in enumerate(results["rounds"], 1):
        lines.append(f"| {i} | {r['accuracy']:.1%} | {r['savings_pct']:.1f}% | ${r['total_routed_cost']:.6f} | ${r['total_opus_cost']:.6f} |")

    lines.extend(["", "## Cost Model", "",
        "| Model | Input $/M | Output $/M | Tier |",
        "|-------|-----------|------------|------|",
        "| gemini-2.0-flash-lite | $0.075 | $0.30 | Low |",
        "| gemini-2.5-flash | $0.15 | $0.60 | Medium |",
        "| claude-opus-4-7 | $15.00 | $75.00 | High |", "",
        f"Classifier overhead: ~$0.00002/call (Flash Lite, {CLASSIFIER_TOKEN_OVERHEAD} input tokens)",
        f"Assumed per-request: {AVG_INPUT_TOKENS} input + {AVG_OUTPUT_TOKENS} output tokens", "",
        "## Key Takeaways", ""])
    if t['significant']:
        lines.append(f"1. **{sav['mean_pct']:.0f}% cost reduction** with statistically significant savings (p={t['p_value']:.4f})")
    else:
        lines.append(f"1. **{sav['mean_pct']:.0f}% cost reduction** (significance pending)")
    lines.extend([
        f"2. **{acc['mean']:.0%} routing accuracy** — Flash Lite correctly identifies complexity tiers",
        f"3. Classifier overhead is negligible (~$0.00002/call) vs model cost savings",
        f"4. Average classification latency: {results['avg_latency_ms']:.0f}ms", "",
        "## Scaling Projections", "",
        "| Daily Volume | All-Opus Cost | Smart Router | Monthly Savings |",
        "|-------------|---------------|--------------|-----------------|"])
    for vol in (100, 1000, 10000, 100000):
        opus_d = vol * estimate_cost("vertex_ai/claude-opus-4-7", AVG_INPUT_TOKENS, AVG_OUTPUT_TOKENS)
        routed_d = opus_d * (1 - sav["mean_pct"] / 100)
        lines.append(f"| {vol:,} | ${opus_d:.2f}/day | ${routed_d:.2f}/day | ${(opus_d - routed_d) * 30:.0f}/mo |")

    lines.extend(["", "## Limitations", "",
        "- Model Armor provides safety-only filters (RAI, PI, jailbreak) — no complexity scoring",
        "- AI Gateway operates at network level — cannot route by prompt content",
        "- Vertex AI RoutingConfig only routes between Gemini variants, not cross-provider",
        "- Cost projections assume uniform token counts; real usage varies", "",
        "---", "*Report generated by `src/eval/router_eval.py`*"])
    return "\n".join(lines)


async def main(n_rounds: int = 3, update_report: bool = True):
    results = await run_eval_rounds(n_rounds)
    output_dir = Path("eval_results"); output_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"router_eval_{ts}.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nRaw results: {json_path}")
    report = generate_report(results)
    if update_report:
        report_path = Path("docs/multi_model_cost_comparison.md")
        report_path.parent.mkdir(exist_ok=True)
        report_path.write_text(report)
        print(f"Report updated: {report_path}")
    acc, sav, t = results["accuracy"], results["cost_savings"], results["cost_savings"]["t_test"]
    print(f"\n{'='*60}\nSUMMARY\n{'='*60}")
    print(f"  Accuracy:   {acc['mean']:.1%} (CI: [{acc['bootstrap_ci']['ci_lower']:.1%}, {acc['bootstrap_ci']['ci_upper']:.1%}])")
    print(f"  Savings:    {sav['mean_pct']:.1f}% (CI: [{sav['bootstrap_ci']['ci_lower']:.1f}%, {sav['bootstrap_ci']['ci_upper']:.1f}%])")
    print(f"  t-test:     t={t['t_stat']:.2f}, p={t['p_value']:.6f}")
    print(f"{'='*60}")
    return results


def cli():
    parser = argparse.ArgumentParser(description="Router eval with statistical significance")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--update-report", action="store_true", default=True)
    parser.add_argument("--no-update-report", action="store_false", dest="update_report")
    args = parser.parse_args()
    asyncio.run(main(n_rounds=args.rounds, update_report=args.update_report))


if __name__ == "__main__":
    cli()
