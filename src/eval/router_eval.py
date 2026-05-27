"""Router end-to-end evaluation — cost, latency, and quality across 5 model tiers.

Runs:
  1. Classifier loop (optional, kept from original eval) — accuracy + classifier latency
  2. Per-model inference loop — 22 prompts x 5 models x N rounds; captures real
     latency, real tokens, real cost via direct genai/LiteLLM calls
  3. LLM-as-judge quality loop (optional) — single comparative judge call per prompt
  4. Smart-router synthesis — what you actually get by routing per classifier decision
  5. Statistical tests — bootstrap CI, paired t-test
  6. Markdown report (overwrites docs/multi_model_cost_comparison.md)

Usage:
    uv run python -m src.eval.router_eval                                # full run
    uv run python -m src.eval.router_eval --rounds 1 --skip-quality      # fast
    uv run python -m src.eval.router_eval --models lite,flash            # subset
"""

import argparse
import asyncio
import json
import math
import random
import statistics
import time
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from src.config import LITE_MODEL, FLASH_MODEL, PRO_MODEL, SONNET_MODEL, OPUS_MODEL
from src.eval.router_inference import InferenceResult, call_all_models
from src.eval.router_quality_judge import JudgeScore, judge_responses
from src.eval.router_report import generate_report, TIER_TO_MODEL, MODEL_TO_TIER, TIER_ORDER
from src.router.complexity import classify_complexity, score_to_model_tier
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
        "expected": "high", "category": "planning",
    },
    {
        "prompt": "Compare individual vs group flight bookings for our team retreat to Denver. Factor in cancellation policies, per-diem meal expenses, and whether hotels near the conference center or downtown with transport are more cost-effective.",
        "expected": "high", "category": "analysis",
    },
    {
        "prompt": "Analyze EMP001's expense history: they overspent on entertainment last quarter. Draft a policy recommendation for new entertainment limits, and submit my $45 lunch receipt while you're at it.",
        "expected": "high", "category": "multi_action",
    },
    {
        "prompt": "Book the cheapest SFO-JFK flight, find a hotel within walking distance of 350 5th Ave, cross-reference hotel ratings, check our lodging policy limit, and submit a pre-approval expense for the estimated total trip cost.",
        "expected": "high", "category": "pipeline",
    },
    {
        "prompt": "I need a comprehensive cost analysis: compare flying to SF vs LA for our offsite, factor in hotel costs near conference venues, calculate per-person daily meal + transport budgets, and determine which city gives us more budget headroom for team entertainment.",
        "expected": "high", "category": "analysis",
    },
    {
        "prompt": "Help me with end-to-end trip booking and expenses: search flights, hotels, check all relevant policies, create an itinerary, and submit pre-approval expenses for everything.",
        "expected": "high", "category": "pipeline",
    },
]

# Maps classifier "low/medium/high" level to a model for the legacy classifier loop
LEVEL_TO_MODEL = {"low": LITE_MODEL, "medium": FLASH_MODEL, "high": OPUS_MODEL}

# System instruction for direct model inference (no tools available).
SYSTEM_INSTRUCTION = (
    "You are a corporate travel/expense assistant. Tools are unavailable in this benchmark. "
    "Describe the plan you WOULD execute: list the tools you'd call "
    "(search_flights, search_hotels, check_policy, submit_expense, book_flight), "
    "the arguments, the order, and how you'd synthesize the final answer. "
    "Do not fabricate tool results. Keep it under ~250 words."
)

# Classifier loop assumptions (kept for backward-compat with original eval)
AVG_INPUT_TOKENS = 200
AVG_OUTPUT_TOKENS = 500
CLASSIFIER_TOKEN_OVERHEAD = 40


# --------- Statistical helpers (preserved from original eval) ---------

def _paired_t_test(diffs: list[float]) -> dict:
    n = len(diffs)
    if n < 2:
        return {"t_stat": 0.0, "p_value": 1.0, "significant": False, "n": n}
    mean_d = statistics.mean(diffs)
    std_d = statistics.stdev(diffs)
    if std_d == 0:
        return {
            "t_stat": float("inf") if mean_d != 0 else 0.0,
            "p_value": 0.0 if mean_d != 0 else 1.0,
            "significant": mean_d != 0, "n": n, "mean_diff": mean_d,
        }
    t_stat = mean_d / (std_d / math.sqrt(n))
    p_value = math.erfc(abs(t_stat) / math.sqrt(2))
    return {
        "t_stat": round(t_stat, 4), "p_value": round(p_value, 6),
        "significant": p_value < 0.05, "n": n, "mean_diff": round(mean_d, 4),
    }


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


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * p
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    if lo == hi:
        return sorted_values[lo]
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo)


# --------- Classifier loop (kept from original) ---------

async def run_classifier_round(cases: list[dict]) -> dict:
    results = []
    confusion = {t: {"low": 0, "medium": 0, "high": 0} for t in ("low", "medium", "high")}
    for case in cases:
        t0 = time.monotonic()
        result = await classify_complexity(case["prompt"])
        latency_ms = (time.monotonic() - t0) * 1000
        expected, actual = case["expected"], result.level
        confusion[expected][actual] += 1
        routed_model = LEVEL_TO_MODEL[actual]
        routed_cost = estimate_cost(routed_model, AVG_INPUT_TOKENS, AVG_OUTPUT_TOKENS)
        classifier_cost = estimate_cost("classifier", CLASSIFIER_TOKEN_OVERHEAD, 20)
        opus_cost = estimate_cost(OPUS_MODEL, AVG_INPUT_TOKENS, AVG_OUTPUT_TOKENS)
        results.append({
            "prompt": case["prompt"][:80], "expected": expected, "actual": actual,
            "score": result.score, "model_tier": score_to_model_tier(result.score),
            "match": actual == expected, "latency_ms": round(latency_ms, 1),
            "routed_cost": routed_cost + classifier_cost, "opus_cost": opus_cost,
            "savings": opus_cost - (routed_cost + classifier_cost),
        })
    total = len(results)
    correct = sum(1 for r in results if r["match"])
    accuracy = correct / total if total else 0
    total_routed = sum(r["routed_cost"] for r in results)
    total_opus = sum(r["opus_cost"] for r in results)
    savings_pct = (1 - total_routed / total_opus) * 100 if total_opus else 0
    return {
        "accuracy": round(accuracy, 4), "correct": correct, "total": total,
        "confusion": confusion, "savings_pct": round(savings_pct, 1),
        "avg_latency_ms": round(statistics.mean(r["latency_ms"] for r in results), 1),
        "per_case": results,
    }


async def run_classifier_loop(n_rounds: int) -> dict:
    print(f"\n[classifier] {n_rounds} round(s) x {len(EVAL_CASES)} cases ...")
    all_rounds = []
    for i in range(n_rounds):
        print(f"  round {i+1}/{n_rounds}...", end=" ", flush=True)
        t0 = time.monotonic()
        r = await run_classifier_round(EVAL_CASES)
        elapsed = time.monotonic() - t0
        all_rounds.append(r)
        print(f"acc={r['accuracy']:.1%} savings={r['savings_pct']:.1f}% ({elapsed:.1f}s)")
    accuracies = [r["accuracy"] for r in all_rounds]
    cm = {t: {"low": 0, "medium": 0, "high": 0} for t in ("low", "medium", "high")}
    for r in all_rounds:
        for e in cm:
            for a in cm[e]:
                cm[e][a] += r["confusion"][e][a]
    return {
        "accuracy": {
            "mean": round(statistics.mean(accuracies), 4),
            "bootstrap_ci": _bootstrap_ci(accuracies),
            "per_round": accuracies,
        },
        "confusion_matrix": cm,
        "avg_latency_ms": round(statistics.mean(r["avg_latency_ms"] for r in all_rounds), 1),
        "per_case_routes": all_rounds[-1]["per_case"],  # use last round for routing decisions
        "rounds": all_rounds,
    }


# --------- Inference + judge loops ---------

async def run_inference_round(
    cases: list[dict], models: list[str], semaphore: asyncio.Semaphore
) -> list[dict]:
    """Run one inference round: for each prompt, call all models in parallel."""
    records = []
    for case in cases:
        async with semaphore:
            results = await call_all_models(case["prompt"], models, SYSTEM_INSTRUCTION)
        records.append({
            "prompt": case["prompt"],
            "expected": case["expected"],
            "category": case["category"],
            "results": {m: asdict(r) for m, r in results.items()},
        })
    return records


async def run_quality_round(
    inference_records: list[dict], judge_model: str, max_concurrency: int = 3
) -> list[dict]:
    """Score quality for each prompt's responses (one judge call per prompt, parallelized)."""
    semaphore = asyncio.Semaphore(max_concurrency)

    async def judge_one(rec: dict) -> dict:
        model_to_text = {
            m: r["text"] for m, r in rec["results"].items()
            if not r.get("error") and r["text"]
        }
        if not model_to_text:
            return {"prompt": rec["prompt"], "scores": {}}
        async with semaphore:
            scores = await judge_responses(rec["prompt"], model_to_text, judge_model=judge_model)
        return {"prompt": rec["prompt"], "scores": {m: asdict(s) for m, s in scores.items()}}

    return await asyncio.gather(*(judge_one(rec) for rec in inference_records))


# --------- Aggregation ---------

def aggregate_per_model(
    inference_rounds: list[list[dict]], quality_rounds: list[list[dict]] | None, models: list[str]
) -> dict:
    """Build per-model summary: latency p50/p95/mean+CI, cost totals, quality mean+CI."""
    per_model: dict[str, dict] = {}
    for model in models:
        lat, costs, in_tok, out_tok = [], [], [], []
        errors = 0
        for round_recs in inference_rounds:
            for rec in round_recs:
                r = rec["results"].get(model)
                if not r:
                    continue
                if r.get("error"):
                    errors += 1
                    continue
                lat.append(r["latency_ms"])
                costs.append(r["cost_usd"])
                in_tok.append(r["input_tokens"])
                out_tok.append(r["output_tokens"])
        n = len(lat)
        d: dict = {"n_success": n, "n_errors": errors}
        if n:
            sorted_lat = sorted(lat)
            d.update({
                "latency_mean": round(statistics.mean(lat), 1),
                "latency_p50": round(_percentile(sorted_lat, 0.5), 1),
                "latency_p95": round(_percentile(sorted_lat, 0.95), 1),
                "latency_ci": _bootstrap_ci(lat),
                "avg_input_tokens": round(statistics.mean(in_tok), 1),
                "avg_output_tokens": round(statistics.mean(out_tok), 1),
                "avg_cost": round(statistics.mean(costs), 8),
                "total_cost": round(sum(costs), 6),
            })

        if quality_rounds is not None:
            q_overall, q_dims = [], defaultdict(list)
            q_errors = 0
            for round_q in quality_rounds:
                for q_rec in round_q:
                    s = q_rec["scores"].get(model)
                    if not s:
                        continue
                    if s.get("error"):
                        q_errors += 1
                        continue
                    q_overall.append(s["overall"])
                    for dim in ("plan_completeness", "correctness", "reasoning_clarity", "tool_awareness"):
                        q_dims[dim].append(s[dim])
            d["n_quality"] = len(q_overall)
            d["n_quality_errors"] = q_errors
            if q_overall:
                d["quality"] = {
                    "overall": round(statistics.mean(q_overall), 3),
                    "overall_ci": _bootstrap_ci(q_overall),
                    **{dim: round(statistics.mean(vals), 3) for dim, vals in q_dims.items()},
                }
        per_model[model] = d
    return per_model


def _build_prompt_to_chosen_model(classifier_routes: list[dict] | None) -> dict[str, str]:
    """Map each EVAL_CASES prompt to the model that smart-router would pick.

    Uses the classifier's actual decision when available; otherwise falls back
    to a tier derived from the expected label.
    """
    classifier_by_prefix: dict[str, str] = {}
    if classifier_routes:
        for route in classifier_routes:
            tier = route.get("model_tier") or score_to_model_tier(route["score"])
            classifier_by_prefix[route["prompt"]] = TIER_TO_MODEL.get(tier, FLASH_MODEL)

    expected_default = {"low": LITE_MODEL, "medium": FLASH_MODEL, "high": OPUS_MODEL}
    mapping: dict[str, str] = {}
    for case in EVAL_CASES:
        full = case["prompt"]
        chosen = next(
            (m for prefix, m in classifier_by_prefix.items() if full.startswith(prefix)),
            None,
        )
        mapping[full] = chosen or expected_default[case["expected"]]
    return mapping


def synthesize_smart_router(
    inference_rounds: list[list[dict]], quality_rounds: list[list[dict]] | None,
    classifier_routes: list[dict] | None, models: list[str],
) -> dict:
    """For each prompt, pick the response from the classifier-selected tier.

    Falls back to a tier derived from EVAL_CASES expected label if classifier wasn't run.
    """
    chosen_for = _build_prompt_to_chosen_model(classifier_routes)

    def model_for(prompt: str, strategy: str) -> str:
        if strategy == "smart_router":
            return chosen_for.get(prompt, FLASH_MODEL)
        if strategy == "all_lite":
            return LITE_MODEL
        if strategy == "all_opus":
            return OPUS_MODEL
        return FLASH_MODEL

    def collect(strategy: str) -> dict:
        latencies, costs = [], []
        for round_recs in inference_rounds:
            for rec in round_recs:
                chosen = model_for(rec["prompt"], strategy)
                r = rec["results"].get(chosen)
                if r and not r.get("error"):
                    latencies.append(r["latency_ms"])
                    costs.append(r["cost_usd"])
        out = {
            "n_prompts": len(costs),
            "avg_latency_ms": round(statistics.mean(latencies), 1) if latencies else 0,
            "total_cost": round(sum(costs), 6),
        }
        if quality_rounds is not None:
            qs = []
            for round_q, round_recs in zip(quality_rounds, inference_rounds):
                for q_rec, rec in zip(round_q, round_recs):
                    chosen = model_for(rec["prompt"], strategy)
                    s = q_rec["scores"].get(chosen)
                    if s and not s.get("error"):
                        qs.append(s["overall"])
            out["avg_quality"] = round(statistics.mean(qs), 3) if qs else 0
        return out

    smart, lite, opus = collect("smart_router"), collect("all_lite"), collect("all_opus")
    for row in (smart, lite):
        row["cost_savings_vs_opus_pct"] = round(
            (1 - row["total_cost"] / opus["total_cost"]) * 100, 2
        ) if opus["total_cost"] else 0
    opus["cost_savings_vs_opus_pct"] = 0.0
    return {"smart_router": smart, "all_lite": lite, "all_opus": opus,
            "chosen_per_prompt": chosen_for}


def compute_significance_stats(
    inference_rounds: list[list[dict]], quality_rounds: list[list[dict]] | None,
    classifier_routes: list[dict] | None,
) -> dict:
    """Bootstrap CI on per-round cost savings; paired t-test on smart-vs-opus quality."""
    stats: dict = {}
    chosen_for = _build_prompt_to_chosen_model(classifier_routes)

    # Per-round savings %
    savings_pcts = []
    for round_recs in inference_rounds:
        smart_cost = opus_cost = 0.0
        for rec in round_recs:
            opus_r = rec["results"].get(OPUS_MODEL)
            smart_r = rec["results"].get(chosen_for.get(rec["prompt"], FLASH_MODEL))
            if opus_r and not opus_r.get("error"):
                opus_cost += opus_r["cost_usd"]
            if smart_r and not smart_r.get("error"):
                smart_cost += smart_r["cost_usd"]
        if opus_cost > 0:
            savings_pcts.append((1 - smart_cost / opus_cost) * 100)
    if savings_pcts:
        stats["cost_savings_vs_opus"] = {
            "mean_pct": round(statistics.mean(savings_pcts), 2),
            "per_round": [round(p, 2) for p in savings_pcts],
            "bootstrap_ci": _bootstrap_ci(savings_pcts),
        }

    if quality_rounds is not None:
        # Paired t-test on smart-router vs all-opus quality, per (round, prompt)
        diffs = []
        for round_q, round_recs in zip(quality_rounds, inference_rounds):
            for q_rec, rec in zip(round_q, round_recs):
                smart_model = chosen_for.get(rec["prompt"], FLASH_MODEL)
                if smart_model == OPUS_MODEL:
                    continue  # smart router == opus on this prompt, no comparison
                opus_s = q_rec["scores"].get(OPUS_MODEL)
                smart_s = q_rec["scores"].get(smart_model)
                if (opus_s and smart_s and
                        not opus_s.get("error") and not smart_s.get("error")):
                    diffs.append(smart_s["overall"] - opus_s["overall"])
        stats["quality_paired_t"] = _paired_t_test(diffs)
    return stats


# --------- Orchestrator ---------

async def run_eval(
    n_rounds: int, models: list[str], judge_model: str,
    skip_quality: bool, skip_classifier: bool, max_concurrency: int,
) -> dict:
    print(f"\n=== Router Eval: {n_rounds} round(s), models: {','.join(MODEL_TO_TIER.get(m, m) for m in models)} ===")
    classifier_results = None
    if not skip_classifier:
        classifier_results = await run_classifier_loop(n_rounds)

    inference_rounds: list[list[dict]] = []
    semaphore = asyncio.Semaphore(max_concurrency)
    print(f"\n[inference] {n_rounds} round(s) x {len(EVAL_CASES)} prompts x {len(models)} models...")
    for i in range(n_rounds):
        print(f"  round {i+1}/{n_rounds}...", end=" ", flush=True)
        t0 = time.monotonic()
        recs = await run_inference_round(EVAL_CASES, models, semaphore)
        elapsed = time.monotonic() - t0
        err_count = sum(1 for rec in recs for r in rec["results"].values() if r.get("error"))
        print(f"done ({elapsed:.0f}s, {err_count} errors)")
        inference_rounds.append(recs)

    quality_rounds: list[list[dict]] | None = None
    if not skip_quality:
        print(f"\n[quality] {n_rounds} round(s) x {len(EVAL_CASES)} judge calls (judge={judge_model})...")
        quality_rounds = []
        for i, round_recs in enumerate(inference_rounds, 1):
            print(f"  round {i}/{n_rounds}...", end=" ", flush=True)
            t0 = time.monotonic()
            qs = await run_quality_round(round_recs, judge_model, max_concurrency=max_concurrency)
            elapsed = time.monotonic() - t0
            err_count = sum(1 for q in qs for s in q["scores"].values() if s.get("error"))
            print(f"done ({elapsed:.0f}s, {err_count} score errors)")
            quality_rounds.append(qs)

    per_model = aggregate_per_model(inference_rounds, quality_rounds, models)
    classifier_routes = classifier_results["per_case_routes"] if classifier_results else None
    smart = synthesize_smart_router(inference_rounds, quality_rounds, classifier_routes, models)
    stats = compute_significance_stats(inference_rounds, quality_rounds, classifier_routes)

    return {
        "timestamp": datetime.now().isoformat(),
        "n_rounds": n_rounds, "n_cases_per_round": len(EVAL_CASES),
        "models": models, "judge_model": judge_model,
        "quality_enabled": not skip_quality,
        "classifier": classifier_results,
        "per_model": per_model, "smart_router": smart, "stats": stats,
        "inference_rounds": inference_rounds,
        "quality_rounds": quality_rounds,
    }


def _parse_models(s: str) -> list[str]:
    aliases = {"lite": LITE_MODEL, "flash": FLASH_MODEL, "pro": PRO_MODEL,
               "sonnet": SONNET_MODEL, "opus": OPUS_MODEL, "all": None}
    if s.strip().lower() == "all":
        return [LITE_MODEL, FLASH_MODEL, PRO_MODEL, SONNET_MODEL, OPUS_MODEL]
    parts = [p.strip() for p in s.split(",") if p.strip()]
    out = []
    for p in parts:
        if p in aliases and aliases[p] is not None:
            out.append(aliases[p])
        else:
            out.append(p)
    return out


def _print_summary(results: dict):
    print(f"\n{'='*70}\nSUMMARY\n{'='*70}")
    for model in results["models"]:
        d = results["per_model"].get(model, {})
        tier = MODEL_TO_TIER.get(model, "?")
        if not d.get("n_success"):
            print(f"  {tier:<7} {model:<32}  NO DATA")
            continue
        q = d.get("quality", {}).get("overall", None)
        q_str = f" quality={q:.2f}" if q is not None else ""
        print(f"  {tier:<7} {model:<32}  "
              f"lat_p50={d['latency_p50']:>6.0f}ms  "
              f"lat_p95={d['latency_p95']:>6.0f}ms  "
              f"cost={d['avg_cost']:.6f}/call{q_str}  "
              f"err={d['n_errors']}")
    smart = results["smart_router"].get("smart_router")
    opus = results["smart_router"].get("all_opus")
    if smart and opus:
        print(f"\n  Smart router vs all-Opus: "
              f"cost ${smart['total_cost']:.4f} vs ${opus['total_cost']:.4f}  "
              f"(savings: {smart.get('cost_savings_vs_opus_pct', 0):.1f}%)")
    print("=" * 70)


async def main(args):
    models = _parse_models(args.models)
    results = await run_eval(
        n_rounds=args.rounds, models=models, judge_model=args.judge_model,
        skip_quality=args.skip_quality, skip_classifier=args.skip_classifier,
        max_concurrency=args.max_concurrency,
    )

    output_dir = Path("eval_results")
    output_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"router_eval_{ts}.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nRaw results: {json_path}")

    if args.update_report:
        report = generate_report(results)
        report_path = Path("docs/multi_model_cost_comparison.md")
        report_path.parent.mkdir(exist_ok=True)
        report_path.write_text(report)
        print(f"Report updated: {report_path}")

    _print_summary(results)
    return results


def cli():
    parser = argparse.ArgumentParser(description="Router end-to-end eval: cost + latency + quality")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--models", type=str, default="all",
                        help="Comma-separated tier names (lite,flash,pro,sonnet,opus) or 'all'")
    # Default judge: gemini-2.5-pro (non-thinking, fast, reliable structured output).
    # Not Opus (avoids self-grading bias).
    parser.add_argument("--judge-model", type=str, default="gemini-2.5-pro")
    parser.add_argument("--skip-quality", action="store_true")
    parser.add_argument("--skip-classifier", action="store_true")
    parser.add_argument("--max-concurrency", type=int, default=2,
                        help="Max concurrent prompts (each prompt fans out to len(models) models)")
    parser.add_argument("--update-report", action="store_true", default=True)
    parser.add_argument("--no-update-report", action="store_false", dest="update_report")
    args = parser.parse_args()
    asyncio.run(main(args))


if __name__ == "__main__":
    cli()
