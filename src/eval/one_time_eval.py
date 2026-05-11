"""One-time evaluation with custom pointwise metric rubrics."""

import vertexai
from vertexai import agent_engines
from google.genai import types

from src.config import GCP_PROJECT_ID, GCP_REGION

HELPFULNESS_TEMPLATE = """\
You are an expert evaluator. Rate the agent's response for helpfulness.

Criteria: Does the response provide helpful, relevant, and actionable information for the user's travel or expense request?

Rating Rubric:
1 - Not helpful — ignores the request or provides irrelevant information
2 - Slightly helpful — addresses the request but with significant gaps
3 - Moderately helpful — addresses the request with minor gaps
4 - Helpful — fully addresses the request with clear information
5 - Very helpful — exceeds expectations with proactive suggestions

User prompt: {prompt}
Agent response: {response}

Provide your rating as a single integer (1-5):
"""

TOOL_USE_TEMPLATE = """\
You are an expert evaluator. Rate the agent's tool usage accuracy.

Criteria: Does the agent correctly use the available MCP tools to fulfill the request? Are the right tools called with appropriate parameters?

Rating Rubric:
1 - No tool use or completely wrong tool
2 - Wrong tool or badly formed parameters
3 - Correct tool but with parameter issues
4 - Correct tool with appropriate parameters
5 - Optimal tool use with well-formed parameters and good error handling

User prompt: {prompt}
Agent response: {response}

Provide your rating as a single integer (1-5):
"""

POLICY_COMPLIANCE_TEMPLATE = """\
You are an expert evaluator. Rate the agent's policy compliance.

Criteria: Does the agent correctly enforce corporate expense policies? Does it flag over-limit expenses and guide the user appropriately?

Rating Rubric:
1 - Ignores policy limits entirely
2 - Mentions policy but applies it incorrectly
3 - Applies policy but doesn't guide the user
4 - Correctly applies policy and informs the user
5 - Proactively checks policy before submission and provides clear guidance

User prompt: {prompt}
Agent response: {response}

Provide your rating as a single integer (1-5):
"""

HELPFULNESS_METRIC = types.Metric(
    name="helpfulness",
    prompt_template=HELPFULNESS_TEMPLATE,
)

TOOL_USE_METRIC = types.Metric(
    name="tool_use_accuracy",
    prompt_template=TOOL_USE_TEMPLATE,
)

POLICY_COMPLIANCE_METRIC = types.Metric(
    name="policy_compliance",
    prompt_template=POLICY_COMPLIANCE_TEMPLATE,
)


def run_one_time_eval(agent_resource_name: str):
    """Run one-time evaluation against a deployed agent."""
    from google import genai

    vertexai.init(project=GCP_PROJECT_ID, location=GCP_REGION)
    client = genai.Client(
        vertexai=True,
        project=GCP_PROJECT_ID,
        location=GCP_REGION,
    )

    eval_dataset = types.EvaluationDataset(
        eval_dataset_items=[
            {"prompt": "Find flights from SFO to JFK on June 15"},
            {"prompt": "Search hotels in New York under $300"},
            {"prompt": "Submit a $500 entertainment expense for user EMP001"},
            {"prompt": "Check if a $50 meal expense is within policy"},
            {"prompt": "Book flight FL001 for Jane Doe"},
        ]
    )

    print(f"Running one-time eval on {agent_resource_name}...")
    print(f"  Dataset: 5 prompts")
    print(f"  Metrics: helpfulness, tool_use_accuracy, policy_compliance")

    eval_result = client.evals.evaluate(
        src=eval_dataset,
        config=types.EvaluationConfig(
            agent=agent_resource_name,
            metrics=[HELPFULNESS_METRIC, TOOL_USE_METRIC, POLICY_COMPLIANCE_METRIC],
        ),
    )

    print("\n=== Evaluation Results ===")
    for metric_name, scores in eval_result.summary_metrics.items():
        print(f"  {metric_name}: {scores}")

    return eval_result


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m src.eval.one_time_eval <agent-resource-name>")
        sys.exit(1)
    run_one_time_eval(sys.argv[1])
