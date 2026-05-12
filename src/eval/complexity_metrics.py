"""Complexity routing evaluation metrics — Vertex AI API + ADK custom metric + standalone scorers."""

import asyncio
import statistics
import time
from typing import Optional

from vertexai import types as vtx_types

from src.router.complexity import classify_complexity
from src.router.cost_tracker import estimate_cost


# ---------------------------------------------------------------------------
# Vertex AI Eval API metric (for batch_eval / online monitors)
# ---------------------------------------------------------------------------
COMPLEXITY_ROUTING_METRIC = vtx_types.LLMMetric(
    name="complexity_routing_accuracy",
    prompt_template=vtx_types.MetricPromptBuilder(
        instruction=(
            "Evaluate whether the agent correctly classified prompt complexity "
            "and routed to the appropriate model tier. "
            "Low complexity (simple single-intent lookups) should use a lightweight model. "
            "Medium complexity (moderate reasoning, 2 related intents) should use a mid-tier model. "
            "High complexity (multi-step planning, cross-domain analysis, 3+ intents) "
            "should use a frontier model."
        ),
        criteria={
            "Complexity assessment": "Does the routing decision match the actual complexity of the prompt?",
            "Model appropriateness": "Is the selected model tier cost-effective for this complexity level?",
            "User experience": "Does the user get an adequate response quality for their request?",
        },
        rating_scores={
            "5": "Perfect routing — complexity correctly identified and optimal model selected.",
            "4": "Good routing — correct general tier, minor suboptimality.",
            "3": "Acceptable — model works but a different tier would be more appropriate.",
            "2": "Poor routing — significantly over- or under-provisioned model for the task.",
            "1": "Wrong routing — simple query sent to expensive model or complex query to minimal model.",
        },
    ),
)


# ---------------------------------------------------------------------------
# ADK custom metric (for `adk eval` CLI)
# ---------------------------------------------------------------------------
try:
    from google.adk.evaluation.eval_case import Invocation
    from google.adk.evaluation.eval_metrics import EvalMetric, EvalStatus
    from google.adk.evaluation.evaluator import EvaluationResult, PerInvocationResult

    async def check_complexity_routing(
        eval_metric: EvalMetric,
        actual_invocations: list[Invocation],
        expected_invocations: Optional[list[Invocation]],
        conversation_scenario=None,
    ) -> EvaluationResult:
        """ADK custom metric: score whether router picked the right model tier."""
        per_invocation_results = []

        for actual in actual_invocations:
            prompt_text = "".join(
                part.text for part in (actual.user_content.parts or []) if part.text
            )
            if not prompt_text:
                per_invocation_results.append(PerInvocationResult(
                    actual_invocation=actual,
                    score=0.0,
                    eval_status=EvalStatus.NOT_EVALUATED,
                ))
                continue

            result = await classify_complexity(prompt_text)
            response_text = "".join(
                part.text for part in (actual.final_response.parts or []) if part.text
            ).lower()

            routed_correctly = False
            if result.level == "low" and "lite" in response_text:
                routed_correctly = True
            elif result.level == "medium" and "flash" in response_text:
                routed_correctly = True
            elif result.level == "high" and ("opus" in response_text or "deep" in response_text):
                routed_correctly = True
            elif result.level in response_text:
                routed_correctly = True

            score = 1.0 if routed_correctly else 0.0
            per_invocation_results.append(PerInvocationResult(
                actual_invocation=actual,
                score=score,
                eval_status=EvalStatus.PASSED if routed_correctly else EvalStatus.FAILED,
            ))

        scores = [r.score for r in per_invocation_results if r.eval_status != EvalStatus.NOT_EVALUATED]
        avg = statistics.mean(scores) if scores else 0.0
        threshold = eval_metric.criterion.threshold if eval_metric.criterion else 0.8
        return EvaluationResult(
            overall_score=avg,
            overall_eval_status=EvalStatus.PASSED if avg >= threshold else EvalStatus.FAILED,
            per_invocation_results=per_invocation_results,
        )
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Standalone complexity accuracy scorer
# ---------------------------------------------------------------------------
async def run_complexity_accuracy_eval(cases: list[dict]) -> dict:
    """Classify each prompt and compare against expected complexity level.

    Returns accuracy, confusion matrix, per-case details, and timing stats.
    """
    results = []
    confusion = {"low": {"low": 0, "medium": 0, "high": 0},
                 "medium": {"low": 0, "medium": 0, "high": 0},
                 "high": {"low": 0, "medium": 0, "high": 0}}
    latencies = []

    for case in cases:
        expected = case.get("expected_complexity")
        if not expected:
            continue

        t0 = time.monotonic()
        result = await classify_complexity(case["prompt"])
        latency_ms = (time.monotonic() - t0) * 1000
        latencies.append(latency_ms)

        match = result.level == expected
        confusion[expected][result.level] += 1
        results.append({
            "prompt": case["prompt"][:80],
            "expected": expected,
            "actual": result.level,
            "score": result.score,
            "reason": result.reason,
            "match": match,
            "latency_ms": round(latency_ms, 1),
        })

    total = len(results)
    correct = sum(1 for r in results if r["match"])
    accuracy = correct / total if total else 0

    return {
        "total_cases": total,
        "correct": correct,
        "accuracy": round(accuracy, 4),
        "accuracy_pct": f"{accuracy * 100:.1f}%",
        "avg_latency_ms": round(statistics.mean(latencies), 1) if latencies else 0,
        "confusion_matrix": confusion,
        "per_case": results,
    }


# ---------------------------------------------------------------------------
# Cost efficiency scorer
# ---------------------------------------------------------------------------
MODEL_MAP = {
    "low": "gemini-2.0-flash-lite",
    "medium": "gemini-2.5-flash",
    "high": "vertex_ai/claude-opus-4-7",
}

AVG_INPUT_TOKENS = 200
AVG_OUTPUT_TOKENS = 500


async def run_cost_efficiency_eval(cases: list[dict]) -> dict:
    """Compare smart-router cost vs all-Opus baseline."""
    routed_cost = 0.0
    all_opus_cost = 0.0
    per_case = []

    for case in cases:
        result = await classify_complexity(case["prompt"])
        model = MODEL_MAP.get(result.level, "gemini-2.5-flash")
        case_cost = estimate_cost(model, AVG_INPUT_TOKENS, AVG_OUTPUT_TOKENS)
        classifier_cost = estimate_cost("classifier", len(case["prompt"].split()) * 2, 20)
        total_case_cost = case_cost + classifier_cost
        opus_cost = estimate_cost("vertex_ai/claude-opus-4-7", AVG_INPUT_TOKENS, AVG_OUTPUT_TOKENS)

        routed_cost += total_case_cost
        all_opus_cost += opus_cost

        per_case.append({
            "prompt": case["prompt"][:60],
            "complexity": result.level,
            "model": model,
            "cost_usd": round(total_case_cost, 8),
            "opus_cost_usd": round(opus_cost, 8),
        })

    savings_pct = (1 - routed_cost / all_opus_cost) * 100 if all_opus_cost else 0

    return {
        "total_prompts": len(cases),
        "routed_cost_usd": round(routed_cost, 8),
        "all_opus_cost_usd": round(all_opus_cost, 8),
        "savings_pct": round(savings_pct, 1),
        "per_case": per_case,
    }
