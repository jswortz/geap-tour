"""Simulated evaluation — generate synthetic scenarios and run agent inference for CI/CD."""

import vertexai
from google import genai
from google.genai import types
from vertexai import agent_engines

from src.config import GCP_PROJECT_ID, GCP_REGION
from src.eval.one_time_eval import HELPFULNESS_METRIC, TOOL_USE_METRIC


def run_simulated_eval(
    agent_resource_name: str,
    scenario_count: int = 10,
    max_turns: int = 5,
    score_threshold: float = 3.0,
) -> bool:
    """Run simulated evaluation. Returns True if all metrics pass threshold."""
    vertexai.init(project=GCP_PROJECT_ID, location=GCP_REGION)
    client = genai.Client(
        vertexai=True,
        project=GCP_PROJECT_ID,
        location=GCP_REGION,
    )

    agent = agent_engines.get(agent_resource_name)

    # Step 1: Generate synthetic conversation scenarios
    print(f"[1/3] Generating {scenario_count} conversation scenarios...")
    eval_dataset = client.evals.generate_conversation_scenarios(
        agent_info=types.evals.AgentInfo.load_from_agent(agent=agent),
        config={
            "count": scenario_count,
            "generation_instruction": (
                "Generate diverse scenarios covering: flight search, hotel booking, "
                "expense submission within policy, over-limit expenses, booking cancellation, "
                "and multi-step travel planning."
            ),
        },
    )
    print(f"  ✓ Generated {len(eval_dataset)} scenarios")

    # Step 2: Run agent inference on generated scenarios
    print(f"[2/3] Running inference (max {max_turns} turns per scenario)...")
    eval_dataset_with_traces = client.evals.run_inference(
        agent=agent,
        src=eval_dataset,
        config={
            "user_simulator_config": {"max_turn": max_turns},
        },
    )
    print(f"  ✓ Inference complete")

    # Step 3: Evaluate with metrics
    print("[3/3] Evaluating with metrics...")
    eval_result = client.evals.evaluate(
        src=eval_dataset_with_traces,
        config={
            "metrics": [HELPFULNESS_METRIC, TOOL_USE_METRIC],
        },
    )

    # Report results
    print("\n=== Simulated Evaluation Results ===")
    all_pass = True
    for metric_name, scores in eval_result.summary_metrics.items():
        avg_score = scores.get("mean", 0)
        status = "PASS" if avg_score >= score_threshold else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"  {metric_name}: {avg_score:.2f} (threshold: {score_threshold}) [{status}]")

    return all_pass


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m src.eval.simulated_eval <agent-resource-name> [threshold]")
        sys.exit(1)
    resource = sys.argv[1]
    threshold = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
    passed = run_simulated_eval(resource, score_threshold=threshold)
    sys.exit(0 if passed else 1)
