"""One-time evaluation with custom pointwise metric rubrics."""

import vertexai
from vertexai import Client, types
from google.genai import types as g_types

from src.config import GCP_PROJECT_ID, GCP_REGION

HELPFULNESS_METRIC = types.LLMMetric(
    name="helpfulness",
    prompt_template=types.MetricPromptBuilder(
        instruction="Rate the agent's response for helpfulness.",
        criteria={
            "relevance": "Does the response provide helpful, relevant, and actionable information for the user's travel or expense request?"
        },
        rating_scores={
            "5": "Very helpful — exceeds expectations with proactive suggestions",
            "4": "Helpful — fully addresses the request with clear information",
            "3": "Moderately helpful — addresses the request with minor gaps",
            "2": "Slightly helpful — addresses the request but with significant gaps",
            "1": "Not helpful — ignores the request or provides irrelevant information",
        }
    )
)

TOOL_USE_METRIC = types.LLMMetric(
    name="tool_use_accuracy",
    prompt_template=types.MetricPromptBuilder(
        instruction="Rate the agent's tool usage accuracy.",
        criteria={
            "accuracy": "Does the agent correctly use the available MCP tools to fulfill the request? Are the right tools called with appropriate parameters?"
        },
        rating_scores={
            "5": "Optimal tool use with well-formed parameters and good error handling",
            "4": "Correct tool with appropriate parameters",
            "3": "Correct tool but with parameter issues",
            "2": "Wrong tool or badly formed parameters",
            "1": "No tool use or completely wrong tool",
        }
    )
)

POLICY_COMPLIANCE_METRIC = types.LLMMetric(
    name="policy_compliance",
    prompt_template=types.MetricPromptBuilder(
        instruction="Rate the agent's corporate policy compliance.",
        criteria={
            "compliance": "Does the agent correctly enforce corporate expense policies? Does it flag over-limit expenses and guide the user appropriately?"
        },
        rating_scores={
            "5": "Proactively checks policy before submission and provides clear guidance",
            "4": "Correctly applies policy and informs the user",
            "3": "Applies policy but doesn't guide the user",
            "2": "Mentions policy but applies it incorrectly",
            "1": "Ignores policy limits entirely",
        }
    )
)


def run_one_time_eval(agent_resource_name: str):
    """Run one-time evaluation against a deployed agent."""
    vertexai.init(project=GCP_PROJECT_ID, location=GCP_REGION)
    client = Client(
        project=GCP_PROJECT_ID,
        location=GCP_REGION,
    )

    eval_dataset = types.EvaluationDataset(
        eval_cases=[
            types.EvalCase(prompt=g_types.Content(parts=[g_types.Part.from_text(text="Find flights from SFO to JFK on June 15")], role="user")),
            types.EvalCase(prompt=g_types.Content(parts=[g_types.Part.from_text(text="Search hotels in New York under $300")], role="user")),
            types.EvalCase(prompt=g_types.Content(parts=[g_types.Part.from_text(text="Submit a $500 entertainment expense for user EMP001")], role="user")),
            types.EvalCase(prompt=g_types.Content(parts=[g_types.Part.from_text(text="Check if a $50 meal expense is within policy")], role="user")),
            types.EvalCase(prompt=g_types.Content(parts=[g_types.Part.from_text(text="Book flight FL001 for Jane Doe")], role="user")),
        ]
    )

    print(f"Running one-time eval on {agent_resource_name}...")
    print("  Dataset: 5 prompts")
    print("  Metrics: helpfulness, tool_use_accuracy, policy_compliance")

    print("  Running inference...")
    inference_result = client.evals.run_inference(
        src=eval_dataset,
        agent=agent_resource_name,
    )

    print("  Running evaluation...")
    eval_result = client.evals.evaluate(
        dataset=inference_result,
        metrics=[HELPFULNESS_METRIC, TOOL_USE_METRIC, POLICY_COMPLIANCE_METRIC],
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
