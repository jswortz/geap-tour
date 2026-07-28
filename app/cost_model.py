"""Deterministic cost-accrual model for the multi-model router.

Self-contained (no heavy ADK/MCP imports) so the Cloud Run image stays lean — the
pricing here mirrors ``src/router/cost_tracker.py`` (COST_RATES) and the tier mapping
mirrors ``src/router/agents.py`` / ``src/eval/complexity_metrics.py`` (MODEL_MAP).

For each demo prompt we know its complexity level, route it to the matching model tier,
and accumulate cost — alongside an "all-Opus" baseline where every prompt hits the
frontier model. That contrast is the whole story: the router spends frontier dollars only
on the prompts that need them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

# Pricing per 1M tokens — kept in sync with src/router/cost_tracker.py::COST_RATES.
COST_RATES: Dict[str, Dict[str, float]] = {
    "gemini-3.1-flash-lite": {"input": 0.075, "output": 0.30},
    "gemini-3.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-3.1-pro-preview": {"input": 1.25, "output": 10.00},
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "claude-opus-4-6": {"input": 15.00, "output": 75.00},
    "classifier": {"input": 0.075, "output": 0.30},
}

# Complexity level -> (tier label, model). Mirrors the router's delegation
# (low->lite, medium->flash, high->opus). The router also has pro/sonnet tiers;
# these three make the cost spread clearest for the demo.
TIER_MODEL = {
    "low": ("Lite", "gemini-3.1-flash-lite"),
    "medium": ("Flash", "gemini-3.5-flash"),
    "high": ("Opus", "claude-opus-4-6"),
}
BASELINE_MODEL = "claude-opus-4-6"  # "all-Opus" comparison

AVG_INPUT_TOKENS = 200
AVG_OUTPUT_TOKENS = 500
CLASSIFIER_IN = 40
CLASSIFIER_OUT = 20

# Demo prompt set (drawn from src/eval/agent_eval_configs.ROUTER_EVAL_CASES) — a realistic
# corporate travel/expense mix so ~half the traffic is genuinely simple.
DEMO_PROMPTS: List[Dict[str, str]] = [
    {"prompt": "Find flights from SFO to JFK", "level": "low"},
    {"prompt": "What's the expense policy for meals?", "level": "low"},
    {"prompt": "Search hotels in Chicago under $200", "level": "low"},
    {"prompt": "How much can I spend on meals per day while traveling?", "level": "low"},
    {"prompt": "Check if a $50 transport expense is within policy", "level": "low"},
    {"prompt": "Find flights to NYC and compare the cheapest options by airline", "level": "medium"},
    {"prompt": "Search hotels in Boston, then check if the nightly rate fits our lodging policy", "level": "medium"},
    {"prompt": "Show my expense history and flag any items that exceeded policy limits", "level": "medium"},
    {"prompt": "Plan a 5-day Tokyo trip for 4: flights, hotels near Shibuya, meal + entertainment budget", "level": "high"},
    {"prompt": "Compare individual vs group flight bookings for the Denver retreat with per-diem analysis", "level": "high"},
    {"prompt": "Analyze EMP001's expense history, draft a policy recommendation, and submit a $45 lunch receipt", "level": "high"},
    {"prompt": "Book cheapest SFO-JFK, find a nearby hotel, cross-reference ratings, check policy, submit pre-approval", "level": "high"},
]


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Cost in USD for one request. Mirrors src/router/cost_tracker.estimate_cost."""
    rate = COST_RATES.get(model, COST_RATES["gemini-3.5-flash"])
    return (input_tokens / 1_000_000) * rate["input"] + (output_tokens / 1_000_000) * rate["output"]


@dataclass
class Step:
    idx: int
    prompt: str
    level: str
    tier: str
    model: str
    request_cost: float
    baseline_cost: float
    cum_router: float
    cum_baseline: float


@dataclass
class Accrual:
    steps: List[Step] = field(default_factory=list)
    router_total: float = 0.0
    baseline_total: float = 0.0
    savings_pct: float = 0.0
    tier_counts: Dict[str, int] = field(default_factory=dict)
    tier_cost: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "router_total": self.router_total,
            "baseline_total": self.baseline_total,
            "savings_pct": self.savings_pct,
            "tier_counts": self.tier_counts,
            "tier_cost": self.tier_cost,
            "steps": [s.__dict__ for s in self.steps],
        }


def build_accrual(prompts: List[Dict[str, str]] | None = None) -> Accrual:
    """Route each prompt, accumulate router vs all-Opus cost, and summarize."""
    prompts = prompts or DEMO_PROMPTS
    acc = Accrual()
    cum_r = cum_b = 0.0
    classifier_overhead = estimate_cost("classifier", CLASSIFIER_IN, CLASSIFIER_OUT)
    for i, p in enumerate(prompts, 1):
        level = p["level"]
        tier, model = TIER_MODEL.get(level, TIER_MODEL["medium"])
        req = estimate_cost(model, AVG_INPUT_TOKENS, AVG_OUTPUT_TOKENS) + classifier_overhead
        base = estimate_cost(BASELINE_MODEL, AVG_INPUT_TOKENS, AVG_OUTPUT_TOKENS)
        cum_r += req
        cum_b += base
        acc.steps.append(Step(i, p["prompt"], level, tier, model, req, base, cum_r, cum_b))
        acc.tier_counts[tier] = acc.tier_counts.get(tier, 0) + 1
        acc.tier_cost[tier] = acc.tier_cost.get(tier, 0.0) + req
    acc.router_total = cum_r
    acc.baseline_total = cum_b
    acc.savings_pct = (1 - cum_r / cum_b) * 100 if cum_b else 0.0
    return acc
