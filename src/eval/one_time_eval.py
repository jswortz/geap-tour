"""One-time evaluation using ADK AgentEvaluator against local evalsets.

Sets inference parallelism to 1 to avoid MCP session contention with
remote Cloud Run servers. Patches an ADK bug where timed-out eval cases
with None inferences crash the evaluator.
"""

import json
import logging
import sys

from google.adk.evaluation import AgentEvaluator
from google.adk.evaluation.eval_set import EvalSet
from google.adk.evaluation.eval_config import EvalConfig
from google.adk.evaluation.base_eval_service import InferenceConfig

log = logging.getLogger(__name__)

EVAL_CONFIG_FILES = {
    "default": "src/eval/evalsets/eval_config.json",
    "router": "src/eval/evalsets/router_eval_config.json",
}

AGENT_MODULES = {
    "coordinator": "src.agents.coordinator_agent",
    "travel": "src.agents.travel_agent",
    "expense": "src.agents.expense_agent",
    "router": "src.router.agents",
}

AGENT_NAMES = {
    "coordinator": "coordinator_agent",
    "travel": "travel_agent",
    "expense": "expense_agent",
    "router": "router_agent",
}

EVALSET_FILES = {
    "coordinator": "src/eval/evalsets/coordinator.evalset.json",
    "travel": "src/eval/evalsets/travel_agent.evalset.json",
    "expense": "src/eval/evalsets/expense_agent.evalset.json",
    "router": "src/eval/evalsets/router_agent.evalset.json",
}

INFERENCE_PARALLELISM = 1


def _patch_eval_service_none_guard():
    """Monkey-patch LocalEvalService to skip eval cases with None inferences,
    and allow custom fields (e.g., expected_complexity) in IntermediateData.

    ADK bug: when an MCP tool times out during inference, the inference result
    has inferences=None. The evaluator then crashes at
    `len(inference_result.inferences)` with TypeError. This patch skips
    those cases gracefully.

    Also patches IntermediateData to accept extra fields like
    expected_complexity used by the router evalset's custom metrics.
    """
    # Patch all ADK eval pydantic models to accept custom fields like
    # expected_complexity in the router evalset's intermediate_data.
    # Must patch every model in eval_case and eval_set modules because
    # EvalSet.model_validate() triggers validation of deeply nested types.
    from google.adk.evaluation import eval_case as _ec, eval_set as _es
    for _mod in (_ec, _es):
        for _name in dir(_mod):
            _cls = getattr(_mod, _name)
            if isinstance(_cls, type) and hasattr(_cls, "model_config"):
                try:
                    if _cls.model_config.get("extra") == "forbid":
                        _cls.model_config["extra"] = "ignore"
                        _cls.__pydantic_complete__ = False
                except (TypeError, AttributeError):
                    pass
    for _mod in (_ec, _es):
        for _name in dir(_mod):
            _cls = getattr(_mod, _name)
            if isinstance(_cls, type) and hasattr(_cls, "model_rebuild"):
                try:
                    _cls.model_rebuild(force=True)
                except Exception:
                    pass

    from google.adk.evaluation import local_eval_service as les

    _orig = les.LocalEvalService._evaluate_single_inference_result

    async def _patched(self, inference_result, evaluate_config):
        if inference_result.inferences is None:
            log.warning(
                "Skipping eval case %s — inference returned None (likely MCP timeout)",
                inference_result.eval_case_id,
            )
            from google.adk.evaluation.eval_result import EvalCaseResult, EvalStatus
            return inference_result, EvalCaseResult(
                eval_id=inference_result.eval_case_id,
                eval_set_id=inference_result.eval_set_id,
                final_eval_status=EvalStatus.NOT_EVALUATED,
                overall_eval_metric_results=[],
                eval_metric_result_per_invocation=[],
                session_id="skipped",
            )
        return await _orig(self, inference_result=inference_result, evaluate_config=evaluate_config)

    les.LocalEvalService._evaluate_single_inference_result = _patched


async def run_one_time_eval(agent_key: str = "coordinator", num_runs: int = 1):
    """Run one-time evaluation against a local agent using ADK evalsets."""
    # Patch must run before EvalSet.model_validate() which triggers
    # IntermediateData validation on evalset JSON
    _patch_eval_service_none_guard()

    module = AGENT_MODULES.get(agent_key)
    agent_name = AGENT_NAMES.get(agent_key)
    evalset_file = EVALSET_FILES.get(agent_key)
    if not module:
        print(f"Unknown agent: {agent_key}. Available: {list(AGENT_MODULES)}")
        sys.exit(1)

    with open(evalset_file) as f:
        eval_set = EvalSet.model_validate(json.load(f))

    config_file = EVAL_CONFIG_FILES.get(agent_key, EVAL_CONFIG_FILES["default"])
    with open(config_file) as f:
        eval_config = EvalConfig.model_validate(json.load(f))

    print(f"Running ADK evaluation for {agent_key}...")
    print(f"  Module:      {module}")
    print(f"  Agent:       {agent_name}")
    print(f"  Evalset:     {evalset_file} ({len(eval_set.eval_cases)} cases)")
    print(f"  Criteria:    {list(eval_config.criteria.keys())}")
    print(f"  Runs:        {num_runs}")
    print(f"  Parallelism: {INFERENCE_PARALLELISM}")

    _orig_default = InferenceConfig.model_fields["parallelism"].default
    InferenceConfig.model_fields["parallelism"].default = INFERENCE_PARALLELISM

    try:
        eval_result = await AgentEvaluator.evaluate_eval_set(
            agent_module=module,
            eval_set=eval_set,
            eval_config=eval_config,
            num_runs=num_runs,
            agent_name=agent_name,
            print_detailed_results=True,
        )
    finally:
        InferenceConfig.model_fields["parallelism"].default = _orig_default

    print("\n=== Evaluation Complete ===")
    return eval_result


if __name__ == "__main__":
    import asyncio
    agent_key = sys.argv[1] if len(sys.argv) > 1 else "coordinator"
    num_runs = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    asyncio.run(run_one_time_eval(agent_key=agent_key, num_runs=num_runs))
