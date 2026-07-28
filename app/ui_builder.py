"""Native A2UI v0.8 screen builders for the Router Cost Visualizer (Gemini Enterprise canvas).

Gemini Enterprise renders NATIVE A2UI components (Card / Row / Column / Divider / Text / Button and
an interactive Vega-Lite ``VegaChart``) but does NOT render inline WebFrameSrcdoc HTML. So every screen
here is built purely from native components — fully dynamic (driven by the live per-prompt accrual),
no static images, and it scrolls in the GE canvas. Mirrors the proven builders in
``dg-ge-data-agent/app/ui_builder.py``.

Two "tabs", switched by Button userActions handled in ``app/agent_executor.py``:
  * build_dashboard_screen(acc)      → live cost/routing dashboard (KPIs, cumulative-cost chart,
                                       tier breakdown, per-prompt routing).
  * build_routing_logic_screen(acc)  → teaches the scoring: score→tier→model, real token rates, and
                                       the classifier's real score+reason for each prompt this session.
"""
from __future__ import annotations

from typing import List

from app.cost_model import COST_RATES, Accrual
from app.router_logic import THRESHOLDS, TIER_LABEL, TIER_MODEL

SURFACE_ID = "router-cost"

# Colors for the Vega charts (Google-Cloud palette).
C_ROUTER = "#1a73e8"
C_BASELINE = "#c5221f"
TIER_COLOR = {"Lite": "#34a853", "Flash": "#1a73e8", "Sonnet": "#a142f4", "Pro": "#f29900", "Opus": "#d93025"}


def _fmt(x: float) -> str:
    if x == 0:
        return "$0"
    return f"${x:,.6f}" if abs(x) < 0.01 else (f"${x:,.4f}" if abs(x) < 1 else f"${x:,.2f}")


class _Screen:
    """Accumulates native A2UI components with unique ids and emits the command list."""

    def __init__(self) -> None:
        self.components: List[dict] = []
        self._n = 0

    def _id(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}-{self._n}"

    def text(self, s: str, hint: str = "body") -> str:
        cid = self._id("t")
        self.components.append({"id": cid, "component": {"Text": {"text": {"literalString": str(s)}, "usageHint": hint}}})
        return cid

    def card(self, child_id: str) -> str:
        cid = self._id("card")
        self.components.append({"id": cid, "component": {"Card": {"child": child_id}}})
        return cid

    def text_card(self, s: str, hint: str = "body") -> str:
        return self.card(self.text(s, hint))

    def col(self, child_ids: List[str]) -> str:
        cid = self._id("col")
        self.components.append({"id": cid, "component": {"Column": {"children": {"explicitList": child_ids}}}})
        return cid

    def row(self, child_ids: List[str], dist: str = "spaceBetween") -> str:
        cid = self._id("row")
        self.components.append({"id": cid, "component": {"Row": {"children": {"explicitList": child_ids}, "distribution": dist}}})
        return cid

    def divider(self) -> str:
        cid = self._id("div")
        self.components.append({"id": cid, "component": {"Divider": {}}})
        return cid

    def vega(self, spec: dict) -> str:
        cid = self._id("vega")
        self.components.append({"id": cid, "component": {"VegaChart": {"spec": spec}}})
        return self.card(cid)

    def button(self, label: str, action: str, primary: bool = False) -> str:
        eid = self._id("btn")
        tid = f"txt_{eid}"
        self.components.append({"id": eid, "component": {"Button": {"child": tid, "primary": primary, "action": {"name": action}}}})
        self.components.append({"id": tid, "component": {"Text": {"text": {"literalString": label}, "usageHint": "body"}}})
        return eid

    def build(self, root_child_ids: List[str]) -> List[dict]:
        self.components.insert(0, {"id": "root-layout", "component": {"Column": {"children": {"explicitList": root_child_ids}}}})
        return [
            {"beginRendering": {"surfaceId": SURFACE_ID, "root": "root-layout"}},
            {"surfaceUpdate": {"surfaceId": SURFACE_ID, "components": self.components}},
        ]


# --- Vega-Lite specs (real data, rendered natively by GE) ------------------
def _cumulative_cost_spec(acc: Accrual) -> dict:
    values = []
    for s in acc.steps:
        values.append({"n": s.idx, "cost": round(s.cum_router, 6), "series": "Smart Router"})
        values.append({"n": s.idx, "cost": round(s.cum_baseline, 6), "series": "All-Opus baseline"})
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "background": "transparent",
        "title": {"text": "Cumulative cost as prompts arrive (USD)", "fontSize": 13},
        "data": {"values": values},
        "mark": {"type": "line", "point": True, "strokeWidth": 3},
        "encoding": {
            "x": {"field": "n", "type": "ordinal", "title": "Prompt #"},
            "y": {"field": "cost", "type": "quantitative", "title": "Cumulative USD"},
            "color": {"field": "series", "type": "nominal", "title": None,
                      "scale": {"domain": ["Smart Router", "All-Opus baseline"], "range": [C_ROUTER, C_BASELINE]}},
            "tooltip": [{"field": "n", "title": "Prompt #"}, {"field": "series", "title": "Series"},
                        {"field": "cost", "title": "Cumulative USD", "format": "$.6f"}],
        },
        "width": "container",
        "height": 260,
    }


def _cost_by_tier_spec(acc: Accrual) -> dict:
    values = [{"tier": t, "cost": round(c, 6), "requests": acc.tier_counts.get(t, 0)}
              for t, c in acc.tier_cost.items()]
    order = ["Lite", "Flash", "Sonnet", "Pro", "Opus"]
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "background": "transparent",
        "title": {"text": "Real spend by model tier (USD)", "fontSize": 13},
        "data": {"values": values},
        "mark": {"type": "bar", "cornerRadiusEnd": 3},
        "encoding": {
            "x": {"field": "tier", "type": "nominal", "title": None, "sort": order},
            "y": {"field": "cost", "type": "quantitative", "title": "USD"},
            "color": {"field": "tier", "type": "nominal", "legend": None,
                      "scale": {"domain": order, "range": [TIER_COLOR[t] for t in order]}},
            "tooltip": [{"field": "tier", "title": "Tier"}, {"field": "requests", "title": "Requests"},
                        {"field": "cost", "title": "USD", "format": "$.6f"}],
        },
        "width": "container",
        "height": 240,
    }


# --- Screen 1: live cost dashboard -----------------------------------------
def build_dashboard_screen(acc: Accrual) -> List[dict]:
    sc = _Screen()
    root: List[str] = []

    header = sc.col([
        sc.text("⚡ Multi-Model Router — Live Cost Dashboard", "h2"),
        sc.text("Every prompt you send is classified, routed to the cheapest capable model, actually "
                "run, and priced from real token usage — vs an all-Opus baseline on the same tokens.", "body"),
    ])
    root.append(sc.card(header))

    if not acc.steps:
        empty = sc.col([
            sc.text("No prompts routed yet", "h3"),
            sc.text("Send a corporate travel or expense request (e.g. \"Find flights from SFO to JFK\" "
                    "or \"Plan a 5-day Tokyo trip for 4 with a budget\"). I'll classify its complexity, "
                    "route it to the right tier, run it for real, and chart the cost here.", "body"),
        ])
        root.append(sc.card(empty))
        root.append(sc.button("🔬 Routing logic & scoring", "view_routing", primary=True))
        return sc.build(root)

    n = len(acc.steps)
    opus_n = acc.tier_counts.get("Opus", 0)
    kpis = sc.row([
        sc.text_card(f"Prompts routed\n{n}", "h4"),
        sc.text_card(f"Smart Router\n{_fmt(acc.router_total)}", "h4"),
        sc.text_card(f"All-Opus baseline\n{_fmt(acc.baseline_total)}", "h4"),
        sc.text_card(f"Savings\n{acc.savings_pct:.1f}%", "h4"),
    ])
    root.append(kpis)
    root.append(sc.vega(_cumulative_cost_spec(acc)))

    root.append(sc.text("Where the traffic went (by tier)", "h3"))
    for tier in ("Lite", "Flash", "Sonnet", "Pro", "Opus"):
        cnt = acc.tier_counts.get(tier, 0)
        if cnt:
            root.append(sc.text_card(f"{tier} — {cnt} req · {_fmt(acc.tier_cost.get(tier, 0.0))}", "body"))

    root.append(sc.divider())
    root.append(sc.text("Per-prompt routing & running total", "h3"))
    for s in acc.steps:
        prompt = s.prompt if len(s.prompt) <= 90 else s.prompt[:88] + "…"
        line = (
            f"#{s.idx}  {s.tier}  (score {s.score:.2f})\n"
            f"{prompt}\n"
            f"{s.model} · {s.input_tokens:,} in / {s.output_tokens:,} out · "
            f"{_fmt(s.request_cost)}  (running {_fmt(s.cum_router)})"
        )
        if s.error:
            line += f"\n⚠️ {s.error}"
        root.append(sc.text_card(line, "body"))

    root.append(sc.divider())
    root.append(sc.button("🔬 Routing logic & scoring", "view_routing", primary=True))
    root.append(sc.button("↺ Reset session", "reset", primary=False))
    root.append(sc.text(f"Frontier (Opus) was used for {opus_n} of {n} prompts. "
                        "Baseline = Opus rates on the same real token counts.", "caption"))
    return sc.build(root)


# --- Screen 2: routing logic & scoring (tokenomics teaching) ----------------
def build_routing_logic_screen(acc: Accrual) -> List[dict]:
    sc = _Screen()
    root: List[str] = []

    header = sc.col([
        sc.text("🔬 How prompts get routed — scoring & tokenomics", "h2"),
        sc.text("A lightweight classifier scores each prompt 0–1 on complexity. The score selects a "
                "model tier; you pay that tier's token rates instead of always paying frontier prices.", "body"),
    ])
    root.append(sc.card(header))

    # Score → tier → model → real rates.
    root.append(sc.text("Complexity score → model tier → token price", "h3"))
    lo = 0.0
    order = ["lite", "flash", "sonnet", "pro", "opus"]
    for key in order:
        hi = THRESHOLDS.get(key)
        rng = f"{lo:.2f}–{hi:.2f}" if hi is not None else f"{lo:.2f}–1.00"
        model = TIER_MODEL[key]
        rate = COST_RATES.get(model, {})
        rate_str = f"${rate.get('input', 0):.3f} in / ${rate.get('output', 0):.2f} out per 1M tokens"
        root.append(sc.text_card(f"{TIER_LABEL[key]}  (score {rng})\n{model}\n{rate_str}", "body"))
        lo = hi if hi is not None else lo

    root.append(sc.text_card(
        "💡 Tokenomics: Opus costs 200× Lite on input and 250× on output per token. Routing the ~half "
        "of traffic that is simple to Lite/Flash keeps frontier dollars for the prompts that truly need "
        "multi-step reasoning — the savings compound with volume.", "body"))

    # This session's real routing decisions (real score + classifier reason).
    root.append(sc.divider())
    root.append(sc.text("This session's routing decisions", "h3"))
    if not acc.steps:
        root.append(sc.text_card("No prompts scored yet — send one from the Cost dashboard and its real "
                                 "score, reason, and chosen tier will appear here.", "body"))
    else:
        for s in acc.steps:
            prompt = s.prompt if len(s.prompt) <= 90 else s.prompt[:88] + "…"
            reason = s.reason or "(no reason returned)"
            root.append(sc.text_card(
                f"#{s.idx}  score {s.score:.2f} → {s.tier}\n"
                f"{prompt}\n"
                f"Why: {reason}\n"
                f"{s.model} · {s.input_tokens:,} in / {s.output_tokens:,} out · {_fmt(s.request_cost)}", "body"))
        root.append(sc.vega(_cost_by_tier_spec(acc)))

    root.append(sc.divider())
    root.append(sc.button("📊 Cost dashboard", "view_dashboard", primary=True))
    root.append(sc.button("↺ Reset session", "reset", primary=False))
    return sc.build(root)
