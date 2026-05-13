"""Simulated evaluation — generate synthetic scenarios and run agent inference for CI/CD.

Supports per-agent evaluation with conversation scenarios from JSON files,
ADK user simulator with configurable max turns, and multi-turn metrics.

Usage:
    uv run python -m src.eval.simulated_eval <agent-resource-name>
    uv run python -m src.eval.simulated_eval <agent-resource-name> 3.0 --agent-name travel_agent
"""

from pathlib import Path

import vertexai
from google import genai
from vertexai import agent_engines

from src.config import GCP_PROJECT_ID, GCP_REGION
from src.eval.one_time_eval import HELPFULNESS_METRIC, TOOL_USE_METRIC
from src.eval.agent_eval_configs import build_agent_info

SCENARIO_DIR = Path(__file__).parent / "scenarios"

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
    vertexai.init(project=GCP_PROJECT_ID, location=GCP_REGION)
    client = genai.Client(
        vertexai=True,
        project=GCP_PROJECT_ID,
        location=GCP_REGION,
    )

    # Build agent info without MCP connections
    agent_info = build_agent_info(agent_name)

    generation_instruction = GENERATION_INSTRUCTIONS.get(
        agent_name, GENERATION_INSTRUCTIONS["coordinator_agent"]
    )

    # Step 1: Generate synthetic conversation scenarios
    print(f"[1/3] Generating {scenario_count} conversation scenarios for {agent_name}...")
    eval_dataset = client.evals.generate_conversation_scenarios(
        agent_info=agent_info,
        config={
            "count": scenario_count,
            "generation_instruction": generation_instruction,
        },
    )
    print(f"  Generated {len(eval_dataset)} scenarios")

    # Step 2: Run agent inference on generated scenarios
    agent = agent_engines.get(agent_resource_name)
    print(f"[2/3] Running inference (max {max_turns} turns per scenario)...")
    eval_dataset_with_traces = client.evals.run_inference(
        agent=agent,
        src=eval_dataset,
        config={
            "user_simulator_config": {
                "max_turn": max_turns,
                "model": "gemini-flash-latest",
            },
        },
    )
    print("  Inference complete")

    # Step 3: Evaluate with metrics
    print("[3/3] Evaluating with metrics...")
    eval_result = client.evals.evaluate(
        src=eval_dataset_with_traces,
        config={
            "metrics": [HELPFULNESS_METRIC, TOOL_USE_METRIC],
        },
    )

    # Report results
    print(f"\n=== Simulated Evaluation Results ({agent_name}) ===")
    all_pass = True
    for metric_name, scores in eval_result.summary_metrics.items():
        avg_score = scores.get("mean", 0) if isinstance(scores, dict) else scores
        status = "PASS" if avg_score >= score_threshold else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"  {metric_name}: {avg_score:.2f} (threshold: {score_threshold}) [{status}]")

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
