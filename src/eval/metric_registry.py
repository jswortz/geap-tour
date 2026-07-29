"""Evaluation Metric Registry — define, register, and reuse custom metrics via the SDK.

Covers the "Manage evaluation metrics" doc page:
https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/manage-metrics

The Metric Registry lets you define a metric once and reuse it across offline
batch runs and online monitors, instead of reconfiguring it per run. This module
demonstrates all THREE metric types the docs describe, plus the SDK registration
call `client.evals.create_evaluation_metric()`:

  1. Predefined (Google-managed) rubric metrics  → `types.RubricMetric.*`
       - Single-turn:  FINAL_RESPONSE_QUALITY, HALLUCINATION, TOOL_USE_QUALITY, SAFETY
       - Multi-turn:   MULTI_TURN_TASK_SUCCESS, MULTI_TURN_TOOL_USE_QUALITY,
                       MULTI_TURN_TRAJECTORY_QUALITY
       (adaptive rubric = criteria auto-generated per case;
        static rubric   = fixed criteria — see docstrings on each accessor)
  2. Custom LLM metrics (LLM-as-judge, natural-language rubric) → `types.LLMMetric`
       Reuses POLICY_COMPLIANCE_METRIC / TOOL_USE_METRIC from batch_eval.py.
  3. Custom code metrics (deterministic Python) → `types.CodeExecutionMetric`
       `custom_function` is a SERVER-EXECUTED code STRING that must define
       `def evaluate(instance: dict) -> float:`. Keep it pure-stdlib.

We ALSO show the reference-based vs reference-free distinction: EXACT_MATCH_METRIC
is reference-based (needs a `reference` answer), while the rubric metrics above are
reference-free (they judge the trace on its own).

NOTE on parallel registration paths: `src/eval/setup_online_evaluators.py` registers
custom rubric metrics via the v1beta1 `evaluationMetrics` REST endpoint (for online
monitors). This module uses the higher-level SDK call `create_evaluation_metric()` —
both write to the same Metric Registry.

Usage:
    uv run python -m src.eval.metric_registry register   # register all custom metrics
    uv run python -m src.eval.metric_registry list        # list registered metrics
    uv run python -m src.eval.metric_registry delete       # delete GEAP custom metrics
"""

import sys

from vertexai import types

# Reuse the existing LLM-as-judge metrics rather than redefining them.
from src.eval.batch_eval import POLICY_COMPLIANCE_METRIC, TOOL_USE_METRIC


# ---------------------------------------------------------------------------
# Predefined rubric metrics (Google-managed) — grouped for reuse by other modules
# ---------------------------------------------------------------------------
SINGLE_TURN_RUBRIC_METRICS = [
    types.RubricMetric.FINAL_RESPONSE_QUALITY,  # adaptive rubric
    types.RubricMetric.HALLUCINATION,           # static rubric
    types.RubricMetric.TOOL_USE_QUALITY,        # adaptive rubric
    types.RubricMetric.SAFETY,                  # static rubric — 1 safe / 0 unsafe
]


def _multi_turn_rubric_metrics() -> list:
    """Resolve the multi-turn rubric metric accessors, skipping any absent in the SDK.

    Multi-turn autoraters analyze the full conversation history:
      - MULTI_TURN_TASK_SUCCESS   — were the conversation goal(s) achieved? (reference-free)
      - MULTI_TURN_TOOL_USE_QUALITY — right tools, right args, right time, across turns
      - MULTI_TURN_TRAJECTORY_QUALITY — was the reasoning path logical/efficient?
    """
    names = [
        "MULTI_TURN_TASK_SUCCESS",
        "MULTI_TURN_TOOL_USE_QUALITY",
        "MULTI_TURN_TRAJECTORY_QUALITY",
    ]
    metrics = []
    for name in names:
        metric = getattr(types.RubricMetric, name, None)
        if metric is not None:
            metrics.append(metric)
    return metrics


MULTI_TURN_RUBRIC_METRICS = _multi_turn_rubric_metrics()


# ---------------------------------------------------------------------------
# Reference-based (computation) metric — Exact Match
# ---------------------------------------------------------------------------
def _build_exact_match_metric():
    """Exact Match is a reference-based computation metric (needs a `reference`).

    Contrast with the rubric metrics above, which are reference-free. Guarded so a
    minor SDK naming difference degrades to None rather than breaking import.
    """
    for factory in (
        lambda: types.Metric(name="exact_match"),
        lambda: types.RubricMetric.EXACT_MATCH,  # type: ignore[attr-defined]
    ):
        try:
            return factory()
        except Exception:
            continue
    return None


EXACT_MATCH_METRIC = _build_exact_match_metric()


# ---------------------------------------------------------------------------
# Custom code metric — deterministic policy-limit check (types.CodeExecutionMetric)
# ---------------------------------------------------------------------------
# `custom_function` is executed server-side; it must define `evaluate(instance)`.
# Keep it dependency-free (stdlib only). It returns 1.0 when the agent's response
# states the correct corporate dollar limit for the category it discusses, else 0.0.
_CODE_POLICY_LIMIT_FN = '''
def evaluate(instance: dict) -> float:
    """Deterministic check: does the response cite the correct policy limit?"""
    import re

    limits = {
        "meal": 75, "meals": 75,
        "transport": 200,
        "lodging": 400,
        "supplies": 100,
        "entertainment": 150,
    }

    # Extract the response text across the shapes the eval service may pass.
    text = ""
    if isinstance(instance, dict):
        text = (
            instance.get("response")
            or instance.get("final_response")
            or instance.get("output")
            or ""
        )
        if not text:
            agent_data = instance.get("agent_eval_data") or {}
            turns = agent_data.get("turns") or []
            parts = []
            for turn in turns:
                if isinstance(turn, dict):
                    parts.append(str(turn.get("response") or turn.get("content") or ""))
            text = " ".join(parts)
    text = str(text).lower()
    if not text:
        return 0.0

    mentioned = [cat for cat in limits if cat in text]
    if not mentioned:
        return 0.5  # no category discussed — neither right nor wrong

    numbers = set(re.findall(r"\\$?\\s*(\\d{2,4})", text))
    for cat in mentioned:
        if str(limits[cat]) in numbers:
            return 1.0
    return 0.0
'''


def _build_code_metric():
    try:
        return types.CodeExecutionMetric(
            name="policy_limit_exact",
            custom_function=_CODE_POLICY_LIMIT_FN,
        )
    except Exception:
        return None


CODE_POLICY_LIMIT_METRIC = _build_code_metric()


# ---------------------------------------------------------------------------
# The set of CUSTOM metrics this project registers in the Metric Registry
# ---------------------------------------------------------------------------
def custom_metrics() -> list:
    """Return the custom metrics to register (skips any that failed to build)."""
    metrics = [POLICY_COMPLIANCE_METRIC, TOOL_USE_METRIC]
    if CODE_POLICY_LIMIT_METRIC is not None:
        metrics.append(CODE_POLICY_LIMIT_METRIC)
    if EXACT_MATCH_METRIC is not None:
        metrics.append(EXACT_MATCH_METRIC)
    return metrics


def _client():
    import vertexai  # noqa: F401
    from vertexai import Client
    from src.config import GCP_PROJECT_ID, GCP_REGION

    return Client(project=GCP_PROJECT_ID, location=GCP_REGION)


def _existing_by_display_name(client) -> dict:
    """Map ``display_name`` → registry resource name for metrics already published.

    ``create_evaluation_metric`` uses each metric's ``name`` as its ``display_name``,
    so this lets us make registration idempotent and resolve resource names for delete.
    """
    resp = client.evals.list_evaluation_metrics()
    return {m.display_name: m.name for m in (resp.evaluation_metrics or [])}


def register_all(client=None) -> dict:
    """Register every custom metric via `client.evals.create_evaluation_metric()`.

    Idempotent: a metric whose ``display_name`` is already in the registry is reused,
    not duplicated. Returns a mapping of metric name → registered resource path
    (or an error string).
    """
    client = client or _client()
    existing = _existing_by_display_name(client)
    registered = {}
    for metric in custom_metrics():
        name = getattr(metric, "name", metric.__class__.__name__)
        if name in existing:
            registered[name] = existing[name]
            print(f"  = {name} already registered → {existing[name]}")
            continue
        try:
            path = client.evals.create_evaluation_metric(metric=metric)
            registered[name] = str(path)
            print(f"  ✓ registered {name} → {path}")
        except Exception as e:  # noqa: BLE001
            registered[name] = f"ERROR: {e}"
            print(f"  ✗ {name}: {e}")
    return registered


def list_registered(client=None) -> list:
    """List metrics currently in the registry."""
    client = client or _client()
    try:
        metrics = list(client.evals.list_evaluation_metrics().evaluation_metrics or [])
    except Exception as e:  # noqa: BLE001
        print(f"  (could not list metrics: {e})")
        return []
    for m in metrics:
        print(f"  - {m.display_name} → {m.name}")
    return metrics


def delete_registered(client=None) -> None:
    """Delete the GEAP custom metrics from the registry (by resolved resource name)."""
    client = client or _client()
    existing = _existing_by_display_name(client)
    for metric in custom_metrics():
        name = getattr(metric, "name", None)
        resource = existing.get(name)
        if not resource:
            continue
        try:
            client.evals.delete_evaluation_metric(metric_resource_name=resource)
            print(f"  ✓ deleted {name}")
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {name}: {e}")


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "list"
    print(f"=== Metric Registry: {cmd} ===")
    if cmd == "register":
        register_all()
    elif cmd == "list":
        list_registered()
    elif cmd == "delete":
        delete_registered()
    else:
        print("Usage: python -m src.eval.metric_registry {register|list|delete}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
