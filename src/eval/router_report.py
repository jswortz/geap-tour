"""Markdown report generator for router end-to-end experiment.

Consumes the aggregated results dict produced by router_eval.py and emits
the regenerated docs/multi_model_cost_comparison.md.
"""

import statistics
from src.config import LITE_MODEL, FLASH_MODEL, PRO_MODEL, SONNET_MODEL, OPUS_MODEL
from src.router.cost_tracker import COST_RATES

TIER_TO_MODEL = {
    "lite": LITE_MODEL,
    "flash": FLASH_MODEL,
    "pro": PRO_MODEL,
    "sonnet": SONNET_MODEL,
    "opus": OPUS_MODEL,
}
MODEL_TO_TIER = {v: k for k, v in TIER_TO_MODEL.items()}
TIER_ORDER = ["lite", "flash", "pro", "sonnet", "opus"]


def _fmt_ci(ci: dict, pct: bool = False, digits: int = 1) -> str:
    if not ci:
        return "—"
    lo, hi = ci.get("ci_lower", 0), ci.get("ci_upper", 0)
    suffix = "%" if pct else ""
    fmt = f"{{:.{digits}f}}"
    return f"[{fmt.format(lo)}{suffix}, {fmt.format(hi)}{suffix}]"


def _fmt_pricing_row(model: str) -> str:
    rates = COST_RATES.get(model, {"input": 0, "output": 0})
    return f"| `{model}` | ${rates['input']:.3f} | ${rates['output']:.2f} |"


def _section_header(results: dict) -> list[str]:
    return [
        "# Multi-Model Prompt Router — Cost, Latency & Quality Report",
        "",
        f"> Generated: {results['timestamp'][:19]}  ",
        f"> Rounds: {results['n_rounds']} | Cases/round: {results['n_cases_per_round']} | "
        f"Models evaluated: {len(results.get('models', []))} | "
        f"Judge: `{results.get('judge_model', '—')}`",
        "",
    ]


def _section_architecture() -> list[str]:
    return [
        "## Architecture",
        "",
        "```",
        "User Prompt",
        "    |",
        "    v",
        "[Model Armor] -- safety screening (RAI, PI, jailbreak)",
        "    |",
        "    v",
        f"[Router Agent] ({LITE_MODEL})",
        "    |  before_agent_callback: classify_complexity()",
        "    |  Flash Lite scores prompt 0-1, maps to 5-tier",
        "    |",
        f"    |-- score<0.30   --> [Lite]   `{LITE_MODEL}`",
        f"    |-- score<0.45   --> [Flash]  `{FLASH_MODEL}`",
        f"    |-- score<0.60   --> [Sonnet] `{SONNET_MODEL}`",
        f"    |-- score<0.80   --> [Pro]    `{PRO_MODEL}`",
        f"    +-- score>=0.80  --> [Opus]   `{OPUS_MODEL}`",
        "```",
        "",
    ]


def _section_classifier_accuracy(results: dict) -> list[str]:
    classifier = results.get("classifier")
    if not classifier:
        return []
    acc = classifier["accuracy"]
    cm = classifier["confusion_matrix"]
    lines = [
        "## Classifier Accuracy",
        "",
        f"**Overall: {acc['mean']:.1%}** (95% CI: "
        f"[{acc['bootstrap_ci']['ci_lower']:.1%}, {acc['bootstrap_ci']['ci_upper']:.1%}])",
        "",
        "| Tier | Accuracy | Correct / Total |",
        "|------|----------|-----------------|",
    ]
    for tier in ("low", "medium", "high"):
        row = cm[tier]
        total_t = sum(row.values())
        correct = row[tier]
        pct = correct / total_t * 100 if total_t else 0
        lines.append(f"| {tier} | {pct:.0f}% | {correct}/{total_t} |")
    lines.extend([
        "",
        "### Confusion Matrix",
        "",
        "| Expected \\ Actual | Low | Medium | High |",
        "|-------------------|-----|--------|------|",
    ])
    for e in ("low", "medium", "high"):
        row = cm[e]
        lines.append(f"| {e} | {row['low']} | {row['medium']} | {row['high']} |")
    lines.extend([
        "",
        f"Avg classifier latency: **{classifier['avg_latency_ms']:.0f} ms**  ",
        "",
    ])
    return lines


def _section_latency(per_model: dict) -> list[str]:
    lines = [
        "## Per-Model Latency",
        "",
        "Wall-clock time from request to response. Direct API calls — no tools, no MCP, no ADK overhead.",
        "",
        "| Tier | Model | Mean (ms) | p50 (ms) | p95 (ms) | 95% CI of mean |",
        "|------|-------|-----------|----------|----------|----------------|",
    ]
    for tier in TIER_ORDER:
        m = TIER_TO_MODEL[tier]
        d = per_model.get(m)
        if not d or not d.get("n_success"):
            lines.append(f"| {tier} | `{m}` | — | — | — | — |")
            continue
        lines.append(
            f"| {tier} | `{m}` | {d['latency_mean']:.0f} | {d['latency_p50']:.0f} | "
            f"{d['latency_p95']:.0f} | {_fmt_ci(d['latency_ci'], digits=0)} |"
        )
    lines.append("")
    return lines


def _section_cost(per_model: dict) -> list[str]:
    lines = [
        "## Per-Model Cost",
        "",
        "Real token counts from API `usage_metadata`, cost computed from current per-1M-token pricing.",
        "",
        "| Tier | Model | Avg In Tokens | Avg Out Tokens | $/call | Total $ |",
        "|------|-------|--------------:|---------------:|-------:|--------:|",
    ]
    for tier in TIER_ORDER:
        m = TIER_TO_MODEL[tier]
        d = per_model.get(m)
        if not d or not d.get("n_success"):
            lines.append(f"| {tier} | `{m}` | — | — | — | — |")
            continue
        lines.append(
            f"| {tier} | `{m}` | {d['avg_input_tokens']:.0f} | {d['avg_output_tokens']:.0f} | "
            f"${d['avg_cost']:.6f} | ${d['total_cost']:.4f} |"
        )
    lines.append("")
    return lines


def _section_quality(per_model: dict, has_quality: bool) -> list[str]:
    if not has_quality:
        return ["## Per-Model Quality", "", "_Quality judge was skipped for this run._", ""]
    lines = [
        "## Per-Model Quality (LLM-as-Judge)",
        "",
        "4-dim rubric, each 1-5. Overall = mean of the four. Single comparative judge call per prompt "
        "(responses anonymized A-E, order shuffled per call to mitigate bias).",
        "",
        "| Tier | Model | Plan | Correct | Reasoning | Tools | **Overall** | 95% CI |",
        "|------|-------|-----:|--------:|----------:|------:|------------:|--------|",
    ]
    for tier in TIER_ORDER:
        m = TIER_TO_MODEL[tier]
        d = per_model.get(m)
        if not d or not d.get("n_quality"):
            lines.append(f"| {tier} | `{m}` | — | — | — | — | — | — |")
            continue
        q = d["quality"]
        lines.append(
            f"| {tier} | `{m}` | {q['plan_completeness']:.2f} | {q['correctness']:.2f} | "
            f"{q['reasoning_clarity']:.2f} | {q['tool_awareness']:.2f} | "
            f"**{q['overall']:.2f}** | {_fmt_ci(q['overall_ci'], digits=2)} |"
        )
    lines.append("")
    return lines


def _section_frontier(per_model: dict, has_quality: bool) -> list[str]:
    if not has_quality:
        return []
    rows = []
    for tier in TIER_ORDER:
        m = TIER_TO_MODEL[tier]
        d = per_model.get(m)
        if not d or not d.get("n_quality") or not d.get("avg_cost"):
            continue
        q = d["quality"]["overall"]
        cost = d["avg_cost"]
        rows.append((tier, m, q, cost, q / cost if cost > 0 else 0))
    rows.sort(key=lambda r: -r[4])
    lines = [
        "## Cost-Quality Frontier",
        "",
        "Quality per dollar — higher is better. Sorted by efficiency.",
        "",
        "| Rank | Tier | Model | Quality | $/call | Quality / $ |",
        "|------|------|-------|--------:|-------:|------------:|",
    ]
    for i, (tier, m, q, cost, ratio) in enumerate(rows, 1):
        lines.append(f"| {i} | {tier} | `{m}` | {q:.2f} | ${cost:.6f} | {ratio:,.0f} |")
    lines.append("")
    return lines


def _section_smart_router(smart: dict, has_quality: bool) -> list[str]:
    if not smart:
        return []
    lines = [
        "## Smart Router Synthesis",
        "",
        "What you actually get in production: for each prompt, pick the response from the model the classifier routed to. "
        "Compared against the two extremes (all-Lite = cheapest, all-Opus = most expensive).",
        "",
    ]
    headers = ["Strategy", "Avg Latency (ms)", "Total $", "vs all-Opus"]
    if has_quality:
        headers.insert(2, "Avg Quality")
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for strat in ("smart_router", "all_lite", "all_opus"):
        row = smart.get(strat)
        if not row:
            continue
        latency = f"{row['avg_latency_ms']:.0f}"
        cost = f"${row['total_cost']:.4f}"
        vs_opus = "baseline" if strat == "all_opus" else (
            f"{row['cost_savings_vs_opus_pct']:+.1f}%"
        )
        name = {"smart_router": "**Smart Router**", "all_lite": "All-Lite", "all_opus": "All-Opus"}[strat]
        cells = [name, latency, cost, vs_opus]
        if has_quality:
            cells.insert(2, f"{row.get('avg_quality', 0):.2f}")
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def _section_significance(stats: dict, has_quality: bool) -> list[str]:
    lines = ["## Statistical Significance", ""]
    cost_sig = stats.get("cost_savings_vs_opus")
    if cost_sig:
        ci = cost_sig.get("bootstrap_ci", {})
        lines.append(
            f"- **Cost savings (smart router vs all-Opus):** mean {cost_sig['mean_pct']:.1f}%, "
            f"95% CI {_fmt_ci(ci, pct=True, digits=1)}."
        )
    if has_quality:
        q_t = stats.get("quality_paired_t")
        if q_t:
            verdict = "Smart router quality is statistically indistinguishable from Opus" if not q_t["significant"] else (
                "Smart router quality differs significantly from Opus (review direction below)"
            )
            lines.append(
                f"- **Quality (smart router vs all-Opus, paired t-test):** t={q_t['t_stat']:.2f}, "
                f"p={q_t['p_value']:.4f}, n={q_t['n']} — {verdict}."
            )
            mean_diff = q_t.get("mean_diff")
            if mean_diff is not None:
                direction = "Smart router scored higher" if mean_diff > 0 else ("Opus scored higher" if mean_diff < 0 else "Tied")
                lines.append(
                    f"  - Mean quality delta (smart - opus): {mean_diff:+.3f} — {direction}."
                )
    lines.append("")
    return lines


def _section_pricing() -> list[str]:
    lines = [
        "## Pricing Reference (per 1M tokens)",
        "",
        "| Model | Input $ | Output $ |",
        "|-------|--------:|---------:|",
    ]
    for tier in TIER_ORDER:
        lines.append(_fmt_pricing_row(TIER_TO_MODEL[tier]))
    lines.append("")
    return lines


def _section_scaling(smart: dict) -> list[str]:
    sr = smart.get("smart_router") if smart else None
    op = smart.get("all_opus") if smart else None
    if not sr or not op:
        return []
    per_prompt_smart = sr["total_cost"] / sr["n_prompts"]
    per_prompt_opus = op["total_cost"] / op["n_prompts"]
    lines = [
        "## Scaling Projections",
        "",
        "Monthly cost projection assuming the per-prompt mix observed in this benchmark.",
        "",
        "| Daily Volume | All-Opus / day | Smart Router / day | Monthly Savings |",
        "|-------------|---------------:|-------------------:|----------------:|",
    ]
    for vol in (100, 1000, 10000, 100000):
        opus_d = vol * per_prompt_opus
        smart_d = vol * per_prompt_smart
        lines.append(f"| {vol:,} | ${opus_d:.2f} | ${smart_d:.2f} | ${(opus_d - smart_d) * 30:,.0f} |")
    lines.append("")
    return lines


def _section_methodology(results: dict) -> list[str]:
    return [
        "## Methodology",
        "",
        f"- **Test set:** {results['n_cases_per_round']} prompts spanning low / medium / high complexity tiers.",
        f"- **Rounds:** {results['n_rounds']}. Each (prompt, model) cell is run {results['n_rounds']} time(s); "
        "metrics are aggregated across all runs.",
        "- **Inference:** direct API calls (`google.genai` for Gemini, LiteLLM `acompletion` for Claude). "
        "No ADK orchestration, no MCP tools, no Cloud Run round-trip — to isolate model behavior.",
        "- **System instruction:** asks models to describe the plan they'd execute (tool names, args, "
        "synthesis steps) since tools are not provided. Quality is rated on reasoning, not tool execution.",
        "- **Quality judge:** single comparative call per prompt over all anonymized responses (A-E, shuffled). "
        "Mitigates ordering bias. Judge is `" + str(results.get("judge_model", "—")) + "` (not Opus, "
        "to avoid self-grading bias).",
        "- **Concurrency:** within each prompt, the 5 models are called in parallel via `asyncio.gather`. "
        "Across prompts, runs are sequential to avoid quota spikes.",
        "",
    ]


def _section_limitations() -> list[str]:
    return [
        "## Limitations",
        "",
        "- **No tool execution.** Quality reflects reasoning and tool *selection*, not real tool outcomes. "
        "End-to-end task success requires the full ADK + MCP stack and would add Cloud Run latency.",
        "- **LLM-as-judge bias.** Even with anonymization and a non-Opus judge, the rubric is subjective. "
        "Treat quality scores as comparative, not absolute.",
        "- **List pricing.** Cost uses public per-1M-token rates; enterprise discounts change ratios.",
        "- **Latency variance.** Cold starts and queueing effects can vary by run; we report mean / p50 / p95.",
        "- **Token estimates for thinking models.** Gemini 3.x thinking tokens are billed at output rate "
        "and already included in `candidates_token_count`.",
        "",
        "---",
        "*Report generated by `src/eval/router_report.py`*",
    ]


def generate_report(results: dict) -> str:
    per_model = results.get("per_model", {})
    smart = results.get("smart_router", {})
    stats = results.get("stats", {})
    has_quality = bool(results.get("quality_enabled"))

    parts = []
    parts.extend(_section_header(results))
    parts.extend(_section_architecture())
    parts.extend(_section_classifier_accuracy(results))
    parts.extend(_section_latency(per_model))
    parts.extend(_section_cost(per_model))
    parts.extend(_section_quality(per_model, has_quality))
    parts.extend(_section_frontier(per_model, has_quality))
    parts.extend(_section_smart_router(smart, has_quality))
    parts.extend(_section_significance(stats, has_quality))
    parts.extend(_section_pricing())
    parts.extend(_section_scaling(smart))
    parts.extend(_section_methodology(results))
    parts.extend(_section_limitations())
    return "\n".join(parts)
