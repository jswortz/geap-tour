"""Demo runner — routes curated prompts through the 5-tier multi-model router."""

import asyncio
import time

from .complexity import classify_complexity, score_to_model_tier
from .config import LITE_MODEL, FLASH_MODEL, PRO_MODEL, SONNET_MODEL, OPUS_MODEL
from .cost_tracker import CostTracker, RequestLog, estimate_cost

DEMO_PROMPTS = [
    # Low — trivial, single intent
    ("What's the expense policy for meals?", "low"),
    ("Find hotels in Miami", "low"),

    # Medium-low — single intent with light reasoning
    ("Find flights from SFO to JFK and show the cheapest", "medium_low"),
    ("Submit a $30 meals expense for coffee, user EMP001", "medium_low"),
    ("Book flight FL001 for Alice Johnson", "medium_low"),

    # Medium — 2 intents, comparison, reasoning
    ("Search hotels in New York, then check if the nightly rate fits our lodging policy", "medium"),
    ("Find flights to NYC and compare the cheapest options by airline", "medium"),

    # Medium-high — 3+ intents, cross-domain
    ("Show expense history for EMP001, check entertainment policy, and submit a $45 lunch receipt", "medium_high"),
    ("Compare flights from SFO to JFK vs LAX to ORD, factoring in per-diem meals and hotel costs", "medium_high"),

    # High — expert, multi-step planning, synthesis
    (
        "Plan a 5-day trip to Tokyo for a team of 4: find flights, hotels near "
        "Shibuya, estimate daily meal expenses, and check what our corporate policy "
        "allows for international entertainment expenses.",
        "high",
    ),
    (
        "I have a $2000 budget for a London trip. Find flights, hotels, check "
        "lodging and meal policies, and tell me if I can afford it within corporate limits. "
        "Also draft a pre-trip expense estimate for my manager.",
        "high",
    ),
]

MODEL_TIER_MAP = {
    "lite": LITE_MODEL,
    "flash": FLASH_MODEL,
    "pro": PRO_MODEL,
    "sonnet": SONNET_MODEL,
    "opus": OPUS_MODEL,
}

# For backward compat with run_comparison imports
MODEL_MAP = MODEL_TIER_MAP

AVG_INPUT_TOKENS = 200
AVG_OUTPUT_TOKENS = 500


async def run_demo():
    tracker = CostTracker()
    print("\n" + "=" * 80)
    print("5-TIER MULTI-MODEL PROMPT ROUTER DEMO")
    print("=" * 80)
    print(f"\n{'#':<3} {'Expected':<12} {'Level':<8} {'Tier':<8} {'Score':<6} {'Model':<30} {'Cost':>10}")
    print("-" * 90)

    for i, (prompt, expected) in enumerate(DEMO_PROMPTS, 1):
        start = time.monotonic()
        result = await classify_complexity(prompt)
        latency = (time.monotonic() - start) * 1000

        tier = score_to_model_tier(result.score)
        model = MODEL_TIER_MAP[tier]
        cost = estimate_cost(model, AVG_INPUT_TOKENS, AVG_OUTPUT_TOKENS)
        classifier_cost = estimate_cost("classifier", len(prompt.split()) * 2, 20)
        total_cost = cost + classifier_cost

        match = "OK" if result.level == expected else "MISS"
        print(
            f"{i:<3} {expected:<12} {result.level:<12} {result.score:<6.2f} "
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
        OPUS_MODEL, AVG_INPUT_TOKENS, AVG_OUTPUT_TOKENS
    )
    routed_cost = tracker.total_cost()
    savings_pct = (1 - routed_cost / all_opus_cost) * 100 if all_opus_cost else 0

    print("\n### vs All-Opus Baseline")
    print(f"All-Opus cost:  ${all_opus_cost:.6f}")
    print(f"Routed cost:    ${routed_cost:.6f}")
    print(f"**Savings:      {savings_pct:.1f}%**")


if __name__ == "__main__":
    asyncio.run(run_demo())
