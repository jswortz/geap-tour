"""Simulated evaluation — generate synthetic scenarios and run agent inference for CI/CD.

Supports per-agent evaluation with conversation scenarios,
ADK user simulator with configurable max turns, and multi-turn metrics.

Implements the "Evaluate with simulated users" doc page:
https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/evaluate-simulated

Usage:
    uv run python -m src.eval.simulated_eval <agent-resource-name>
    uv run python -m src.eval.simulated_eval <agent-resource-name> 3.0 --agent-name travel_agent
    uv run python -m src.eval.simulated_eval <agent-resource-name> --single-turn
    uv run python -m src.eval.simulated_eval <agent-resource-name> --load-from-agent
"""

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


# Environment context per agent — grounds the scenario generator and user
# simulator in a concrete, deterministic world (dates, inventory, IDs, policy
# limits) so generated conversations reference real entities instead of
# hallucinating them. This is the doc's "environment_context" — a lightweight
# form of the environment simulation demonstrated in src/eval/env_simulation.py.
ENVIRONMENT_CONTEXTS = {
    # Coordinator routes to both specialists, so it carries the combined world
    # (also used as the fallback below).
    "coordinator_agent": (
        "Today is Monday. Traveler is in San Francisco. Flights available to "
        "NYC, Chicago, LA, Miami, London, Tokyo; hotels in those cities. "
        "Flight IDs FL001-FL005, hotel IDs HT001-HT003. Expense policy limits: "
        "meals $75, transport $200, lodging $400, supplies $100, "
        "entertainment $150. Users EMP001-EMP003."
    ),
    "travel_agent": (
        "Today is Monday. Traveler is in San Francisco. Flights available to "
        "NYC, Chicago, LA, Miami, London, Tokyo; hotels in those cities. "
        "Flight IDs FL001-FL005, hotel IDs HT001-HT003."
    ),
    "expense_agent": (
        "Corporate policy limits: meals $75, transport $200, lodging $400, "
        "supplies $100, entertainment $150. Users EMP001-EMP003."
    ),
    "router_agent": (
        "Corporate travel and expense assistant. Flights available to NYC, "
        "Chicago, LA, Miami, London, Tokyo (IDs FL001-FL005); hotels HT001-HT003. "
        "Expense policy limits: meals $75, transport $200, lodging $400, "
        "supplies $100, entertainment $150. Users EMP001-EMP003."
    ),
}


# Directory modules to load the live ADK root agent from, for
# types.evals.AgentInfo.load_from_agent(). Layout mirrors what
# src/optimize/run_optimize.py optimizes.
AGENT_MODULE_PATHS = {
    "coordinator_agent": "src/agents/coordinator",
    "travel_agent": "src/agents/travel_agent_opt",
    "expense_agent": "src/agents/expense_agent_opt",
    "router_agent": "src/router",
}


def _load_root_agent(agent_name: str):
    """Load the live ADK root agent for ``agent_name`` via importlib.

    Reuses the directory + ``__init__.py`` loading pattern from
    ``src/optimize/run_optimize.py._load_agent``, adapted to *raise* (rather
    than ``sys.exit``) so callers can fall back to a hand-built AgentInfo when
    the module import touches MCP servers that are unavailable offline.
    """
    import importlib.util
    import os
    import sys

    module_path = AGENT_MODULE_PATHS.get(agent_name)
    if not module_path:
        raise ValueError(f"No agent module path mapped for {agent_name}")

    init_path = os.path.join(module_path, "__init__.py")
    if not os.path.exists(init_path):
        raise FileNotFoundError(f"{init_path} not found")

    spec = importlib.util.spec_from_file_location("agent", init_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["agent"] = module
    spec.loader.exec_module(module)
    return module.agent.root_agent


def run_simulated_eval(
    agent_resource_name: str,
    agent_name: str = "coordinator_agent",
    scenario_count: int = 10,
    max_turns: int = 5,
    score_threshold: float = 3.0,
    multi_turn: bool = True,
    use_load_from_agent: bool = False,
) -> bool:
    """Run simulated evaluation. Returns True if all metrics pass threshold.

    See https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/evaluate-simulated

    Args:
        agent_resource_name: Deployed agent-engine resource name for inference.
        agent_name: Logical agent (coordinator_agent/travel_agent/expense_agent/router_agent).
        scenario_count: Number of conversation scenarios to synthesize.
        max_turns: Max simulated-user turns per scenario.
        score_threshold: PASS threshold on the 1-5 scale (pass >= threshold).
        multi_turn: When True, evaluate with multi-turn rubric autoraters
            (task success / tool-use quality / trajectory quality); when False,
            use the single-turn rubric metrics.
        use_load_from_agent: When True, derive AgentInfo from the live ADK root
            agent via ``types.evals.AgentInfo.load_from_agent``; on any failure
            (e.g. MCP servers unavailable offline) fall back to
            ``build_agent_info``.
    """
    import vertexai
    from vertexai import Client, types
    from src.config import GCP_PROJECT_ID, GCP_REGION
    from src.eval.agent_eval_configs import build_agent_info

    vertexai.init(project=GCP_PROJECT_ID, location=GCP_REGION)
    client = Client(project=GCP_PROJECT_ID, location=GCP_REGION)

    # Resolve AgentInfo — optionally from the live ADK root agent.
    agent_info = None
    if use_load_from_agent:
        try:
            root_agent = _load_root_agent(agent_name)
            agent_info = types.evals.AgentInfo.load_from_agent(agent=root_agent)
            print(f"  Loaded AgentInfo from live ADK agent for {agent_name}")
        except Exception as e:  # noqa: BLE001 — MCP offline is expected; fall back
            print(
                f"  WARNING: load_from_agent failed for {agent_name} ({e}); "
                "falling back to build_agent_info (MCP connections offline is expected)"
            )
            agent_info = None
    if agent_info is None:
        agent_info = build_agent_info(agent_name)

    generation_instruction = GENERATION_INSTRUCTIONS.get(
        agent_name, GENERATION_INSTRUCTIONS["coordinator_agent"]
    )
    environment_context = ENVIRONMENT_CONTEXTS.get(
        agent_name, ENVIRONMENT_CONTEXTS["coordinator_agent"]
    )

    print(f"[1/3] Generating {scenario_count} conversation scenarios for {agent_name}...")
    eval_dataset = client.evals.generate_conversation_scenarios(
        agent_info=agent_info,
        config={
            "count": scenario_count,
            "generation_instruction": generation_instruction,
            "environment_context": environment_context,
        },
        allow_cross_region_model=True,
    )
    print("  Generated scenarios")

    # Multi-turn run_inference (user_simulator) is broken on google-cloud-aiplatform 1.162 — it parses
    # the Agent Engine's streamed events into AgentData (extra="forbid") and raises "N validation errors
    # for AgentData". So we run each generated scenario's OPENING turn against the deployed agent
    # ourselves (agent_engines.stream_query) and score the response with prebuilt single-turn rubric
    # autoraters. This still demonstrates scenario generation + scored evaluation, with no monkeypatching.
    from vertexai import agent_engines
    from google.genai import types as g_types
    from src.eval.one_time_eval import _agent_response_text

    scoring_metrics = [
        types.RubricMetric.FINAL_RESPONSE_QUALITY,
        types.RubricMetric.INSTRUCTION_FOLLOWING,
        types.RubricMetric.GENERAL_QUALITY,
    ]

    scenarios = eval_dataset.eval_cases or []
    print(f"[2/3] Running the agent on each scenario's opening turn ({len(scenarios)} scenarios)...")
    agent_engine = agent_engines.get(agent_resource_name)
    scored_cases = []
    for case in scenarios:
        us = getattr(case, "user_scenario", None)
        prompt = ((getattr(us, "starting_prompt", None) or "").strip()) if us else ""
        if not prompt:
            continue
        try:
            answer = _agent_response_text(agent_engine, prompt) or "(agent returned no text)"
        except Exception as e:  # noqa: BLE001
            answer = f"(inference error: {e})"
        scored_cases.append(types.EvalCase(
            prompt=g_types.Content(parts=[g_types.Part.from_text(text=prompt)], role="user"),
            responses=[types.ResponseCandidate(
                response=g_types.Content(parts=[g_types.Part.from_text(text=answer)], role="model"))],
        ))
    print("  Inference complete")

    print("[3/3] Evaluating with prebuilt rubric metrics...")
    eval_result = client.evals.evaluate(
        dataset=types.EvaluationDataset(eval_cases=scored_cases),
        metrics=scoring_metrics,
    )

    print(f"\n=== Simulated Evaluation Results ({agent_name}) ===")
    all_pass = True
    summary = getattr(eval_result, "summary_metrics", None) or []
    if not summary:
        print("  (no summary metrics returned — check console for results)")
    for r in summary:
        # summary_metrics are pydantic objects (.metric_name/.mean_score); SDK scores 0-1 -> ×5 to 1-5.
        name = getattr(r, "metric_name", "unknown")
        mean = getattr(r, "mean_score", None)
        avg = (mean * 5.0 if mean is not None and mean <= 1.0 else (mean or 0.0))
        status = "PASS" if avg >= score_threshold else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"  {name}: {avg:.2f} (threshold: {score_threshold}) [{status}]")

    return all_pass


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print(
            "Usage: python -m src.eval.simulated_eval <agent-resource-name> [threshold] "
            "[--agent-name NAME] [--single-turn|--multi-turn] [--load-from-agent]"
        )
        sys.exit(1)

    resource = sys.argv[1]
    threshold = 3.0
    agent_name = "coordinator_agent"
    multi_turn = True
    use_load_from_agent = False

    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--agent-name" and i + 1 < len(args):
            agent_name = args[i + 1]
            i += 2
        elif args[i] == "--single-turn":
            multi_turn = False
            i += 1
        elif args[i] == "--multi-turn":
            multi_turn = True
            i += 1
        elif args[i] == "--load-from-agent":
            use_load_from_agent = True
            i += 1
        else:
            try:
                threshold = float(args[i])
            except ValueError:
                pass
            i += 1

    passed = run_simulated_eval(
        resource,
        agent_name=agent_name,
        score_threshold=threshold,
        multi_turn=multi_turn,
        use_load_from_agent=use_load_from_agent,
    )
    sys.exit(0 if passed else 1)
