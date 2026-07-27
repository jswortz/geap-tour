"""Demo steps — one function per GEAP "Optimize > Evaluation" doc feature.

Each function is tagged in its docstring with the doc page it demonstrates and
returns a JSON-serializable summary dict. Every step is wrapped so that a missing
credential, engine, or SDK feature degrades to ``{"status": "skipped", ...}``
instead of aborting the whole flywheel — the demo is meant to run end-to-end.

The raw SDK result objects (which carry ``.show()`` for notebook visualization)
are returned via the ``raw`` key when available; the orchestrator strips them
before writing JSON.

Doc set: https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/agent-evaluation
"""

from __future__ import annotations

DOC_BASE = "https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation"


def make_client():
    """Build a Vertex AI (Agent Platform) SDK client, or None if unavailable."""
    try:
        import vertexai  # noqa: F401
        from vertexai import Client
        from src.config import GCP_PROJECT_ID, GCP_REGION, GCP_STAGING_BUCKET

        vertexai.init(
            project=GCP_PROJECT_ID,
            location=GCP_REGION,
            staging_bucket=f"gs://{GCP_STAGING_BUCKET}",
        )
        return Client(project=GCP_PROJECT_ID, location=GCP_REGION)
    except Exception as e:  # noqa: BLE001
        print(f"  (could not init SDK client: {e})")
        return None


def resolve_resource(agent_id: str) -> str:
    from src.config import GCP_PROJECT_ID, GCP_REGION

    if agent_id.startswith("projects/"):
        return agent_id
    return f"projects/{GCP_PROJECT_ID}/locations/{GCP_REGION}/reasoningEngines/{agent_id}"


def _ok(step, title, doc_slug, **extra):
    return {"step": step, "title": title, "doc": f"{DOC_BASE}/{doc_slug}", "status": "ok", **extra}


def _skipped(step, title, doc_slug, reason, **extra):
    return {"step": step, "title": title, "doc": f"{DOC_BASE}/{doc_slug}", "status": "skipped", "reason": reason, **extra}


# ---------------------------------------------------------------------------
# Phase 1 — Design & scoring setup
# ---------------------------------------------------------------------------
def register_metrics(client, do_register: bool = False) -> dict:
    """[manage-metrics] Build & optionally register the Metric Registry entries.

    Demonstrates all three metric types: predefined rubric, custom LLM-as-judge,
    and custom code (CodeExecutionMetric), plus a reference-based Exact Match.
    """
    try:
        from src.eval import metric_registry as mr

        catalog = {
            "single_turn_rubric": [getattr(m, "value", getattr(m, "name", str(m))) for m in mr.SINGLE_TURN_RUBRIC_METRICS],
            "multi_turn_rubric": [getattr(m, "value", getattr(m, "name", str(m))) for m in mr.MULTI_TURN_RUBRIC_METRICS],
            "custom": [getattr(m, "name", type(m).__name__) for m in mr.custom_metrics()],
            "exact_match_reference_based": mr.EXACT_MATCH_METRIC is not None,
            "code_metric": mr.CODE_POLICY_LIMIT_METRIC is not None,
        }
        registered = {}
        if do_register and client is not None:
            registered = mr.register_all(client)
        return _ok(1, "Metric Registry (predefined + custom LLM + custom code + exact-match)",
                   "manage-metrics", catalog=catalog, registered=registered)
    except Exception as e:  # noqa: BLE001
        return _skipped(1, "Metric Registry", "manage-metrics", str(e))


# ---------------------------------------------------------------------------
# Phase 2 — Execution
# ---------------------------------------------------------------------------
def rapid_eval(client, agent_resource: str) -> dict:
    """[evaluate-agents] Rapid eval — quick pointwise LLM-judge run on a few prompts."""
    try:
        from src.eval.one_time_eval import run_one_time_eval

        result = run_one_time_eval(agent_resource)
        summary = []
        for r in (getattr(result, "summary_metrics", None) or []):
            summary.append({"metric": getattr(r, "metric_name", "?"),
                            "mean": getattr(r, "mean_score", None)})
        return _ok(2, "Rapid evaluation (client.evals.evaluate)", "evaluate-agents",
                   metrics=summary, raw=result)
    except Exception as e:  # noqa: BLE001
        return _skipped(2, "Rapid evaluation", "evaluate-agents", str(e))


def testcase_eval(agent_id: str, agent_name: str = "coordinator_agent",
                  score_threshold: float = 3.0) -> dict:
    """[evaluate-agents] Test-Case (batch) eval — regression suite against a deployed agent."""
    try:
        from src.eval.multi_agent_batch_eval import run_multi_agent_batch_eval

        results = run_multi_agent_batch_eval(
            agents=[agent_name], agent_id=agent_id, score_threshold=score_threshold,
        )
        agent = results.get("agents", {}).get(agent_name, {})
        return _ok(3, "Test-Case / regression evaluation", "evaluate-agents",
                   agent=agent_name, status_detail=agent.get("status"),
                   metrics=agent.get("metrics", {}))
    except Exception as e:  # noqa: BLE001
        return _skipped(3, "Test-Case / regression evaluation", "evaluate-agents", str(e))


def simulate(agent_resource: str, agent_name: str = "coordinator_agent",
             scenario_count: int = 3, max_turns: int = 4) -> dict:
    """[evaluate-simulated] User simulation — scenario gen + multi-turn autoraters."""
    try:
        from src.eval.simulated_eval import run_simulated_eval

        passed = run_simulated_eval(
            agent_resource, agent_name=agent_name,
            scenario_count=scenario_count, max_turns=max_turns, multi_turn=True,
        )
        return _ok(4, "Simulated multi-turn evaluation", "evaluate-simulated",
                   agent=agent_name, passed=bool(passed))
    except Exception as e:  # noqa: BLE001
        return _skipped(4, "Simulated multi-turn evaluation", "evaluate-simulated", str(e))


def environment_simulation() -> dict:
    """[evaluate-simulated] Environment simulation — tool-call mocking + error injection."""
    try:
        from src.eval.env_simulation import run_with_env_simulation

        summary = run_with_env_simulation(inject_errors=True)
        return _ok(5, "Environment simulation (mock tools + injected 503s)",
                   "evaluate-simulated", summary=summary)
    except Exception as e:  # noqa: BLE001
        return _skipped(5, "Environment simulation", "evaluate-simulated", str(e))


def offline_eval(client, agent_name: str = "coordinator_agent") -> dict:
    """[evaluate-offline] Offline eval — score historical traces/sessions (no re-inference)."""
    try:
        from src.eval.offline_trace_eval import evaluate_from_traces

        summary = evaluate_from_traces(client=client, agent_name=agent_name)
        return _ok(6, "Offline evaluation over historical traces/sessions",
                   "evaluate-offline", result=summary)
    except Exception as e:  # noqa: BLE001
        return _skipped(6, "Offline evaluation", "evaluate-offline", str(e))


# ---------------------------------------------------------------------------
# Phase 3 — Scoring in production
# ---------------------------------------------------------------------------
def online_monitors(do_setup: bool = False) -> dict:
    """[evaluate-online] Continuous eval — Online Monitors on live production traces."""
    try:
        note = ("Online Monitors asynchronously score live traces on a ~10-min loop "
                "(Query -> Evaluate -> Report), exporting to Cloud Logging + Cloud Monitoring. "
                "Create/verify with: python -m src.eval.setup_online_evaluators create|verify")
        detail = {"note": note}
        if do_setup:
            try:
                from src.eval import setup_online_evaluators as soe
                if hasattr(soe, "list_evaluators"):
                    detail["evaluators"] = str(soe.list_evaluators())
            except Exception as e:  # noqa: BLE001
                detail["setup_error"] = str(e)
        return _ok(7, "Continuous evaluation with Online Monitors", "evaluate-online", **detail)
    except Exception as e:  # noqa: BLE001
        return _skipped(7, "Online Monitors", "evaluate-online", str(e))


# ---------------------------------------------------------------------------
# Phase 4 — Refinement
# ---------------------------------------------------------------------------
def analyze(agent_id: str) -> dict:
    """[view-results] Analyze — failure clusters mapped to loss-pattern taxonomies."""
    try:
        from src.eval.failure_clusters import analyze_failure_clusters
        eval_result = analyze_failure_clusters(agent_id)
        return _ok(8, "Analyze results & failure clusters (taxonomy + 3-level triage)",
                   "view-results", raw=eval_result)
    except Exception as e:  # noqa: BLE001
        return _skipped(8, "Analyze results & failure clusters", "view-results", str(e))


def optimize(client, agent_module_path: str = "src/agents/coordinator") -> dict:
    """[optimize-agent] Optimize — SDK optimizer path with ADK-GEPA fallback (Quality Flywheel)."""
    try:
        from src.eval.sdk_optimize import sdk_optimize
        result = sdk_optimize(client=client, agent_module_path=agent_module_path)
        return _ok(9, "Optimize agent prompts (Quality Flywheel)", "optimize-agent", result=result)
    except Exception as e:  # noqa: BLE001
        return _skipped(9, "Optimize agent prompts", "optimize-agent", str(e))


def quality_alerts() -> dict:
    """[quality-alerts] Quality-drift alert policy (gcloud policy.yaml path)."""
    try:
        from src.eval.quality_alerts import export_policy_yaml
        path = export_policy_yaml("src/eval/policies/quality_drift_policy.yaml")
        return _ok(10, "Quality-drift alerts (Cloud Monitoring policy)", "quality-alerts",
                   policy_file=str(path))
    except Exception as e:  # noqa: BLE001
        return _skipped(10, "Quality-drift alerts", "quality-alerts", str(e))
