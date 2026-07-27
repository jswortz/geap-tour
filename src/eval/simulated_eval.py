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
    _patch_evals_extra_fields()

    import vertexai
    from vertexai import Client, types
    from src.config import GCP_PROJECT_ID, GCP_REGION, FLASH_MODEL
    from src.eval.agent_eval_configs import build_agent_info, get_multi_turn_metrics

    vertexai.init(project=GCP_PROJECT_ID, location=GCP_REGION)
    client = Client(project=GCP_PROJECT_ID, location=GCP_REGION)

    # Single-turn metrics double as the fallback set if a multi-turn metric
    # turns out to be unsupported by the evaluate API (see retry below).
    single_turn_metrics = [
        types.RubricMetric.FINAL_RESPONSE_QUALITY,
        types.RubricMetric.SAFETY,
        types.RubricMetric.TOOL_USE_QUALITY,
    ]
    eval_metrics = get_multi_turn_metrics(agent_name) if multi_turn else single_turn_metrics

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

    print(f"[2/3] Running inference (max {max_turns} turns per scenario)...")
    eval_dataset_with_traces = client.evals.run_inference(
        agent=agent_resource_name,
        src=eval_dataset,
        config={
            "user_simulator_config": {
                "max_turn": max_turns,
                "model_name": FLASH_MODEL,
            },
        },
    )
    print("  Inference complete")

    print("[3/3] Evaluating with metrics...")
    try:
        eval_result = client.evals.evaluate(
            dataset=eval_dataset_with_traces,
            metrics=eval_metrics,
        )
    except Exception as e:  # noqa: BLE001
        # One unsupported multi-turn metric shouldn't abort the whole run —
        # print the error and retry once with the safe single-turn metric set.
        print(f"  WARNING: evaluate() failed ({e}); retrying with single-turn metrics...")
        eval_result = client.evals.evaluate(
            dataset=eval_dataset_with_traces,
            metrics=single_turn_metrics,
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
