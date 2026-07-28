"""Cost + accrual model for the live Router Cost Visualizer.

Self-contained (no heavy ADK/MCP imports) so the Cloud Run image stays lean. Pricing mirrors
``src/router/cost_tracker.py::COST_RATES``; the accrual accumulates the REAL per-prompt routing
results produced by ``app/router_logic.route_and_run`` (each prompt is actually classified and the
routed tier model is actually invoked, so tokens and cost are measured, not estimated).

Each step records the routed model's real cost alongside an "all-Opus" baseline priced at Opus rates
on the SAME real token counts — the contrast is the whole story: the router spends frontier dollars
only on the prompts that genuinely need them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

# Pricing per 1M tokens — kept in sync with src/router/cost_tracker.py::COST_RATES.
# MUST cover every model id in app.router_logic.TIER_MODEL (else cost silently falls back).
COST_RATES: Dict[str, Dict[str, float]] = {
    "gemini-3.1-flash-lite": {"input": 0.075, "output": 0.30},
    "gemini-3.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-3.1-pro-preview": {"input": 1.25, "output": 10.00},
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-opus-4-6": {"input": 15.00, "output": 75.00},
    "claude-opus-4-7": {"input": 15.00, "output": 75.00},
    "classifier": {"input": 0.075, "output": 0.30},
}

BASELINE_MODEL = "claude-opus-4-6"  # "all-Opus" comparison


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Cost in USD for one request. Mirrors src/router/cost_tracker.estimate_cost."""
    rate = COST_RATES.get(model, COST_RATES["gemini-3.5-flash"])
    return (input_tokens * rate["input"] + output_tokens * rate["output"]) / 1_000_000


@dataclass
class Step:
    idx: int
    prompt: str
    score: float
    reason: str
    tier: str          # display label: Lite / Flash / Sonnet / Pro / Opus
    model: str
    input_tokens: int
    output_tokens: int
    request_cost: float      # real routed cost (incl. classifier overhead)
    baseline_cost: float     # all-Opus on the same real tokens
    cum_router: float
    cum_baseline: float
    latency_ms: float = 0.0
    error: str = ""


@dataclass
class Accrual:
    steps: List[Step] = field(default_factory=list)
    router_total: float = 0.0
    baseline_total: float = 0.0
    savings_pct: float = 0.0
    tier_counts: Dict[str, int] = field(default_factory=dict)
    tier_cost: Dict[str, float] = field(default_factory=dict)

    def add(self, prompt: str, routed: dict) -> Step:
        """Append a real routed result (from router_logic.route_and_run) and recompute totals."""
        self.router_total += routed.get("cost", 0.0)
        self.baseline_total += routed.get("baseline_cost", 0.0)
        tier = routed.get("tier_label", routed.get("tier", "?"))
        step = Step(
            idx=len(self.steps) + 1,
            prompt=prompt,
            score=routed.get("score", 0.0),
            reason=routed.get("reason", ""),
            tier=tier,
            model=routed.get("model", ""),
            input_tokens=routed.get("input_tokens", 0),
            output_tokens=routed.get("output_tokens", 0),
            request_cost=routed.get("cost", 0.0),
            baseline_cost=routed.get("baseline_cost", 0.0),
            cum_router=self.router_total,
            cum_baseline=self.baseline_total,
            latency_ms=routed.get("latency_ms", 0.0),
            error=routed.get("error", ""),
        )
        self.steps.append(step)
        self.tier_counts[tier] = self.tier_counts.get(tier, 0) + 1
        self.tier_cost[tier] = self.tier_cost.get(tier, 0.0) + step.request_cost
        self.savings_pct = (1 - self.router_total / self.baseline_total) * 100 if self.baseline_total else 0.0
        return step

    def to_dict(self) -> dict:
        return {
            "router_total": self.router_total,
            "baseline_total": self.baseline_total,
            "savings_pct": self.savings_pct,
            "tier_counts": self.tier_counts,
            "tier_cost": self.tier_cost,
            "steps": [s.__dict__ for s in self.steps],
        }
