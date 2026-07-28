"""Agent Platform SDK optimizer path — with a defensive ADK GEPA fallback.

The Quality Flywheel (Evaluate -> Analyze -> Optimize)
------------------------------------------------------
GEAP's continuous-improvement loop has three phases:

  1. Evaluate  — run the agent over an eval dataset and score the traces with
                 rubric / LLM-as-judge / code metrics (see src/eval/batch_eval.py,
                 src/eval/metric_registry.py).
  2. Analyze   — review the scored results and summary metrics to find where the
                 agent underperforms.
  3. Optimize  — feed the eval result + dataset back into a prompt optimizer so
                 the agent's instructions are auto-tuned against the metrics.
                 The improved agent is re-evaluated, closing the loop.

This module implements phase 3.

The documented Agent Platform SDK path
--------------------------------------
Google's "Evaluate agents" doc shows the intended one-call SDK optimizer:

    result = client.optimizer.optimize(
        targets=["system_prompt"],
        benchmark=eval_result,   # the phase-1 evaluation result
        tests=eval_dataset,      # the eval cases to optimize against
    )

  - https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/optimize-agent
  - https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/evaluate-agents

SDK reality (verified)
----------------------
`client.optimizer` does NOT exist in the currently pinned `aiplatform` /
`vertexai` SDK. So this module FEATURE-DETECTS the documented path and, when it
is absent (or raises), FALLS BACK to the repo's real optimization path: the ADK
GEPA optimizer in ``src/optimize/run_optimize.py`` (``GEPARootAgentPromptOptimizer``).

`sdk_optimize()` never raises — it always returns a dict describing which path
ran. The GEPA fallback is a 10-20 minute live job, so it is gated behind the
``GEAP_RUN_GEPA`` env var: without it (e.g. during import / validation / offline
use) the function returns ``status="skipped"`` instead of blocking.

Usage:
    python -m src.eval.sdk_optimize [agent_module_path]
    GEAP_RUN_GEPA=1 python -m src.eval.sdk_optimize src/agents/coordinator
"""

import os
import sys

OPTIMIZE_DOC_URL = (
    "https://docs.cloud.google.com/gemini-enterprise-agent-platform/"
    "optimize/evaluation/optimize-agent"
)
EVALUATE_DOC_URL = (
    "https://docs.cloud.google.com/gemini-enterprise-agent-platform/"
    "optimize/evaluation/evaluate-agents"
)


def _summarize(result) -> object:
    """Best-effort JSON-friendly summary of an unknown SDK optimizer result."""
    for attr in ("to_dict", "model_dump"):
        fn = getattr(result, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:  # noqa: BLE001
                pass
    return repr(result)


def sdk_optimize(
    client=None,
    eval_result=None,
    eval_dataset=None,
    agent_module_path: str = "src/agents/coordinator",
    targets=None,
    run: bool = False,
    max_metric_calls: int | None = None,
) -> dict:
    """Optimize an agent's prompt(s), preferring the documented SDK optimizer.

    Feature-detects ``client.optimizer.optimize(...)`` and uses it when present;
    otherwise falls back to the ADK GEPA optimizer in
    ``src/optimize/run_optimize.py``. Never raises — always returns a dict with a
    ``method`` key describing which path ran.

    Args:
        client: A Vertex AI ``Client`` (or any object). Feature-detected for an
            ``optimizer.optimize`` attribute.
        eval_result: Phase-1 evaluation result (the ``benchmark``).
        eval_dataset: The eval cases to optimize against (the ``tests``).
        agent_module_path: Agent module dir used by the ADK GEPA fallback.
        targets: What to optimize; defaults to ``["system_prompt"]``.

    Returns:
        dict describing the outcome, e.g.::

            {"method": "sdk.optimizer", "result": {...}}
            {"method": "adk_gepa_fallback", "status": "skipped", "reason": "..."}
            {"method": "adk_gepa_fallback", "status": "completed", ...}
            {"method": "adk_gepa_fallback", "status": "error", "error": "..."}
    """
    targets = targets or ["system_prompt"]

    # --- Path 1: documented Agent Platform SDK optimizer (feature-detected) ---
    optimizer = getattr(client, "optimizer", None)
    if optimizer is not None and callable(getattr(optimizer, "optimize", None)):
        try:
            result = client.optimizer.optimize(
                targets=targets,
                benchmark=eval_result,
                tests=eval_dataset,
            )
            return {"method": "sdk.optimizer", "result": _summarize(result)}
        except Exception as e:  # noqa: BLE001
            print(
                "[sdk_optimize] client.optimizer.optimize(...) raised "
                f"({e!r}); falling back to the ADK GEPA optimizer."
            )
    else:
        print(
            "[sdk_optimize] client.optimizer is unavailable in this aiplatform "
            "SDK version (the documented client.optimizer.optimize(...) path does "
            "not exist here). Falling back to the ADK GEPA optimizer "
            "(src/optimize/run_optimize.py). See: " + OPTIMIZE_DOC_URL
        )

    # --- Path 2: ADK GEPA fallback (src/optimize/run_optimize.py) -------------
    # GEPA is a live 10-20 min optimization against a real GCP project, so it is
    # opt-in via GEAP_RUN_GEPA to avoid blocking during import / validation.
    run_gepa = run or os.environ.get("GEAP_RUN_GEPA", "").strip().lower() in {"1", "true", "yes", "on"}
    if not run_gepa:
        return {
            "method": "adk_gepa_fallback",
            "status": "skipped",
            "reason": (
                "GEPA is a live optimization against the deployed agent (requires reachable MCP "
                "servers). Pass run=True (the demo does) or set GEAP_RUN_GEPA=1 to execute it. "
                f"Would call: run_optimize(agent_module_path={agent_module_path!r})."
            ),
            "agent_module_path": agent_module_path,
        }

    try:
        from src.optimize.run_optimize import run_optimize

        result = run_optimize(agent_module_path, max_metric_calls=max_metric_calls)
        best_instruction = None
        try:
            if hasattr(result, "gepa_result"):
                best = result.optimized_agents[result.gepa_result["best_idx"]]
                best_instruction = getattr(best.optimized_agent, "instruction", None)
        except Exception:  # noqa: BLE001
            pass
        return {
            "method": "adk_gepa_fallback",
            "status": "completed",
            "agent_module_path": agent_module_path,
            "max_metric_calls": max_metric_calls,
            "optimized_instruction": best_instruction,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "method": "adk_gepa_fallback",
            "status": "error",
            "error": f"{type(e).__name__}: {e}",
            "agent_module_path": agent_module_path,
        }


def _build_client():
    """Construct a Vertex AI Client; return None if it cannot be built."""
    try:
        import vertexai  # noqa: F401
        from vertexai import Client

        from src.config import GCP_PROJECT_ID, GCP_REGION

        return Client(project=GCP_PROJECT_ID, location=GCP_REGION)
    except Exception as e:  # noqa: BLE001
        print(f"[sdk_optimize] could not build a Vertex Client ({e!r}); using client=None")
        return None


if __name__ == "__main__":
    agent_module_path = sys.argv[1] if len(sys.argv) > 1 else "src/agents/coordinator"
    client = _build_client()
    outcome = sdk_optimize(client=client, agent_module_path=agent_module_path)
    print(outcome)
