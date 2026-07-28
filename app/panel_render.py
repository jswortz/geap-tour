"""Render the live Router Cost Visualizer dashboards to PNG (matplotlib, Agg — no headless browser).

Gemini Enterprise only docks Image/WebFrame surfaces in the right-hand canvas panel (native components
render inline), and WebFrame renders blank in this deployment — so to show the dashboard "on the side"
we render it to a PNG per request from the live per-session accrual and serve it via a native Image.
Pure-pip (matplotlib), no system deps, so the Cloud Run image stays lean.

Two views, both laid out to fit the canvas panel without needing to scroll (per-row lists are capped):
  render_dashboard_png(acc)  — KPIs + cumulative-cost chart + tier spend + recent per-prompt routing.
  render_routing_png(acc)    — score→tier→token-rate table + this session's real routing decisions.
"""
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

from app.cost_model import COST_RATES
from app.router_logic import OPUS_MODEL, THRESHOLDS, TIER_LABEL, TIER_MODEL

# Google-Cloud-ish palette.
BLUE = "#1a73e8"
BLUE_D = "#174ea6"
INK = "#202124"
MUTED = "#5f6368"
LINE = "#dadce0"
OK = "#137333"
BASELINE = "#c5221f"
BG = "#f8f9fa"
TIER_ORDER = ["Lite", "Flash", "Sonnet", "Pro", "Opus"]
TIER_COLOR = {"Lite": "#34a853", "Flash": "#1a73e8", "Sonnet": "#a142f4", "Pro": "#f29900", "Opus": "#d93025"}
MAX_ROWS = 7  # cap per-prompt rows so the image fits the panel without scrolling

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "figure.facecolor": BG,
    "axes.facecolor": "white",
    "savefig.facecolor": BG,
})


def _money(x: float) -> str:
    if x == 0:
        return "$0"
    return f"${x:,.6f}" if abs(x) < 0.01 else (f"${x:,.4f}" if abs(x) < 1 else f"${x:,.2f}")


def _trunc(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _kpi(fig, x, y, w, h, label, value, accent=BLUE):
    """Draw a KPI card (figure-fraction coords)."""
    ax = fig.add_axes([x, y, w, h]); ax.axis("off")
    ax.add_patch(FancyBboxPatch((0.02, 0.08), 0.96, 0.84, boxstyle="round,pad=0.02,rounding_size=0.06",
                                linewidth=1, edgecolor="#eceff5", facecolor="white",
                                mutation_aspect=h / w))
    ax.plot([0.05, 0.95], [0.9, 0.9], color=accent, lw=3, solid_capstyle="round")
    ax.text(0.08, 0.62, label.upper(), fontsize=8.5, color=MUTED, weight="bold", va="center")
    ax.text(0.08, 0.32, value, fontsize=17, color=accent, weight="bold", va="center")


def _fig_to_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140, bbox_inches="tight", pad_inches=0.18)
    plt.close(fig)
    return buf.getvalue()


def render_dashboard_png(acc) -> bytes:
    fig = plt.figure(figsize=(8.6, 9.4))
    # Header
    hax = fig.add_axes([0, 0.93, 1, 0.07]); hax.axis("off")
    hax.add_patch(FancyBboxPatch((0.03, 0.05), 0.94, 0.9, boxstyle="round,pad=0.01,rounding_size=0.3",
                                 linewidth=0, facecolor=BLUE))
    hax.text(0.06, 0.5, "Multi-Model Router — Live Cost Dashboard", fontsize=15, color="white",
             weight="bold", va="center")

    n = len(acc.steps)
    opus_n = acc.tier_counts.get("Opus", 0)
    if n == 0:
        ax = fig.add_axes([0.06, 0.4, 0.88, 0.45]); ax.axis("off")
        ax.text(0.5, 0.7, "No prompts routed yet", fontsize=16, weight="bold", color=INK, ha="center")
        ax.text(0.5, 0.45, "Send a corporate travel or expense request and I'll classify it,\n"
                           "route it to the cheapest capable model, run it for real, and chart the\n"
                           "cost here vs an all-Opus baseline.", fontsize=11, color=MUTED, ha="center")
        return _fig_to_png(fig)

    # KPI row
    kx, kw, gap = 0.04, 0.223, 0.01
    _kpi(fig, kx + 0 * (kw + gap), 0.83, kw, 0.085, "Prompts routed", str(n))
    _kpi(fig, kx + 1 * (kw + gap), 0.83, kw, 0.085, "Smart Router", _money(acc.router_total))
    _kpi(fig, kx + 2 * (kw + gap), 0.83, kw, 0.085, "All-Opus base", _money(acc.baseline_total), accent=BASELINE)
    _kpi(fig, kx + 3 * (kw + gap), 0.83, kw, 0.085, "Savings", f"{acc.savings_pct:.1f}%", accent=OK)

    # Cumulative-cost line chart
    cax = fig.add_axes([0.09, 0.55, 0.86, 0.24])
    xs = [s.idx for s in acc.steps]
    cax.plot(xs, [s.cum_baseline for s in acc.steps], color=BASELINE, lw=2.2, ls="--", marker="o",
             ms=4, label="All-Opus baseline")
    cax.plot(xs, [s.cum_router for s in acc.steps], color=BLUE, lw=2.6, marker="o", ms=4, label="Smart Router")
    cax.fill_between(xs, [s.cum_router for s in acc.steps], color=BLUE, alpha=0.06)
    cax.set_title("Cumulative cost as prompts arrive (USD)", fontsize=11, color=INK, loc="left", weight="bold")
    cax.set_xlabel("Prompt #", fontsize=9, color=MUTED)
    cax.tick_params(labelsize=8, colors=MUTED)
    cax.set_xticks(xs)
    for sp in ("top", "right"):
        cax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        cax.spines[sp].set_color(LINE)
    cax.grid(axis="y", color="#eef1f5", lw=1)
    cax.legend(fontsize=8.5, frameon=False, loc="upper left")

    # Tier spend bar
    tiers = [t for t in TIER_ORDER if acc.tier_counts.get(t)]
    bax = fig.add_axes([0.09, 0.34, 0.86, 0.14])
    costs = [acc.tier_cost.get(t, 0.0) for t in tiers]
    bax.barh(tiers, costs, color=[TIER_COLOR[t] for t in tiers], height=0.6)
    for i, t in enumerate(tiers):
        bax.text(max(costs) * 0.01 if max(costs) else 0, i,
                 f"  {acc.tier_counts.get(t,0)} req · {_money(acc.tier_cost.get(t,0.0))}",
                 va="center", ha="left", fontsize=8.5, color=INK)
    bax.set_title("Real spend by model tier", fontsize=11, color=INK, loc="left", weight="bold")
    bax.tick_params(labelsize=9, colors=INK, length=0)
    bax.set_xticks([])
    for sp in bax.spines.values():
        sp.set_visible(False)
    bax.invert_yaxis()

    # Recent per-prompt routing table
    tax = fig.add_axes([0.04, 0.03, 0.92, 0.27]); tax.axis("off")
    shown = acc.steps[-MAX_ROWS:]
    hidden = n - len(shown)
    title = "Per-prompt routing & running total" + (f"  (latest {len(shown)} of {n})" if hidden else "")
    tax.text(0.01, 0.98, title, fontsize=11, weight="bold", color=INK, va="top")
    cols = [("#", 0.01), ("Prompt", 0.05), ("Score", 0.43), ("Tier", 0.51), ("In/Out", 0.62),
            ("Cost", 0.75), ("Running", 0.88)]
    y = 0.88
    for label, cx in cols:
        tax.text(cx, y, label, fontsize=8, weight="bold", color=MUTED, va="top")
    y -= 0.055
    for s in shown:
        tax.text(0.01, y, str(s.idx), fontsize=8.5, color=MUTED, va="top")
        tax.text(0.05, y, _trunc(s.prompt, 30), fontsize=8.5, color=INK, va="top")
        tax.text(0.43, y, f"{s.score:.2f}", fontsize=8.5, color=INK, va="top")
        tax.text(0.51, y, s.tier, fontsize=8.5, color=TIER_COLOR.get(s.tier, INK), weight="bold", va="top")
        tax.text(0.62, y, f"{s.input_tokens:,}/{s.output_tokens:,}", fontsize=8.5, color=INK, va="top")
        tax.text(0.75, y, _money(s.request_cost), fontsize=8.5, color=INK, va="top")
        tax.text(0.88, y, _money(s.cum_router), fontsize=8.5, color=BLUE_D, weight="bold", va="top")
        y -= 0.052
    tax.text(0.01, y - 0.01, f"Frontier (Opus) used for {opus_n} of {n} prompts · baseline = Opus rates "
             "on the same real tokens · pricing per 1M tokens", fontsize=7.5, color=MUTED, va="top", style="italic")
    return _fig_to_png(fig)


def render_routing_png(acc) -> bytes:
    fig = plt.figure(figsize=(8.6, 9.4))
    hax = fig.add_axes([0, 0.93, 1, 0.07]); hax.axis("off")
    hax.add_patch(FancyBboxPatch((0.03, 0.05), 0.94, 0.9, boxstyle="round,pad=0.01,rounding_size=0.3",
                                 linewidth=0, facecolor=BLUE_D))
    hax.text(0.06, 0.5, "How Prompts Get Routed — Scoring & Tokenomics", fontsize=14, color="white",
             weight="bold", va="center")

    # Score -> tier -> model -> rate table
    tax = fig.add_axes([0.04, 0.60, 0.92, 0.30]); tax.axis("off")
    tax.text(0.01, 0.98, "Complexity score  →  model tier  →  token price", fontsize=12, weight="bold",
             color=INK, va="top")
    cols = [("Tier", 0.01), ("Score", 0.16), ("Model", 0.32), ("$ in / 1M", 0.72), ("$ out / 1M", 0.87)]
    y = 0.85
    for label, cx in cols:
        tax.text(cx, y, label, fontsize=9, weight="bold", color=MUTED, va="top")
    y -= 0.09
    lo = 0.0
    for key in ["lite", "flash", "sonnet", "pro", "opus"]:
        hi = THRESHOLDS.get(key)
        rng = f"{lo:.2f}–{hi:.2f}" if hi is not None else f"{lo:.2f}–1.00"
        model = TIER_MODEL[key]
        rate = COST_RATES.get(model, {})
        tax.text(0.01, y, TIER_LABEL[key], fontsize=10, weight="bold", color=TIER_COLOR[TIER_LABEL[key]], va="top")
        tax.text(0.16, y, rng, fontsize=9.5, color=INK, va="top")
        tax.text(0.32, y, model, fontsize=9.5, color=INK, va="top", family="DejaVu Sans Mono")
        tax.text(0.72, y, f"${rate.get('input',0):.3f}", fontsize=9.5, color=INK, va="top")
        tax.text(0.87, y, f"${rate.get('output',0):.2f}", fontsize=9.5, color=INK, va="top")
        lo = hi if hi is not None else lo
        y -= 0.09
    orate = COST_RATES.get(OPUS_MODEL, COST_RATES["claude-opus-4-6"])
    lrate = COST_RATES["gemini-3.1-flash-lite"]
    tax.text(0.01, y - 0.02,
             f"Tokenomics: Opus costs {orate['input']/lrate['input']:.0f}x Lite on input and "
             f"{orate['output']/lrate['output']:.0f}x on output per token.\nRouting simple prompts to "
             "Lite/Flash keeps frontier dollars for the prompts that truly need reasoning.",
             fontsize=8.5, color=MUTED, va="top", style="italic")

    # This session's real routing decisions
    sax = fig.add_axes([0.04, 0.04, 0.92, 0.50]); sax.axis("off")
    sax.text(0.01, 0.99, "This session's routing decisions", fontsize=12, weight="bold", color=INK, va="top")
    if not acc.steps:
        sax.text(0.01, 0.9, "No prompts scored yet — send one from the dashboard and its real score, "
                 "reason, and chosen tier will appear here.", fontsize=10, color=MUTED, va="top")
        return _fig_to_png(fig)
    y = 0.93
    for s in acc.steps[-6:]:
        sax.text(0.01, y, f"#{s.idx}", fontsize=9, color=MUTED, va="top")
        sax.text(0.06, y, _trunc(s.prompt, 60), fontsize=9.5, color=INK, weight="bold", va="top")
        sax.text(0.86, y, f"{s.score:.2f} → {s.tier}", fontsize=9.5,
                 color=TIER_COLOR.get(s.tier, INK), weight="bold", va="top")
        y -= 0.045
        sax.text(0.06, y, f"Why: {_trunc(s.reason or '(no reason)', 92)}", fontsize=8.5, color=MUTED, va="top")
        y -= 0.04
        sax.text(0.06, y, f"{s.model} · {s.input_tokens:,} in / {s.output_tokens:,} out · {_money(s.request_cost)}",
                 fontsize=8.5, color=INK, va="top", family="DejaVu Sans Mono")
        y -= 0.058
    return _fig_to_png(fig)
