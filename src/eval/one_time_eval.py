"""One-time evaluation with custom pointwise metric rubrics."""

import vertexai
from vertexai import Client, types
from google.genai import types as g_types

from src.config import GCP_PROJECT_ID, GCP_REGION

# Rapid eval uses the SDK's PREBUILT rubric metrics (LLM-as-judge). We deliberately avoid hand-built
# ``LLMMetric`` + ``MetricPromptBuilder`` metrics here: on google-cloud-aiplatform 1.162 their autorater
# returns a markdown "## Evaluation / Rating Score" assessment that the eval API cannot parse as JSON
# (400 INVALID_ARGUMENT), so every case errors. The predefined ``RubricMetric`` autoraters return
# structured scores reliably. Custom LLM-as-judge and code metrics are still demonstrated in
# ``src/eval/metric_registry.py`` (the "manage-metrics" step) and ``src/eval/batch_eval.py``.
METRICS = [
    types.RubricMetric.FINAL_RESPONSE_QUALITY,
    types.RubricMetric.INSTRUCTION_FOLLOWING,
    types.RubricMetric.GENERAL_QUALITY,
]


PROMPTS = [
    "Find flights from SFO to JFK on June 15",
    "Search hotels in New York under $300",
    "Submit a $500 entertainment expense for user EMP001",
    "Check if a $50 meal expense is within policy",
    "Book flight FL001 for Jane Doe",
]


def _agent_response_text(agent_engine, prompt: str, user_id: str = "one-time-eval") -> str:
    """Query a deployed Agent Engine and return its final response text.

    We run inference explicitly here instead of via ``client.evals.run_inference``: on
    google-cloud-aiplatform 1.162 that helper parses the Agent Engine's streamed events into the
    ``AgentData``/``ConversationTurn``/``AgentEvent`` models, which are ``extra="forbid"`` and reject
    the extra fields Agent Engine returns (``model_version``, ``usage_metadata``, ``actions`` …),
    raising "Failed to parse agent run response … to agent data: 'text'"; the resulting garbage
    response then breaks the autorater (400, non-JSON). Reading the response ourselves avoids that
    (SDK issue #6785) with no monkeypatching — ``EvalCase.responses`` carries the clean text.
    """
    texts = []
    for event in agent_engine.stream_query(message=prompt, user_id=user_id):
        if isinstance(event, dict):
            content = event.get("content") or {}
            for part in (content.get("parts") or []):
                if isinstance(part, dict) and part.get("text"):
                    texts.append(part["text"])
    return "\n".join(t for t in texts if t).strip()


def run_one_time_eval(agent_resource_name: str):
    """Run one-time evaluation against a deployed agent."""
    from vertexai import agent_engines

    vertexai.init(project=GCP_PROJECT_ID, location=GCP_REGION)
    client = Client(
        project=GCP_PROJECT_ID,
        location=GCP_REGION,
    )

    print(f"Running one-time eval on {agent_resource_name}...")
    print(f"  Dataset: {len(PROMPTS)} prompts")
    print("  Metrics: final_response_quality, instruction_following, general_quality")

    print("  Running inference (querying the deployed agent)...")
    agent_engine = agent_engines.get(agent_resource_name)
    eval_cases = []
    for prompt in PROMPTS:
        try:
            answer = _agent_response_text(agent_engine, prompt) or "(agent returned no text)"
        except Exception as e:  # noqa: BLE001 — record the failure as the response so eval still runs
            answer = f"(inference error: {e})"
        eval_cases.append(
            types.EvalCase(
                prompt=g_types.Content(parts=[g_types.Part.from_text(text=prompt)], role="user"),
                responses=[types.ResponseCandidate(
                    response=g_types.Content(parts=[g_types.Part.from_text(text=answer)], role="model"))],
            )
        )
    eval_dataset = types.EvaluationDataset(eval_cases=eval_cases)

    print("  Running evaluation...")
    eval_result = client.evals.evaluate(
        dataset=eval_dataset,
        metrics=METRICS,
    )

    print("\n=== Evaluation Results ===")
    for result in (eval_result.summary_metrics or []):
        mean_score_str = f"{result.mean_score:.2f}" if result.mean_score is not None else "N/A"
        print(f"  {result.metric_name}: mean={mean_score_str} (total={result.num_cases_total}, errors={result.num_cases_error})")

    return eval_result


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m src.eval.one_time_eval <agent-resource-name>")
        sys.exit(1)
    run_one_time_eval(sys.argv[1])
