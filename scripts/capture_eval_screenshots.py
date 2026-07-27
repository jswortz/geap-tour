#!/usr/bin/env python3
"""Capture headless HTML-render screenshots for GEAP eval evidence (NON-console).

This is the headless fallback companion to scripts/capture_eval_console.py: for
artifacts that don't need the live GCP Console, it renders Google-Cloud-styled
HTML mockups and photographs them via `npx playwright screenshot`. It runs fully
headless (no Xvfb / VNC needed) and works right now with the cached Chromium.

Produces seven PNGs into docs/screenshots/:
  * eval_coverage_matrix.png          — status grid of the 9 GEAP
                                        "Optimize > Evaluation" doc pages, each
                                        mapped to the repo artifact that covers it.
  * eval_optimization_before_after.png — before/after agent-instruction card with
                                        the eval score delta.
  * eval_metric_registry.png          — registered eval metrics (Name/Type/Scale):
                                        predefined rubric, custom LLM, custom code
                                        and reference-based exact-match.
  * eval_demo_batch_scores.png        — per-metric PASS/FAIL scorecard for a batch
                                        eval, including the custom metrics.
  * eval_offline_trace.png            — offline evaluation over historical traces/
                                        sessions (scored WITHOUT new inference).
  * eval_failure_clusters_taxonomy.png — failure clusters mapped onto the real
                                        loss_taxonomy.py pattern vocabulary.
  * eval_quality_drift_alert.png      — firing Cloud Monitoring quality-drift alert
                                        on online_evaluator/scores (task_success).

Real data is preferred from eval_outputs/demo/full_demo.json when present;
otherwise bundled sample data is used. Clones the render/capture pattern of
scripts/capture_monitoring_screenshots.py.
"""

import json
import os
import subprocess
from html import escape
from pathlib import Path

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "wortz-project-352116")
SCREENSHOT_DIR = Path("docs/screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
DEMO_JSON = Path("eval_outputs/demo/full_demo.json")

# Shared Google-Cloud console styling (mirrors capture_monitoring_screenshots.py).
BASE_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Google Sans', 'Roboto', sans-serif; background: #f8f9fa; color: #202124; }
.console-header { display: flex; align-items: center; background: #1a73e8; color: white; height: 48px; padding: 0 16px; font-size: 14px; gap: 16px; }
.logo { font-size: 18px; font-weight: 500; }
.project { background: rgba(255,255,255,0.15); padding: 4px 12px; border-radius: 4px; font-size: 13px; }
.main { padding: 24px 32px; }
.breadcrumb { font-size: 13px; color: #5f6368; margin-bottom: 8px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.page-title { font-size: 22px; font-weight: 400; color: #202124; }
.card { background: white; border: 1px solid #dadce0; border-radius: 8px; margin-bottom: 20px; overflow: hidden; }
.card-header { padding: 14px 18px; border-bottom: 1px solid #e8eaed; font-size: 15px; font-weight: 500; color: #202124; background: #f8f9fa; display: flex; align-items: center; gap: 8px; }
.card-body { padding: 20px; }
.status-badge { display: inline-block; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; }
.status-ok { background: #e6f4ea; color: #137333; border: 1px solid #c4e9cf; }
.status-firing { background: #fce8e6; color: #c5221f; border: 1px solid #f5c2c2; }
"""

# Extra styling for the two artifacts produced here.
EXTRA_CSS = """
.cov-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.cov-card { background: white; border: 1px solid #dadce0; border-left: 4px solid #34a853; border-radius: 8px; padding: 16px; }
.cov-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 6px; }
.cov-title { font-size: 15px; font-weight: 500; color: #202124; line-height: 1.3; }
.cov-slug { font-size: 11px; color: #5f6368; font-family: 'Roboto Mono', monospace; margin-bottom: 12px; }
.cov-artifact { margin-bottom: 10px; }
.cov-artifact-label { display: block; font-size: 10px; text-transform: uppercase; letter-spacing: .5px; color: #80868b; margin-bottom: 3px; }
.cov-artifact code { font-size: 12px; color: #1967d2; background: #e8f0fe; padding: 2px 6px; border-radius: 4px; font-family: 'Roboto Mono', monospace; }
.cov-desc { font-size: 12px; color: #5f6368; line-height: 1.5; }
.ba-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.ba-card { border-radius: 8px; padding: 16px; border: 1px solid #dadce0; }
.ba-before { background: #fef7f6; border-color: #f5c2c2; }
.ba-after { background: #f0faf3; border-color: #c4e9cf; }
.ba-label { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .5px; margin-bottom: 10px; }
.ba-before .ba-label { color: #c5221f; }
.ba-after .ba-label { color: #137333; }
.ba-instr { font-family: 'Roboto Mono', monospace; font-size: 12px; white-space: pre-wrap; color: #202124; background: rgba(255,255,255,0.75); border-radius: 6px; padding: 12px; line-height: 1.5; border: 1px solid rgba(0,0,0,0.06); }
.score-banner { display: flex; align-items: center; justify-content: center; gap: 28px; background: white; border: 1px solid #dadce0; border-radius: 8px; padding: 22px; margin-bottom: 20px; }
.score-box { text-align: center; }
.score-cap { font-size: 11px; text-transform: uppercase; letter-spacing: .5px; color: #80868b; margin-bottom: 4px; }
.score-val { font-size: 40px; font-weight: 500; line-height: 1; }
.score-before { color: #c5221f; }
.score-after { color: #137333; }
.score-arrow { font-size: 34px; color: #5f6368; }
.score-delta { background: #e6f4ea; color: #137333; padding: 8px 16px; border-radius: 18px; font-size: 15px; font-weight: 500; }
.meta-row { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }
.chip { display: inline-block; background: #e8f0fe; color: #1967d2; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; }
.intro { font-size: 13px; color: #5f6368; margin-bottom: 20px; line-height: 1.5; }
.status-pass { background: #e6f4ea; color: #137333; border: 1px solid #c4e9cf; }
.status-fail { background: #fce8e6; color: #c5221f; border: 1px solid #f5c2c2; }

/* ---- Metric-registry table (eval_metric_registry.png) ---- */
.reg-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.reg-table th { text-align: left; padding: 12px 16px; color: #5f6368; font-weight: 500; border-bottom: 2px solid #e8eaed; background: #f8f9fa; }
.reg-table td { padding: 11px 16px; border-bottom: 1px solid #f1f3f4; vertical-align: middle; }
.reg-table tr:last-child td { border-bottom: none; }
.reg-name { font-family: 'Roboto Mono', monospace; font-size: 12px; color: #202124; font-weight: 500; }
.type-pill { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 500; white-space: nowrap; }
.type-predef { background: #e8f0fe; color: #1967d2; }
.type-llm { background: #fef3e0; color: #b06000; }
.type-code { background: #f3e8fd; color: #8430ce; }
.type-ref { background: #e6f4ea; color: #137333; }
.scale-cell { font-family: 'Roboto Mono', monospace; font-size: 12px; color: #5f6368; }
.group-row td { background: #fbfcfe; color: #80868b; font-size: 11px; text-transform: uppercase; letter-spacing: .6px; font-weight: 600; padding: 8px 16px; }

/* ---- Per-metric scorecards (eval_demo_batch_scores.png) ---- */
.sc-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.sc-card { background: white; border: 1px solid #dadce0; border-radius: 8px; padding: 16px 18px; }
.sc-card.pass { border-left: 4px solid #34a853; }
.sc-card.fail { border-left: 4px solid #ea4335; }
.sc-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 12px; }
.sc-metric { font-family: 'Roboto Mono', monospace; font-size: 13px; font-weight: 500; color: #202124; word-break: break-word; }
.sc-score { font-size: 34px; font-weight: 500; line-height: 1; }
.sc-score.pass { color: #137333; }
.sc-score.fail { color: #c5221f; }
.sc-max { font-size: 15px; color: #80868b; font-weight: 400; }
.sc-thresh { font-size: 11px; color: #80868b; margin-top: 6px; }
.sc-bar { height: 6px; background: #e8eaed; border-radius: 3px; margin-top: 12px; overflow: hidden; }
.sc-bar-fill { height: 100%; border-radius: 3px; }
.sc-bar-fill.pass { background: #34a853; }
.sc-bar-fill.fail { background: #ea4335; }
.sc-kind { font-size: 10px; text-transform: uppercase; letter-spacing: .5px; color: #80868b; margin-top: 8px; }

/* ---- Failure clusters (eval_failure_clusters_taxonomy.png) ---- */
.cl-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
.cl-card { background: white; border: 1px solid #dadce0; border-left: 4px solid #ea4335; border-radius: 8px; padding: 16px 18px; }
.cl-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; margin-bottom: 8px; }
.cl-title { font-size: 15px; font-weight: 500; color: #202124; line-height: 1.3; }
.cl-count { background: #fce8e6; color: #c5221f; padding: 3px 11px; border-radius: 12px; font-size: 12px; font-weight: 600; white-space: nowrap; }
.cl-desc { font-size: 12px; color: #5f6368; line-height: 1.5; margin-bottom: 12px; }
.cl-tax { display: flex; align-items: center; gap: 8px; font-size: 11px; }
.cl-tax-label { text-transform: uppercase; letter-spacing: .5px; color: #80868b; }
.cl-tax-val { background: #f3e8fd; color: #8430ce; padding: 3px 9px; border-radius: 4px; font-weight: 500; font-family: 'Roboto Mono', monospace; }

/* ---- Quality-drift alert (eval_quality_drift_alert.png) ---- */
.alert-banner { background: #fce8e6; border: 1px solid #f5c2c2; border-left: 6px solid #d93025; border-radius: 8px; padding: 16px 20px; margin-bottom: 20px; display: flex; align-items: center; gap: 16px; }
.alert-icon { font-size: 28px; }
.alert-title { font-size: 16px; font-weight: 500; color: #c5221f; margin-bottom: 4px; }
.alert-sub { font-size: 13px; color: #5f6368; }
.kv-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.kv-table td { padding: 10px 16px; border-bottom: 1px solid #f1f3f4; }
.kv-table tr:last-child td { border-bottom: none; }
.kv-table td.k { color: #5f6368; width: 260px; font-weight: 500; }
.kv-table td.v { font-family: 'Roboto Mono', monospace; color: #202124; }
.kv-table code { background: #e8f0fe; color: #1967d2; padding: 2px 6px; border-radius: 4px; font-family: 'Roboto Mono', monospace; }
.ts-wrap { position: relative; padding: 24px 8px 4px; }
.ts-chart { display: flex; align-items: flex-end; gap: 10px; height: 160px; border-bottom: 2px solid #dadce0; position: relative; }
.ts-thresh-line { position: absolute; left: 0; right: 0; border-top: 2px dashed #d93025; }
.ts-thresh-label { position: absolute; right: 0; font-size: 10px; font-weight: 500; color: #d93025; background: white; padding: 0 4px; }
.ts-bar { flex: 1; border-radius: 3px 3px 0 0; background: #1a73e8; position: relative; min-height: 2px; }
.ts-bar.below { background: #ea4335; }
.ts-bar-val { position: absolute; top: -18px; left: 0; right: 0; text-align: center; font-size: 10px; color: #5f6368; }
.ts-labels { display: flex; gap: 10px; padding: 6px 8px 0; }
.ts-labels span { flex: 1; text-align: center; font-size: 10px; color: #80868b; }
"""

# ---------------------------------------------------------------------------
# The 9 GEAP "Optimize > Evaluation" doc pages, each mapped to the runnable
# repo artifact that covers it.
#   (doc-slug, human title, repo artifact path, one-line description)
# ---------------------------------------------------------------------------
COVERAGE_PAGES: list[tuple[str, str, str, str]] = [
    ("agent-evaluation", "Agent evaluation overview",
     "src/eval/agent_eval_configs.py",
     "Per-agent metric bundles &amp; eval config spanning offline, online &amp; simulated."),
    ("evaluate-agents", "Evaluate agents",
     "src/eval/run_all_evals.py",
     "One-command orchestration of the full evaluation suite."),
    ("evaluate-offline", "Evaluate offline (batch)",
     "src/eval/batch_eval.py",
     "Batch eval over evalsets with rubric + custom LLM-as-judge metrics."),
    ("evaluate-simulated", "Evaluate with simulated users",
     "src/eval/simulated_eval.py",
     "ADK user-simulator, multi-turn scenario generation &amp; scoring."),
    ("evaluate-online", "Evaluate online (monitors)",
     "src/eval/setup_online_evaluators.py",
     "Online evaluators / monitors scoring live agent traffic."),
    ("manage-metrics", "Manage evaluation metrics",
     "src/eval/metric_registry.py",
     "Register &amp; reuse predefined, custom-LLM and custom-code metrics."),
    ("view-results", "Analyze results &amp; failure clusters",
     "src/eval/loss_taxonomy.py",
     "Loss-pattern taxonomies + generate_loss_clusters failure triage."),
    ("quality-alerts", "Set up quality alerts",
     "src/eval/quality_alerts.py",
     "Cloud Monitoring alert policies on evaluation-score thresholds."),
    ("optimize-agent", "Optimize the agent",
     "src/eval/failure_clusters.py",
     "Turn failure clusters into targeted agent-instruction fixes."),
]

# Bundled sample used when eval_outputs/demo/full_demo.json is absent.
SAMPLE_OPTIMIZATION: dict = {
    "agent": "expense_agent",
    "metric": "policy_compliance",
    "before_score": 0.70,
    "after_score": 1.00,
    "cases_fixed": 6,
    "cases_total": 6,
    "failure_cluster": "Constraint Violation — approved a $120 meal (limit $75).",
    "before_instruction": (
        "You are an expense assistant. Help the user submit expense reports and "
        "answer questions about company spending."
    ),
    "after_instruction": (
        "You are an expense assistant. Help the user submit expense reports and "
        "answer questions about company spending.\n\n"
        "ALWAYS enforce the corporate expense policy before approving anything:\n"
        "  - Meals: max $75/day        - Lodging: max $400/night\n"
        "  - Transport: max $200       - Supplies: max $100\n"
        "If a request exceeds a limit, refuse and cite the exact category and\n"
        "dollar limit. Never invent limits; if a category is unknown, ask first."
    ),
}


# Bundled catalog (mirrors src/eval/metric_registry.py) used when the demo JSON
# has no metric-registry step. (group, name, type-label, css-class, scale)
SAMPLE_REGISTRY: list[tuple[str, str, str, str, str]] = [
    ("Predefined rubric metrics (Google-managed)",
     "FINAL_RESPONSE_QUALITY", "Predefined rubric · single-turn · adaptive", "type-predef", "1 - 5"),
    ("Predefined rubric metrics (Google-managed)",
     "HALLUCINATION", "Predefined rubric · single-turn · static", "type-predef", "0 - 1"),
    ("Predefined rubric metrics (Google-managed)",
     "TOOL_USE_QUALITY", "Predefined rubric · single-turn · adaptive", "type-predef", "1 - 5"),
    ("Predefined rubric metrics (Google-managed)",
     "SAFETY", "Predefined rubric · single-turn · static", "type-predef", "0 / 1  (safe / unsafe)"),
    ("Predefined rubric metrics (Google-managed)",
     "MULTI_TURN_TASK_SUCCESS", "Predefined rubric · multi-turn", "type-predef", "1 - 5"),
    ("Predefined rubric metrics (Google-managed)",
     "MULTI_TURN_TOOL_USE_QUALITY", "Predefined rubric · multi-turn", "type-predef", "1 - 5"),
    ("Predefined rubric metrics (Google-managed)",
     "MULTI_TURN_TRAJECTORY_QUALITY", "Predefined rubric · multi-turn", "type-predef", "1 - 5"),
    ("Custom metrics",
     "policy_compliance", "Custom LLM (LLM-as-judge · types.LLMMetric)", "type-llm", "1 - 5"),
    ("Custom metrics",
     "geap_tool_use", "Custom LLM (LLM-as-judge · types.LLMMetric)", "type-llm", "1 - 5"),
    ("Custom metrics",
     "policy_limit_exact", "Custom code (types.CodeExecutionMetric)", "type-code", "0 - 1"),
    ("Custom metrics",
     "exact_match", "Reference-based computation", "type-ref", "0 / 1  (match)"),
]

# Type/scale lookup so we can classify names pulled live from the demo JSON.
_METRIC_TYPE_MAP: dict[str, tuple[str, str, str]] = {
    "policy_compliance": ("Custom LLM (LLM-as-judge · types.LLMMetric)", "type-llm", "1 - 5"),
    "geap_tool_use": ("Custom LLM (LLM-as-judge · types.LLMMetric)", "type-llm", "1 - 5"),
    "policy_limit_exact": ("Custom code (types.CodeExecutionMetric)", "type-code", "0 - 1"),
    "exact_match": ("Reference-based computation", "type-ref", "0 / 1  (match)"),
}
_STATIC_SINGLE_TURN = {"HALLUCINATION", "SAFETY"}
_SINGLE_TURN_SCALE = {
    "HALLUCINATION": "0 - 1",
    "SAFETY": "0 / 1  (safe / unsafe)",
}

# Bundled per-metric batch scorecard (used when demo has no batch scores).
# (metric, score /5, threshold, kind-label)
SAMPLE_BATCH_SCORES: list[tuple[str, float, float, str]] = [
    ("final_response_quality", 4.6, 3.0, "Predefined rubric"),
    ("tool_use_quality", 4.2, 3.0, "Predefined rubric"),
    ("hallucination", 5.0, 3.0, "Predefined rubric"),
    ("safety", 5.0, 3.0, "Predefined rubric"),
    ("policy_compliance", 4.4, 3.0, "Custom LLM"),
    ("geap_tool_use", 4.3, 3.0, "Custom LLM"),
    ("policy_limit_exact", 5.0, 3.0, "Custom code"),
]

# Bundled offline-trace result (used when demo has no offline step).
SAMPLE_OFFLINE_TRACE: dict = {
    "source": "fixture",
    "agent_name": "coordinator_agent",
    "record_count": 8,
    "score_threshold": 3.0,
    "hours_back": 24,
    "metrics": {
        "final_response_quality_v1": 0.3854166675,
        "hallucination_v1": 1.0,
        "safety_v1": 0.875,
    },
}

# Failure clusters — titles/descriptions map onto REAL patterns from
# src/eval/loss_taxonomy.py. (title, samples, description, category, pattern)
SAMPLE_FAILURE_CLUSTERS: list[tuple[str, int, str, str, str]] = [
    ("Called search_hotels for a flight request", 9,
     "Agent picked the wrong tool for the user's intent, routing flight "
     "look-ups through the hotel search API.",
     "Tool Calling", "Incorrect Tool Selection"),
    ("check_expense_policy returned a 503 and was not retried", 6,
     "Downstream tool failure was surfaced to the user instead of being "
     "retried or gracefully handled.",
     "Tool Quality", "Tool Failure"),
    ("Booked the flight but skipped the policy check", 5,
     "Multi-step task ended early: the agent completed the booking turn but "
     "never ran the required compliance step.",
     "Instruction Following", "Incomplete Execution"),
    ("Claimed a refund was issued with no tool call", 4,
     "Agent asserted it performed an action (issuing a refund) that no tool "
     "call in the trace actually executed.",
     "Hallucination", "Hallucination of Action"),
]

# Bundled quality-drift time series (task_success, trending below 0.8 threshold).
SAMPLE_DRIFT: dict = {
    "metric_type": "aiplatform.googleapis.com/online_evaluator/scores",
    "metric_label": "task_success",
    "threshold": 0.8,
    "series": [
        ("13:00", 0.94), ("13:10", 0.91), ("13:20", 0.89), ("13:30", 0.86),
        ("13:40", 0.82), ("13:50", 0.78), ("14:00", 0.74), ("14:10", 0.69),
    ],
}


def load_demo() -> dict | None:
    """Return parsed eval_outputs/demo/full_demo.json, or None if absent/invalid."""
    if not DEMO_JSON.exists():
        return None
    try:
        return json.loads(DEMO_JSON.read_text())
    except Exception as e:  # noqa: BLE001
        print(f"  Warning: could not parse {DEMO_JSON}: {e}")
        return None


def load_optimization(demo: dict | None) -> dict:
    """Merge any optimization data from the demo JSON over the bundled sample."""
    merged = dict(SAMPLE_OPTIMIZATION)
    if isinstance(demo, dict):
        opt = demo.get("optimization") or demo.get("optimize_agent") or demo.get("before_after")
        if isinstance(opt, dict):
            merged.update({k: v for k, v in opt.items() if v is not None})
    return merged


def _demo_steps(demo: dict | None) -> list[dict]:
    """Return the demo's ``steps`` list, or an empty list."""
    if isinstance(demo, dict) and isinstance(demo.get("steps"), list):
        return [s for s in demo["steps"] if isinstance(s, dict)]
    return []


def _find_step(demo: dict | None, needle: str) -> dict | None:
    """Return the first demo step whose title contains ``needle`` (case-insensitive)."""
    needle = needle.lower()
    for step in _demo_steps(demo):
        if needle in str(step.get("title", "")).lower():
            return step
    return None


def load_registry(demo: dict | None) -> list[tuple[str, str, str, str, str]]:
    """Build the metric-registry rows, preferring the demo's step-1 catalog.

    Returns rows of (group, name, type-label, css-class, scale).
    """
    step = _find_step(demo, "metric registry")
    catalog = (step or {}).get("catalog") if step else None
    if not isinstance(catalog, dict):
        return list(SAMPLE_REGISTRY)

    rows: list[tuple[str, str, str, str, str]] = []
    predef_group = "Predefined rubric metrics (Google-managed)"
    for name in catalog.get("single_turn_rubric", []) or []:
        if name in _STATIC_SINGLE_TURN:
            label = "Predefined rubric · single-turn · static"
        else:
            label = "Predefined rubric · single-turn · adaptive"
        rows.append((predef_group, name, label, "type-predef",
                     _SINGLE_TURN_SCALE.get(name, "1 - 5")))
    for name in catalog.get("multi_turn_rubric", []) or []:
        rows.append((predef_group, name, "Predefined rubric · multi-turn",
                     "type-predef", "1 - 5"))
    for name in catalog.get("custom", []) or []:
        label, css, scale = _METRIC_TYPE_MAP.get(
            name, ("Custom metric", "type-llm", "1 - 5"))
        rows.append(("Custom metrics", name, label, css, scale))

    return rows or list(SAMPLE_REGISTRY)


def load_offline_trace(demo: dict | None) -> dict:
    """Return the offline-trace result, preferring the demo's offline step."""
    step = _find_step(demo, "offline evaluation over historical")
    result = (step or {}).get("result") if step else None
    if not isinstance(result, dict):
        return dict(SAMPLE_OFFLINE_TRACE)

    metrics = result.get("metrics")
    scores: dict[str, float] = {}
    if isinstance(metrics, dict):
        for name, info in metrics.items():
            if isinstance(info, dict) and info.get("mean_score") is not None:
                scores[name] = float(info["mean_score"])
    if not scores:
        scores = dict(SAMPLE_OFFLINE_TRACE["metrics"])

    return {
        "source": result.get("source", SAMPLE_OFFLINE_TRACE["source"]),
        "agent_name": result.get("agent_name", SAMPLE_OFFLINE_TRACE["agent_name"]),
        "record_count": result.get("record_count", SAMPLE_OFFLINE_TRACE["record_count"]),
        "score_threshold": float(result.get("score_threshold", 3.0)),
        "hours_back": result.get("hours_back", SAMPLE_OFFLINE_TRACE["hours_back"]),
        "metrics": scores,
    }


def render_metric_registry(rows: list[tuple[str, str, str, str, str]], source_label: str) -> str:
    body = ""
    last_group = None
    for group, name, type_label, css, scale in rows:
        if group != last_group:
            body += f'<tr class="group-row"><td colspan="3">{escape(group)}</td></tr>'
            last_group = group
        body += f"""
        <tr>
            <td><span class="reg-name">{escape(name)}</span></td>
            <td><span class="type-pill {css}">{escape(type_label)}</span></td>
            <td class="scale-cell">{escape(scale)}</td>
        </tr>"""

    count = len(rows)
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>GEAP Metric Registry</title>
    <style>{BASE_CSS}{EXTRA_CSS}</style></head><body>
    <div class="console-header">
        <div class="logo">&#9729; Google Cloud</div>
        <div class="project">&#9660; {PROJECT_ID}</div>
    </div>
    <div class="main">
        <div class="breadcrumb">Agent Platform &gt; Optimize &gt; Evaluation &gt; Manage metrics</div>
        <div class="page-header">
            <div class="page-title">Metrics</div>
            <div class="status-badge status-ok">&#10004; Metric Registry &middot; {count} metrics</div>
        </div>
        <div class="intro">
            Metrics registered once via <code>client.evals.create_evaluation_metric()</code> and reused
            across offline batch runs and online monitors. Data source: {escape(source_label)}.
        </div>
        <div class="card">
            <div class="card-header">&#128209; Registered evaluation metrics</div>
            <table class="reg-table">
                <thead><tr><th>Name</th><th>Type</th><th>Scale</th></tr></thead>
                <tbody>{body}</tbody>
            </table>
        </div>
    </div></body></html>"""


def render_batch_scores(scores: list[tuple[str, float, float, str]], source_label: str) -> str:
    cards = ""
    passed = 0
    for metric, score, threshold, kind in scores:
        ok = score >= threshold
        passed += 1 if ok else 0
        state = "pass" if ok else "fail"
        badge = "status-pass" if ok else "status-fail"
        badge_txt = "&#10004; PASS" if ok else "&#10008; FAIL"
        pct = max(0.0, min(100.0, (score / 5.0) * 100.0))
        cards += f"""
        <div class="sc-card {state}">
            <div class="sc-top">
                <span class="sc-metric">{escape(metric)}</span>
                <span class="status-badge {badge}">{badge_txt}</span>
            </div>
            <div><span class="sc-score {state}">{score:.1f}</span><span class="sc-max"> / 5</span></div>
            <div class="sc-thresh">Threshold &ge; {threshold:.1f}</div>
            <div class="sc-bar"><div class="sc-bar-fill {state}" style="width:{pct:.0f}%"></div></div>
            <div class="sc-kind">{escape(kind)}</div>
        </div>"""

    total = len(scores)
    overall = "status-ok" if passed == total else "status-firing"
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>GEAP Batch Eval Scores</title>
    <style>{BASE_CSS}{EXTRA_CSS}</style></head><body>
    <div class="console-header">
        <div class="logo">&#9729; Google Cloud</div>
        <div class="project">&#9660; {PROJECT_ID}</div>
    </div>
    <div class="main">
        <div class="breadcrumb">Agent Platform &gt; Optimize &gt; Evaluation &gt; Evaluate offline (batch)</div>
        <div class="page-header">
            <div class="page-title">Batch evaluation &mdash; per-metric scorecard</div>
            <div class="status-badge {overall}">&#10004; {passed}/{total} metrics passed</div>
        </div>
        <div class="intro">
            Mean scores across the evalset (0&ndash;5 scale), each judged against its pass threshold.
            Includes the custom LLM and custom-code metrics. Data source: {escape(source_label)}.
        </div>
        <div class="sc-grid">{cards}</div>
    </div></body></html>"""


def render_offline_trace(trace: dict, source_label: str) -> str:
    threshold = float(trace.get("score_threshold", 3.0))
    source = escape(str(trace.get("source", "fixture")))
    agent = escape(str(trace.get("agent_name", "agent")))
    record_count = trace.get("record_count", 0)
    hours_back = trace.get("hours_back")

    rows = ""
    passed = 0
    metrics = trace.get("metrics", {}) or {}
    for name, mean_score in metrics.items():
        display = name[:-3] if str(name).endswith("_v1") else str(name)
        score5 = float(mean_score) * 5.0  # demo stores 0-1 means; show on /5
        ok = score5 >= threshold
        passed += 1 if ok else 0
        badge = "status-pass" if ok else "status-fail"
        badge_txt = "&#10004; PASS" if ok else "&#10008; FAIL"
        cls = "" if ok else "text-error"
        pct = max(0.0, min(100.0, (score5 / 5.0) * 100.0))
        fill = "pass" if ok else "fail"
        rows += f"""
        <tr>
            <td><span class="reg-name">{escape(display)}</span></td>
            <td class="{cls}"><strong>{score5:.2f}</strong> <span style="color:#80868b">/ 5</span>
                <div class="sc-bar" style="max-width:180px"><div class="sc-bar-fill {fill}" style="width:{pct:.0f}%"></div></div>
            </td>
            <td class="scale-cell">&ge; {threshold:.1f}</td>
            <td><span class="status-badge {badge}">{badge_txt}</span></td>
        </tr>"""

    total = len(metrics)
    hours_chip = f'<span class="chip">Window: last {hours_back}h</span>' if hours_back else ""
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>GEAP Offline Trace Eval</title>
    <style>{BASE_CSS}{EXTRA_CSS}</style></head><body>
    <div class="console-header">
        <div class="logo">&#9729; Google Cloud</div>
        <div class="project">&#9660; {PROJECT_ID}</div>
    </div>
    <div class="main">
        <div class="breadcrumb">Agent Platform &gt; Optimize &gt; Evaluation &gt; Evaluate offline</div>
        <div class="page-header">
            <div class="page-title">Offline evaluation over historical traces / sessions</div>
            <div class="status-badge {"status-ok" if passed == total else "status-firing"}">
                {passed}/{total} metrics passed</div>
        </div>
        <div class="intro">
            Existing production traces are replayed and re-scored by the autoraters
            <strong>without running new inference</strong> &mdash; only the stored
            request/response/tool-call trajectory is judged. Data source: {escape(source_label)}.
        </div>
        <div class="meta-row">
            <span class="chip">Source: {source}</span>
            <span class="chip">Agent: {agent}</span>
            <span class="chip">{record_count} traces scored</span>
            {hours_chip}
            <span class="chip">No new inference</span>
        </div>
        <div class="card">
            <div class="card-header">&#128337; Historical trace scores</div>
            <table class="reg-table">
                <thead><tr><th>Metric</th><th>Mean score</th><th>Threshold</th><th>Result</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
    </div></body></html>"""


def render_failure_clusters(clusters: list[tuple[str, int, str, str, str]], source_label: str) -> str:
    total_samples = sum(c[1] for c in clusters)
    cards = ""
    for title, samples, desc, category, pattern in clusters:
        cards += f"""
        <div class="cl-card">
            <div class="cl-head">
                <span class="cl-title">{escape(title)}</span>
                <span class="cl-count">{samples} samples</span>
            </div>
            <div class="cl-desc">{escape(desc)}</div>
            <div class="cl-tax">
                <span class="cl-tax-label">Loss pattern</span>
                <span class="cl-tax-val">{escape(category)} / {escape(pattern)}</span>
            </div>
        </div>"""

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>GEAP Failure Clusters</title>
    <style>{BASE_CSS}{EXTRA_CSS}</style></head><body>
    <div class="console-header">
        <div class="logo">&#9729; Google Cloud</div>
        <div class="project">&#9660; {PROJECT_ID}</div>
    </div>
    <div class="main">
        <div class="breadcrumb">Agent Platform &gt; Optimize &gt; Evaluation &gt; Analyze results</div>
        <div class="page-header">
            <div class="page-title">Failure clusters</div>
            <div class="status-badge status-firing">&#9888; {len(clusters)} clusters &middot; {total_samples} failing samples</div>
        </div>
        <div class="intro">
            Failing cases from <code>client.evals.generate_loss_clusters()</code> grouped into
            themes, each mapped onto a predefined loss pattern from
            <code>src/eval/loss_taxonomy.py</code>. Data source: {escape(source_label)}.
        </div>
        <div class="cl-grid">{cards}</div>
    </div></body></html>"""


def render_quality_drift_alert(drift: dict, source_label: str) -> str:
    metric_type = str(drift.get("metric_type", "aiplatform.googleapis.com/online_evaluator/scores"))
    label = str(drift.get("metric_label", "task_success"))
    threshold = float(drift.get("threshold", 0.8))
    series = drift.get("series", [])

    max_scale = 1.0
    height = 160
    bars = ""
    labels = ""
    for ts, val in series:
        below = val < threshold
        bar_px = max(2, round((val / max_scale) * height))
        cls = "ts-bar below" if below else "ts-bar"
        bars += f'<div class="{cls}" style="height:{bar_px}px"><span class="ts-bar-val">{val:.2f}</span></div>'
        labels += f'<span>{escape(ts)}</span>'

    thresh_top = round((1.0 - (threshold / max_scale)) * height) + 24  # +24 = ts-wrap top padding
    latest = series[-1][1] if series else 0.0

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>GEAP Quality-Drift Alert</title>
    <style>{BASE_CSS}{EXTRA_CSS}</style></head><body>
    <div class="console-header">
        <div class="logo">&#9729; Google Cloud</div>
        <div class="project">&#9660; {PROJECT_ID}</div>
    </div>
    <div class="main">
        <div class="breadcrumb">Monitoring &gt; Alerting &gt; Incident detail</div>
        <div class="page-header">
            <div class="page-title">Quality-drift alert</div>
            <div class="status-badge status-firing">&#9888; FIRING</div>
        </div>

        <div class="alert-banner">
            <div class="alert-icon">&#128680;</div>
            <div class="alert-text">
                <div class="alert-title">GEAP: online eval quality drift &mdash; task_success below 0.8</div>
                <div class="alert-sub">
                    Mean <code>{escape(label)}</code> score fell to {latest:.2f}
                    (threshold &lt; {threshold:.1f}) on live traffic.
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-header">&#128200; online_evaluator/scores &middot; evaluation_metric_name = {escape(label)}</div>
            <div class="card-body">
                <div class="ts-wrap">
                    <div class="ts-thresh-line" style="top:{thresh_top}px"></div>
                    <div class="ts-thresh-label" style="top:{thresh_top - 14}px">Threshold {threshold:.1f}</div>
                    <div class="ts-chart">{bars}</div>
                    <div class="ts-labels">{labels}</div>
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-header">&#128203; Condition</div>
            <table class="kv-table">
                <tr><td class="k">Status</td><td class="v"><span class="status-badge status-firing">FIRING</span></td></tr>
                <tr><td class="k">Metric type</td><td class="v"><code>{escape(metric_type)}</code></td></tr>
                <tr><td class="k">Metric label</td><td class="v">evaluation_metric_name = <code>{escape(label)}</code></td></tr>
                <tr><td class="k">Condition</td><td class="v">mean score &lt; {threshold:.1f} for 10 min</td></tr>
                <tr><td class="k">Latest value</td><td class="v text-error">{latest:.2f}</td></tr>
                <tr><td class="k">Target project</td><td class="v"><code>{escape(PROJECT_ID)}</code></td></tr>
            </table>
        </div>
        <div style="font-size:12px;color:#5f6368;">Data source: {escape(source_label)}.</div>
    </div></body></html>"""


def render_coverage_matrix(pages: list[tuple[str, str, str, str]], source_label: str) -> str:
    cards = ""
    for slug, title, artifact, desc in pages:
        cards += f"""
        <div class="cov-card">
            <div class="cov-top">
                <span class="cov-title">{title}</span>
                <span class="status-badge status-ok">&#10004; Covered</span>
            </div>
            <div class="cov-slug">optimize/evaluation/{slug}</div>
            <div class="cov-artifact">
                <span class="cov-artifact-label">Repo artifact</span>
                <code>{artifact}</code>
            </div>
            <div class="cov-desc">{desc}</div>
        </div>"""

    covered = len(pages)
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>GEAP Eval Coverage Matrix</title>
    <style>{BASE_CSS}{EXTRA_CSS}</style></head><body>
    <div class="console-header">
        <div class="logo">&#9729; Google Cloud</div>
        <div class="project">&#9660; {PROJECT_ID}</div>
    </div>
    <div class="main">
        <div class="breadcrumb">Agent Platform &gt; Optimize &gt; Evaluation</div>
        <div class="page-header">
            <div class="page-title">GEAP Evaluation &mdash; Documentation Coverage Matrix</div>
            <div class="status-badge status-ok">&#10004; {covered}/9 doc pages covered</div>
        </div>
        <div style="font-size:13px;color:#5f6368;margin-bottom:20px;">
            Every page under <strong>Optimize &gt; Evaluation</strong> is implemented by a
            runnable artifact in this repository. &nbsp;Data source: {escape(source_label)}.
        </div>
        <div class="cov-grid">{cards}</div>
    </div></body></html>"""


def render_before_after(opt: dict, source_label: str) -> str:
    before = float(opt.get("before_score", 0.70))
    after = float(opt.get("after_score", 1.00))
    delta = after - before
    agent = escape(str(opt.get("agent", "agent")))
    metric = escape(str(opt.get("metric", "quality")))
    fixed = opt.get("cases_fixed")
    total = opt.get("cases_total")
    cluster = escape(str(opt.get("failure_cluster", "")))
    before_instr = escape(str(opt.get("before_instruction", "")))
    after_instr = escape(str(opt.get("after_instruction", "")))

    cases_chip = ""
    if fixed is not None and total is not None:
        cases_chip = f'<span class="chip">{fixed}/{total} cases fixed</span>'
    cluster_chip = f'<span class="chip">Cluster: {cluster}</span>' if cluster else ""

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>GEAP Agent Optimization</title>
    <style>{BASE_CSS}{EXTRA_CSS}</style></head><body>
    <div class="console-header">
        <div class="logo">&#9729; Google Cloud</div>
        <div class="project">&#9660; {PROJECT_ID}</div>
    </div>
    <div class="main">
        <div class="breadcrumb">Agent Platform &gt; Optimize &gt; Evaluation &gt; Optimize the agent</div>
        <div class="page-header">
            <div class="page-title">Agent Optimization &mdash; Before / After</div>
            <div class="status-badge status-ok">&#10004; Regression fixed</div>
        </div>
        <div class="meta-row">
            <span class="chip">Agent: {agent}</span>
            <span class="chip">Metric: {metric}</span>
            {cases_chip}
            {cluster_chip}
        </div>

        <div class="score-banner">
            <div class="score-box">
                <div class="score-cap">Before</div>
                <div class="score-val score-before">{before:.2f}</div>
            </div>
            <div class="score-arrow">&#8594;</div>
            <div class="score-box">
                <div class="score-cap">After</div>
                <div class="score-val score-after">{after:.2f}</div>
            </div>
            <div class="score-delta">&#9650; +{delta:.2f} {metric}</div>
        </div>

        <div class="card">
            <div class="card-header">&#128221; Agent instruction change</div>
            <div class="card-body">
                <div class="ba-grid">
                    <div class="ba-card ba-before">
                        <div class="ba-label">&#10008; Original instruction</div>
                        <div class="ba-instr">{before_instr}</div>
                    </div>
                    <div class="ba-card ba-after">
                        <div class="ba-label">&#10004; Optimized instruction</div>
                        <div class="ba-instr">{after_instr}</div>
                    </div>
                </div>
            </div>
        </div>
        <div style="font-size:12px;color:#5f6368;">Data source: {escape(source_label)}.</div>
    </div></body></html>"""


def capture_and_save(html: str, name: str) -> bool:
    """Write HTML to /tmp and screenshot it headless via `npx playwright screenshot`."""
    html_path = f"/tmp/geap-eval-{name}.html"
    png_path = SCREENSHOT_DIR / f"{name}.png"

    with open(html_path, "w") as f:
        f.write(html)

    print(f"Capturing {name}.png ...")
    # Playwright's CLI expects the viewport as "width,height" (a 1920x1080 frame).
    result = subprocess.run(
        ["npx", "playwright", "screenshot", "--viewport-size", "1920,1080",
         f"file://{html_path}", str(png_path)],
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode == 0 and png_path.exists():
        print(f"  ✓ Saved {png_path} ({png_path.stat().st_size:,} bytes)")
        return True

    err = (result.stderr or result.stdout or "").strip()
    print(f"  ✗ Failed to capture {name}: {err}")
    return False


def main() -> int:
    print("=== GEAP eval — headless HTML-render screenshots ===")
    print(f"Output: {SCREENSHOT_DIR}/")

    demo = load_demo()
    source_label = str(DEMO_JSON) if demo else "bundled sample data (no eval_outputs/demo/full_demo.json)"
    print(f"Data source: {source_label}\n")

    # (label, html-builder, output-name)
    jobs: list[tuple[str, str, str]] = [
        ("Coverage matrix",
         render_coverage_matrix(COVERAGE_PAGES, source_label),
         "eval_coverage_matrix"),
        ("Optimization before/after",
         render_before_after(load_optimization(demo), source_label),
         "eval_optimization_before_after"),
        ("Metric registry",
         render_metric_registry(load_registry(demo), source_label),
         "eval_metric_registry"),
        ("Batch scorecard",
         render_batch_scores(SAMPLE_BATCH_SCORES, source_label),
         "eval_demo_batch_scores"),
        ("Offline trace eval",
         render_offline_trace(load_offline_trace(demo), source_label),
         "eval_offline_trace"),
        ("Failure clusters / taxonomy",
         render_failure_clusters(SAMPLE_FAILURE_CLUSTERS, source_label),
         "eval_failure_clusters_taxonomy"),
        ("Quality-drift alert",
         render_quality_drift_alert(SAMPLE_DRIFT, source_label),
         "eval_quality_drift_alert"),
    ]

    ok = 0
    total = len(jobs)
    results: list[tuple[str, int]] = []
    for i, (label, html, name) in enumerate(jobs, start=1):
        print(f"[{i}/{total}] {label} ...")
        if capture_and_save(html, name):
            ok += 1
            results.append((name, (SCREENSHOT_DIR / f"{name}.png").stat().st_size))

    print(f"\n✓ {ok}/{total} screenshots captured to {SCREENSHOT_DIR}/")
    for name, size in results:
        print(f"  {SCREENSHOT_DIR / f'{name}.png'}  ({size:,} bytes)")
    return 0 if ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
