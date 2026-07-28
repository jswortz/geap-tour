"""Unit tests for the Router Cost Visualizer routing/cost logic (pure, no network)."""
import pytest

from app.cost_model import COST_RATES, Accrual, estimate_cost
from app.router_logic import TIER_MODEL, score_to_tier


@pytest.mark.parametrize("score,tier", [
    (0.0, "lite"), (0.29, "lite"),
    (0.30, "flash"), (0.44, "flash"),
    (0.45, "sonnet"), (0.59, "sonnet"),
    (0.60, "pro"), (0.79, "pro"),
    (0.80, "opus"), (1.0, "opus"),
])
def test_score_to_tier_boundaries(score, tier):
    assert score_to_tier(score) == tier


def test_every_tier_model_has_a_cost_rate():
    # Pitfall guard: a routed tier whose model id is missing from COST_RATES would silently
    # mis-price. Every tier model must be in the rate table.
    for tier, model in TIER_MODEL.items():
        assert model in COST_RATES, f"{tier} model {model} missing from COST_RATES"


def test_estimate_cost_known_and_fallback():
    # 1M input tokens on lite = $0.075 input rate exactly.
    assert estimate_cost("gemini-3.1-flash-lite", 1_000_000, 0) == pytest.approx(0.075)
    # 1M output tokens on opus = $75 output rate.
    assert estimate_cost("claude-opus-4-6", 0, 1_000_000) == pytest.approx(75.0)
    # Unknown model falls back to the flash rate (not zero).
    assert estimate_cost("nonexistent-model", 1_000_000, 0) == pytest.approx(COST_RATES["gemini-3.5-flash"]["input"])


def test_accrual_add_accumulates_and_computes_savings():
    acc = Accrual()
    # A cheap Lite prompt, then an expensive Opus prompt.
    acc.add("simple", {"score": 0.1, "reason": "one lookup", "tier_label": "Lite",
                       "model": "gemini-3.1-flash-lite", "input_tokens": 100, "output_tokens": 200,
                       "cost": 0.0001, "baseline_cost": 0.02})
    acc.add("complex", {"score": 0.9, "reason": "multi-step plan", "tier_label": "Opus",
                        "model": "claude-opus-4-6", "input_tokens": 300, "output_tokens": 800,
                        "cost": 0.06, "baseline_cost": 0.06})

    assert len(acc.steps) == 2
    assert acc.router_total == pytest.approx(0.0601)
    assert acc.baseline_total == pytest.approx(0.08)
    assert acc.savings_pct == pytest.approx((1 - 0.0601 / 0.08) * 100)
    assert acc.tier_counts == {"Lite": 1, "Opus": 1}
    assert acc.tier_cost["Opus"] == pytest.approx(0.06)
    # Running totals are cumulative.
    assert acc.steps[0].cum_router == pytest.approx(0.0001)
    assert acc.steps[1].cum_router == pytest.approx(0.0601)
    # Real per-step fields are carried through.
    assert acc.steps[1].score == 0.9 and acc.steps[1].reason == "multi-step plan"
    assert acc.steps[1].input_tokens == 300 and acc.steps[1].output_tokens == 800


def test_empty_accrual_savings_is_zero():
    assert Accrual().savings_pct == 0.0
