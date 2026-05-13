"""Simulated evaluation — generate synthetic scenarios and run agent inference for CI/CD.

Supports per-agent evaluation with conversation scenarios,
ADK user simulator with configurable max turns, and multi-turn metrics.

Usage:
    uv run python -m src.eval.simulated_eval <agent-resource-name>
    uv run python -m src.eval.simulated_eval <agent-resource-name> 3.0 --agent-name travel_agent
"""


def _patch_evals_extra_fields():
    """Patch two SDK bugs in google-cloud-aiplatform==1.152.0 that break the
    simulated eval pipeline (generate_conversation_scenarios → run_inference → evaluate).

    Tracked upstream: https://github.com/googleapis/python-aiplatform/issues/6785
    Remove this function once the SDK is updated to fix both issues.

    Bug 1 — ConversationTurn rejects extra fields from run_inference response:
        The Vertex AI API returns turn data with fields (model_version, content,
        id, timestamp, author, actions, invocation_id, etc.) that aren't defined
        in the SDK's ConversationTurn pydantic model. Since the base class
        (google.genai._common.BaseModel) sets extra='forbid', pydantic raises
        ValidationError. Fix: set extra='ignore' so unknown fields are accepted
        during parsing but excluded from model_dump(), preventing them from being
        sent back to the evaluate API which also doesn't accept them.

    Bug 2 — turn_index missing from agent engine response:
        _process_multi_turn_agent_response (in _evals_common.py:1880) constructs
        AgentData from raw turn dicts returned by the agent engine. These dicts
        don't include turn_index. When the data is later sent to the evaluate API,
        it fails with "Required field is not set" for turn_index on every turn.
        Fix: inject turn_index based on list position before the SDK processes
        the response.
    """
    from vertexai._genai.types import evals as evals_types

    # Bug 1 fix: allow unknown fields through pydantic validation.
    # __pydantic_complete__ = False forces model_rebuild to regenerate the
    # cached validator, which otherwise ignores config changes.
    ct = evals_types.ConversationTurn
    ct.model_config["extra"] = "ignore"
    ct.__pydantic_complete__ = False
    ct.model_rebuild(force=True)
    evals_types.AgentData.__pydantic_complete__ = False
    evals_types.AgentData.model_rebuild(force=True)

    # Bug 2 fix: inject turn_index into each turn dict before AgentData
    # construction. The evaluate API requires this field but the agent engine
    # response omits it.
    from vertexai._genai import _evals_common

    _orig_process = _evals_common._process_multi_turn_agent_response

    def _patched_process(resp_item, agent_data_agents):
        if isinstance(resp_item, list):
            for i, turn in enumerate(resp_item):
                if isinstance(turn, dict) and "turn_index" not in turn:
                    turn["turn_index"] = i
        return _orig_process(resp_item, agent_data_agents)

    _evals_common._process_multi_turn_agent_response = _patched_process


GENERATION_INSTRUCTIONS = {
    "coordinator_agent": (
        "Generate diverse scenarios covering: flight search, hotel booking, "
        "expense submission within policy, over-limit expenses, booking cancellation, "
        "and multi-step travel planning with expense management."
    ),
    "travel_agent": (
        "Generate diverse scenarios covering: flight search by route and date, "
        "hotel search with price filters, booking confirmation flows, "
        "comparison shopping between options, and edge cases with invalid airports."
    ),
    "expense_agent": (
        "Generate diverse scenarios covering: expense policy checks for all categories, "
        "within-limit and over-limit submissions, expense history review, "
        "invalid category handling, and multi-expense submission flows."
    ),
    "router_agent": (
        "Generate scenarios with varying complexity levels: "
        "simple single-intent lookups (low complexity), moderate reasoning and "
        "multi-step queries (medium complexity), and complex cross-domain "
        "planning tasks requiring deep analysis (high complexity)."
    ),
}


def run_simulated_eval(
    agent_resource_name: str,
    agent_name: str = "coordinator_agent",
    scenario_count: int = 10,
    max_turns: int = 5,
    score_threshold: float = 3.0,
) -> bool:
    """Run simulated evaluation. Returns True if all metrics pass threshold."""
    _patch_evals_extra_fields()

    import vertexai
    from vertexai import Client, types
    from src.config import GCP_PROJECT_ID, GCP_REGION
    from src.eval.agent_eval_configs import build_agent_info

    vertexai.init(project=GCP_PROJECT_ID, location=GCP_REGION)
    client = Client(project=GCP_PROJECT_ID, location=GCP_REGION)

    eval_metrics = [
        types.RubricMetric.FINAL_RESPONSE_QUALITY,
        types.RubricMetric.SAFETY,
        types.RubricMetric.TOOL_USE_QUALITY,
    ]

    agent_info = build_agent_info(agent_name)

    generation_instruction = GENERATION_INSTRUCTIONS.get(
        agent_name, GENERATION_INSTRUCTIONS["coordinator_agent"]
    )

    print(f"[1/3] Generating {scenario_count} conversation scenarios for {agent_name}...")
    eval_dataset = client.evals.generate_conversation_scenarios(
        agent_info=agent_info,
        config={
            "count": scenario_count,
            "generation_instruction": generation_instruction,
        },
        allow_cross_region_model=True,
    )
    print("  Generated scenarios")

    print(f"[2/3] Running inference (max {max_turns} turns per scenario)...")
    eval_dataset_with_traces = client.evals.run_inference(
        agent=agent_resource_name,
        src=eval_dataset,
        config={
            "user_simulator_config": {
                "max_turn": max_turns,
                "model_name": "gemini-2.5-flash",
            },
        },
    )
    print("  Inference complete")

    print("[3/3] Evaluating with metrics...")
    eval_result = client.evals.evaluate(
        dataset=eval_dataset_with_traces,
        metrics=eval_metrics,
    )

    print(f"\n=== Simulated Evaluation Results ({agent_name}) ===")
    all_pass = True
    sm = getattr(eval_result, "summary_metrics", None)
    if sm and isinstance(sm, dict):
        for metric_name, scores in sm.items():
            avg_score = scores.get("mean", 0) if isinstance(scores, dict) else float(scores)
            status = "PASS" if avg_score >= score_threshold else "FAIL"
            if status == "FAIL":
                all_pass = False
            print(f"  {metric_name}: {avg_score:.2f} (threshold: {score_threshold}) [{status}]")
    elif sm and isinstance(sm, list):
        for item in sm:
            if isinstance(item, dict):
                metric_name = item.get("metric", item.get("name", "unknown"))
                avg_score = float(item.get("score", item.get("mean", 0)))
                status = "PASS" if avg_score >= score_threshold else "FAIL"
                if status == "FAIL":
                    all_pass = False
                print(f"  {metric_name}: {avg_score:.2f} (threshold: {score_threshold}) [{status}]")
            else:
                print(f"  {item}")
    else:
        print("  (no summary metrics returned — check console for results)")

    return all_pass


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m src.eval.simulated_eval <agent-resource-name> [threshold] [--agent-name NAME]")
        sys.exit(1)

    resource = sys.argv[1]
    threshold = 3.0
    agent_name = "coordinator_agent"

    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--agent-name" and i + 1 < len(args):
            agent_name = args[i + 1]
            i += 2
        else:
            try:
                threshold = float(args[i])
            except ValueError:
                pass
            i += 1

    passed = run_simulated_eval(resource, agent_name=agent_name, score_threshold=threshold)
    sys.exit(0 if passed else 1)
