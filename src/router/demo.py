"""Demo runner — routes curated prompts through the multi-model router and prints results."""

import asyncio
import time

from .complexity import classify_complexity
from .cost_tracker import CostTracker, RequestLog, estimate_cost

DEMO_PROMPTS = [
    # Low complexity — single intent, direct lookups
    ("Find flights from SFO to JFK", "low"),
    ("What's the expense policy for meals?", "low"),
    ("Search hotels in Chicago under $200", "low"),
    ("Check if a $50 transport expense is within policy", "low"),

    # Medium complexity — moderate reasoning
    ("Find flights to NYC and compare the cheapest options by airline", "medium"),
    ("Search hotels in Boston, then check if the nightly rate fits our lodging policy", "medium"),

    # High complexity — multi-step, cross-domain
    (
        "Plan a 5-day trip to Tokyo for a team of 4: find flights, hotels near "
        "Shibuya, estimate daily meal expenses, and check what our corporate policy "
        "allows for international entertainment expenses.",
        "high",
    ),
    (
        "Compare individual vs group flight bookings for our team retreat to Denver. "
        "Factor in cancellation policies, per-diem meal expenses, and whether hotels "
        "near the conference center or downtown with transport are more cost-effective.",
        "high",
    ),
    (
        "Analyze EMP001's expense history: they overspent on entertainment last quarter. "
        "Draft a policy recommendation for new entertainment limits, and submit my "
        "$45 lunch receipt while you're at it.",
        "high",
    ),
    (
        "Book the cheapest SFO-JFK flight, find a hotel within walking distance of "
        "350 5th Ave, cross-reference hotel ratings, check our lodging policy limit, "
        "and submit a pre-approval expense for the estimated total trip cost.",
        "high",
    ),
]

MODEL_MAP = {
    "low": "gemini-2.5-flash-lite",
    "medium": "gemini-2.5-flash",
    "high": "claude-opus-4-6",
}

AVG_INPUT_TOKENS = 200
AVG_OUTPUT_TOKENS = 500


async def run_demo():
    tracker = CostTracker()
    print("\n" + "=" * 80)
    print("MULTI-MODEL PROMPT ROUTER DEMO")
    print("=" * 80)
    print(f"\n{'#':<3} {'Expected':<8} {'Classified':<10} {'Score':<6} {'Model':<30} {'Cost':>10}")
    print("-" * 80)

    for i, (prompt, expected) in enumerate(DEMO_PROMPTS, 1):
        start = time.monotonic()
        result = await classify_complexity(prompt)
        latency = (time.monotonic() - start) * 1000

        model = MODEL_MAP[result.level]
        cost = estimate_cost(model, AVG_INPUT_TOKENS, AVG_OUTPUT_TOKENS)
        classifier_cost = estimate_cost("classifier", len(prompt.split()) * 2, 20)
        total_cost = cost + classifier_cost

        match = "OK" if result.level == expected else "MISS"
        print(
            f"{i:<3} {expected:<8} {result.level:<10} {result.score:<6.2f} "
            f"{model:<30} ${total_cost:>9.6f}  {match}"
        )

        tracker.log_request(RequestLog(
            prompt=prompt[:80],
            complexity_level=result.level,
            complexity_score=result.score,
            model_used=model,
            input_tokens=AVG_INPUT_TOKENS,
            output_tokens=AVG_OUTPUT_TOKENS,
            latency_ms=latency,
            cost_usd=total_cost,
        ))

    print("\n" + tracker.generate_report())

    all_opus_cost = len(DEMO_PROMPTS) * estimate_cost(
        "claude-opus-4-6", AVG_INPUT_TOKENS, AVG_OUTPUT_TOKENS
    )
    routed_cost = tracker.total_cost()
    savings_pct = (1 - routed_cost / all_opus_cost) * 100 if all_opus_cost else 0

    print(f"\n### vs All-Opus Baseline")
    print(f"All-Opus cost:  ${all_opus_cost:.6f}")
    print(f"Routed cost:    ${routed_cost:.6f}")
    print(f"**Savings:      {savings_pct:.1f}%**")


if __name__ == "__main__":
    asyncio.run(run_demo())
