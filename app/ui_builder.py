"""Branded A2UI screen builder for the Router Cost Visualizer.

Like party-store-ge-a2ui/ui_builder.py, each screen is ONE self-contained ``WebFrameSrcdoc``
HTML panel (Google-Cloud-styled, inline SVG charts, no external JS) rendered in the GE side
canvas. ``build_cost_dashboard_command`` wraps it as an A2UI v0.8 command list; the executor
tags each as a DataPart ``mimeType=application/json+a2ui``.

Pure/stdlib only, so it renders identically in a headless screenshot and in Gemini Enterprise.
"""
from __future__ import annotations

import html
from typing import List

from app.cost_model import Accrual, build_accrual

# --- Google Cloud theme ----------------------------------------------------
BLUE = "#1a73e8"; BLUE_D = "#1967d2"; INK = "#202124"; MUTED = "#5f6368"
LINE = "#dadce0"; CHIP = "#e8f0fe"; OKG = "#e6f4ea"; OK = "#137333"
LITE_C = "#34a853"; FLASH_C = "#1a73e8"; OPUS_C = "#d93025"; BASE_C = "#c5221f"
TIER_COLOR = {"Lite": LITE_C, "Flash": FLASH_C, "Opus": OPUS_C}
LEVEL_LABEL = {"low": "Low", "medium": "Medium", "high": "High"}


def _fmt(x: float) -> str:
    return f"${x:,.4f}" if x < 1 else f"${x:,.2f}"


def _cumulative_chart_svg(acc: Accrual, w: int = 760, h: int = 300) -> str:
    """Two cumulative-cost lines (Smart Router vs all-Opus) over the prompt sequence."""
    steps = acc.steps
    n = len(steps)
    if n == 0:
        return "<svg viewBox='0 0 760 300'></svg>"
    pad_l, pad_r, pad_t, pad_b = 64, 18, 18, 40
    plot_w, plot_h = w - pad_l - pad_r, h - pad_t - pad_b
    ymax = max(acc.baseline_total, acc.router_total) * 1.08 or 1.0

    def X(i: int) -> float:
        return pad_l + (plot_w * (i / (n - 1 if n > 1 else 1)))

    def Y(v: float) -> float:
        return pad_t + plot_h - (plot_h * (v / ymax))

    def pts(getter) -> str:
        return " ".join(f"{X(i):.1f},{Y(getter(s)):.1f}" for i, s in enumerate(steps))

    base_pts = pts(lambda s: s.cum_baseline)
    router_pts = pts(lambda s: s.cum_router)
    # gridlines + y labels (4 bands)
    grid = ""
    for g in range(5):
        val = ymax * g / 4
        y = Y(val)
        grid += (f"<line x1='{pad_l}' y1='{y:.1f}' x2='{w - pad_r}' y2='{y:.1f}' "
                 f"stroke='#eef1f5' stroke-width='1'/>"
                 f"<text x='{pad_l - 8}' y='{y + 4:.1f}' text-anchor='end' font-size='11' fill='{MUTED}'>{_fmt(val)}</text>")
    # x ticks (every other)
    xt = ""
    for i in range(0, n, max(1, n // 6)):
        xt += (f"<text x='{X(i):.1f}' y='{h - pad_b + 20}' text-anchor='middle' font-size='11' fill='{MUTED}'>{i + 1}</text>")
    # area under router line
    area = f"{pad_l},{Y(0):.1f} " + router_pts + f" {X(n-1):.1f},{Y(0):.1f}"
    end_r = Y(acc.router_total); end_b = Y(acc.baseline_total)
    return f"""<svg width='100%' viewBox='0 0 {w} {h}' font-family='Roboto,Inter,sans-serif'>
<polygon points='{area}' fill='{BLUE}' opacity='0.06'/>
{grid}
<polyline points='{base_pts}' fill='none' stroke='{BASE_C}' stroke-width='2.5' stroke-dasharray='6 5' stroke-linejoin='round'/>
<polyline points='{router_pts}' fill='none' stroke='{BLUE}' stroke-width='3' stroke-linejoin='round'/>
<circle cx='{X(n-1):.1f}' cy='{end_b:.1f}' r='4' fill='{BASE_C}'/>
<circle cx='{X(n-1):.1f}' cy='{end_r:.1f}' r='4' fill='{BLUE}'/>
<text x='{X(n-1)-6:.1f}' y='{end_b-8:.1f}' text-anchor='end' font-size='12' font-weight='700' fill='{BASE_C}'>all-Opus {_fmt(acc.baseline_total)}</text>
<text x='{X(n-1)-6:.1f}' y='{end_r+16:.1f}' text-anchor='end' font-size='12' font-weight='700' fill='{BLUE_D}'>Smart Router {_fmt(acc.router_total)}</text>
<text x='{pad_l}' y='{h-6}' font-size='11' fill='{MUTED}'>Prompt #  →  cumulative cost (USD)</text>
</svg>"""


def _tier_bars(acc: Accrual) -> str:
    total = sum(acc.tier_counts.values()) or 1
    rows = ""
    for tier in ("Lite", "Flash", "Opus"):
        cnt = acc.tier_counts.get(tier, 0)
        cost = acc.tier_cost.get(tier, 0.0)
        pct = 100 * cnt / total
        c = TIER_COLOR[tier]
        rows += f"""<div class='trow'>
          <div class='tname'><span class='tdot' style='background:{c}'></span>{tier}</div>
          <div class='tbar'><span style='width:{pct:.0f}%;background:{c}'></span></div>
          <div class='tmeta'>{cnt} req · {_fmt(cost)}</div></div>"""
    return rows


def _prompt_rows(acc: Accrual) -> str:
    rows = ""
    for s in acc.steps:
        c = TIER_COLOR.get(s.tier, MUTED)
        rows += f"""<tr>
          <td class='num'>{s.idx}</td>
          <td class='pr'>{html.escape(s.prompt[:70])}{'…' if len(s.prompt) > 70 else ''}</td>
          <td><span class='chip' style='color:{c};background:{c}1a'>{LEVEL_LABEL.get(s.level, s.level)}</span></td>
          <td class='mono'>{html.escape(s.model)}</td>
          <td class='money'>{_fmt(s.request_cost)}</td>
          <td class='money tot'>{_fmt(s.cum_router)}</td></tr>"""
    return rows


def build_cost_dashboard_html(acc: Accrual | None = None) -> str:
    """Full standalone HTML for the router cost-accrual dashboard."""
    acc = acc or build_accrual()
    n = len(acc.steps)
    opus_n = acc.tier_counts.get("Opus", 0)
    return f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<link href='https://fonts.googleapis.com/css2?family=Google+Sans:wght@500;700&family=Roboto:wght@400;500;700&display=swap' rel='stylesheet'>
<style>
*{{box-sizing:border-box}} html,body{{margin:0;background:#f8f9fa;color:{INK};
font-family:'Roboto',-apple-system,Segoe UI,sans-serif;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:840px;margin:0 auto;padding:18px}}
.hero{{background:linear-gradient(120deg,#1a73e8 0%,#1967d2 60%,#174ea6 100%);color:#fff;
border-radius:16px;padding:18px 22px;box-shadow:0 12px 30px -14px rgba(26,115,232,.55)}}
.hero .chip{{font-family:'Google Sans';font-weight:700;font-size:12px;background:rgba(255,255,255,.22);
padding:4px 11px;border-radius:8px;letter-spacing:.04em}}
.hero h1{{font-family:'Google Sans';font-weight:700;font-size:22px;margin:10px 0 3px}}
.hero .sub{{font-size:13px;opacity:.95}}
.kpis{{display:flex;gap:12px;margin:14px 0}}
.kpi{{flex:1;background:#fff;border:1px solid #eceff5;border-top:3px solid {BLUE};border-radius:12px;
padding:12px 14px;box-shadow:0 6px 18px -12px rgba(16,24,40,.25)}}
.kpi.win{{border-top-color:{OK}}}
.kpi .lab{{font-size:10px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:{MUTED}}}
.kpi .val{{font-family:'Google Sans';font-weight:700;font-size:26px;margin-top:5px;line-height:1}}
.kpi.win .val{{color:{OK}}}
.kpi .foot{{font-size:11px;color:{MUTED};margin-top:4px}}
.card{{background:#fff;border:1px solid #eceff5;border-radius:14px;padding:14px 16px;margin:14px 0;
box-shadow:0 8px 24px -16px rgba(16,24,40,.3)}}
.card h2{{font-family:'Google Sans';font-weight:700;font-size:14px;margin:0 0 10px;
padding-left:9px;border-left:4px solid {BLUE}}}
.legend{{display:flex;gap:16px;font-size:12px;color:{MUTED};margin-top:2px}}
.legend b{{color:{INK}}} .lg{{display:inline-block;width:22px;height:0;border-top:3px solid;vertical-align:middle;margin-right:5px}}
.trow{{display:flex;align-items:center;gap:12px;margin:8px 0;font-size:13px}}
.tname{{width:78px;font-weight:600;display:flex;align-items:center;gap:7px}}
.tdot{{width:9px;height:9px;border-radius:50%;display:inline-block}}
.tbar{{flex:1;height:9px;border-radius:999px;background:#eef1f8;overflow:hidden}}
.tbar>span{{display:block;height:100%;border-radius:999px}}
.tmeta{{width:150px;text-align:right;font-size:12px;color:{MUTED}}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
th{{text-align:left;color:{MUTED};font-weight:500;font-size:11px;text-transform:uppercase;
letter-spacing:.03em;padding:6px 8px;border-bottom:2px solid #eceff5}}
td{{padding:7px 8px;border-bottom:1px solid #f1f3f4}}
td.num{{color:{MUTED};width:26px}} td.pr{{color:{INK}}}
td.mono,.mono{{font-family:'Roboto Mono',monospace;font-size:11.5px;color:#3c4043}}
td.money{{text-align:right;font-variant-numeric:tabular-nums}} td.tot{{font-weight:700;color:{BLUE_D}}}
.chip{{font-size:11px;font-weight:600;padding:2px 9px;border-radius:11px}}
.foot-note{{font-size:11.5px;color:{MUTED};text-align:center;padding:8px 0 2px}}
</style></head><body><div class='wrap'>
  <div class='hero'>
    <span class='chip'>MULTI-MODEL ROUTER</span>
    <h1>Cost accrual: Smart Router vs all-Opus</h1>
    <div class='sub'>A Flash-Lite micro-classifier scores each prompt's complexity and routes it to the
    cheapest capable tier — frontier dollars are spent only where they're earned.</div>
  </div>
  <div class='kpis'>
    <div class='kpi'><div class='lab'>Prompts</div><div class='val'>{n}</div><div class='foot'>{opus_n} routed to Opus</div></div>
    <div class='kpi'><div class='lab'>Smart Router</div><div class='val'>{_fmt(acc.router_total)}</div><div class='foot'>classified + routed</div></div>
    <div class='kpi'><div class='lab'>All-Opus baseline</div><div class='val'>{_fmt(acc.baseline_total)}</div><div class='foot'>every prompt on frontier</div></div>
    <div class='kpi win'><div class='lab'>Savings</div><div class='val'>{acc.savings_pct:.1f}%</div><div class='foot'>vs all-Opus</div></div>
  </div>
  <div class='card'>
    <h2>Cumulative cost as prompts arrive</h2>
    {_cumulative_chart_svg(acc)}
    <div class='legend'><span><span class='lg' style='border-color:{BLUE}'></span><b>Smart Router</b></span>
    <span><span class='lg' style='border-color:{BASE_C};border-top-style:dashed'></span><b>all-Opus</b> baseline</span></div>
  </div>
  <div class='card'>
    <h2>Where the traffic went (by tier)</h2>
    {_tier_bars(acc)}
  </div>
  <div class='card'>
    <h2>Per-prompt routing &amp; running total</h2>
    <table><thead><tr><th>#</th><th>Prompt</th><th>Complexity</th><th>Model</th><th style='text-align:right'>Req cost</th><th style='text-align:right'>Running</th></tr></thead>
    <tbody>{_prompt_rows(acc)}</tbody></table>
  </div>
  <div class='foot-note'>Pricing mirrors src/router/cost_tracker.py · assumes {200} in / {500} out tokens per request + classifier overhead.</div>
</div></body></html>"""


# --- A2UI command wrapper (WebFrameSrcdoc) ---------------------------------
def build_cost_dashboard_command(acc: Accrual | None = None, height: int = 1180) -> List[dict]:
    """A2UI v0.8 command list: begin render + a single WebFrameSrcdoc surface."""
    html_content = build_cost_dashboard_html(acc)
    # GE's canvas panel only renders the surface whose id is "canvas-surface"
    # (the party-store/rag reference plugin standardizes every surfaceId to this).
    # Any other surfaceId leaves the panel blank.
    surface_id = "canvas-surface"
    return [
        {"beginRendering": {"surfaceId": surface_id, "root": "root"}},
        {"surfaceUpdate": {"surfaceId": surface_id, "components": [
            {"id": "root", "component": {"WebFrameSrcdoc": {
                "htmlContent": {"literalString": html_content}, "height": height}}}
        ]}},
    ]
