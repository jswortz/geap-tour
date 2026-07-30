"""Tests for the Router Cost Visualizer's pure cost logic (``app/cost_model.py``).

These lock the deterministic router-vs-all-Opus accounting the A2UI dashboard renders,
and guard ``app/cost_model.COST_RATES`` against drifting from the canonical pricing in
``src/router/cost_tracker.COST_RATES`` (the app image is standalone and keeps its own
copy on purpose, so a test — not an import — is what keeps the two in sync).
"""

import math

from app.cost_model import (
    COST_RATES,
    TIER_MODEL,
    BASELINE_MODEL,
    Accrual,
    Step,
    build_accrual,
    estimate_cost,
)


def test_estimate_cost_matches_per_million_rates():
    # 1M input + 1M output tokens => exactly input_rate + output_rate.
    rate = COST_RATES["gemini-3.1-flash-lite"]
    assert estimate_cost("gemini-3.1-flash-lite", 1_000_000, 1_000_000) == rate["input"] + rate["output"]
    # Half a million output tokens => half the output rate.
    assert estimate_cost("claude-opus-4-6", 0, 500_000) == COST_RATES["claude-opus-4-6"]["output"] / 2


def test_estimate_cost_unknown_model_falls_back_to_flash():
    flash = COST_RATES["gemini-3.5-flash"]
    assert estimate_cost("does-not-exist", 1_000_000, 0) == flash["input"]


def test_build_accrual_default_prompts_shape_and_totals():
    acc = build_accrual()
    assert isinstance(acc, Accrual)
    assert len(acc.steps) == 12  # DEMO_PROMPTS
    # Router routes cheap prompts to cheap tiers, so it must beat the all-Opus baseline.
    assert acc.router_total < acc.baseline_total
    assert acc.savings_pct == (1 - acc.router_total / acc.baseline_total) * 100
    assert acc.savings_pct > 0
    # tier_counts covers every step and only uses the known tier labels.
    assert sum(acc.tier_counts.values()) == 12
    assert set(acc.tier_counts) <= {label for label, _ in TIER_MODEL.values()}
    # tier_cost sums (per tier) to the router total (within float tolerance).
    assert math.isclose(sum(acc.tier_cost.values()), acc.router_total, rel_tol=1e-9)


def test_build_accrual_cumulative_is_monotonic():
    acc = build_accrual()
    prev_r = prev_b = 0.0
    for step in acc.steps:
        assert step.cum_router >= prev_r
        assert step.cum_baseline >= prev_b
        prev_r, prev_b = step.cum_router, step.cum_baseline
    assert math.isclose(acc.steps[-1].cum_router, acc.router_total, rel_tol=1e-9)
    assert math.isclose(acc.steps[-1].cum_baseline, acc.baseline_total, rel_tol=1e-9)


def test_build_accrual_baseline_prices_every_prompt_at_opus():
    acc = build_accrual()
    for step in acc.steps:
        assert step.baseline_cost == estimate_cost(BASELINE_MODEL, 200, 500)


def test_build_accrual_custom_prompts():
    acc = build_accrual([{"prompt": "simple", "level": "low"}, {"prompt": "hard", "level": "high"}])
    assert [s.level for s in acc.steps] == ["low", "high"]
    assert acc.steps[0].tier == TIER_MODEL["low"][0]
    assert acc.steps[1].tier == TIER_MODEL["high"][0]
    assert isinstance(acc.to_dict(), dict) and acc.to_dict()["router_total"] == acc.router_total


def test_step_dataclass_fields():
    s = Step(1, "p", "low", "Lite", "gemini-3.1-flash-lite", 0.1, 0.5, 0.1, 0.5)
    assert (s.idx, s.level, s.tier, s.request_cost, s.cum_baseline) == (1, "low", "Lite", 0.1, 0.5)


def test_cost_rates_do_not_drift_from_canonical_tracker():
    """Every model the app prices must match src/router/cost_tracker on rate values."""
    from src.router.cost_tracker import COST_RATES as CANON
    for model, rate in COST_RATES.items():
        assert model in CANON, f"{model} missing from canonical cost_tracker.COST_RATES"
        assert rate == CANON[model], f"rate drift for {model}: app={rate} tracker={CANON[model]}"
