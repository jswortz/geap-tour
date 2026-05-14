"""Agent optimization — Python-native GEPA wrapper with ADK patches.

Calls the GEPA optimizer API directly (not via subprocess) so we can
patch ADK for MCP timeouts and pydantic extra fields before optimization
runs. The CLI wrapper (`adk optimize`) can't apply these patches.

Usage:
    uv run python -m src.optimize.run_optimize src/agents/coordinator
    uv run python -m src.optimize.run_optimize src/router --sampler-config src/optimize/router_sampler_config.json
"""

import asyncio
import json
import logging
import os
import sys

log = logging.getLogger(__name__)

SAMPLER_CONFIG = os.path.join(os.path.dirname(__file__), "sampler_config.json")


def _patch_adk():
    """Apply ADK patches before optimization runs.

    1. Patches pydantic models to accept extra fields (expected_complexity
       in router evalsets, etc.)
    2. Patches LocalEvalService to skip eval cases with None inferences
       (MCP tool timeouts produce None instead of crashing len(None))
    """
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
                "Skipping eval case %s — inference returned None (MCP timeout)",
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
    log.info("ADK patches applied (extra fields + None inference guard)")


def _load_agent(agent_module_path: str):
    """Load root_agent from an agent module directory."""
    import importlib.util

    init_path = os.path.join(agent_module_path, "__init__.py")
    if not os.path.exists(init_path):
        print(f"Error: {init_path} not found")
        sys.exit(1)

    spec = importlib.util.spec_from_file_location("agent", init_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["agent"] = module
    spec.loader.exec_module(module)
    return module.agent.root_agent


def run_optimize(
    agent_module_path: str = "src/agents/coordinator",
    sampler_config_path: str = SAMPLER_CONFIG,
    optimizer_config_path: str | None = None,
    print_detailed: bool = True,
):
    """Run GEPA optimization with ADK patches applied.

    Args:
        agent_module_path: Path to the agent module directory.
        sampler_config_path: Path to LocalEvalSampler config JSON.
        optimizer_config_path: Optional GEPA optimizer config JSON.
        print_detailed: Print detailed results to console.
    """
    print("=== Agent Optimization (GEPA) ===")
    print(f"Agent:   {agent_module_path}")
    print(f"Sampler: {sampler_config_path}")
    print()

    # Step 1: Apply ADK patches
    print("[1/4] Applying ADK patches...")
    _patch_adk()

    # Step 2: Load agent and configs
    print("[2/4] Loading agent and configs...")
    from google.adk.evaluation.local_eval_sets_manager import LocalEvalSetsManager
    from google.adk.optimization.gepa_root_agent_prompt_optimizer import (
        GEPARootAgentPromptOptimizer,
        GEPARootAgentPromptOptimizerConfig,
    )
    from google.adk.optimization.local_eval_sampler import (
        LocalEvalSampler,
        LocalEvalSamplerConfig,
    )

    root_agent = _load_agent(agent_module_path)
    print(f"  Agent: {root_agent.name}")
    print(f"  Sub-agents: {[a.name for a in root_agent.sub_agents]}")

    app_name = os.path.basename(agent_module_path)
    agents_dir = os.path.dirname(agent_module_path)

    with open(sampler_config_path, "r") as f:
        sampler_config = LocalEvalSamplerConfig.model_validate_json(f.read())

    if sampler_config.app_name != app_name:
        print(f"  Warning: app_name mismatch (config={sampler_config.app_name}, dir={app_name})")
        print(f"  Overriding sampler app_name to '{app_name}'")
        sampler_config.app_name = app_name

    if optimizer_config_path:
        with open(optimizer_config_path, "r") as f:
            optimizer_config = GEPARootAgentPromptOptimizerConfig.model_validate_json(f.read())
    else:
        optimizer_config = GEPARootAgentPromptOptimizerConfig()

    eval_sets_manager = LocalEvalSetsManager(agents_dir=agents_dir)
    sampler = LocalEvalSampler(sampler_config, eval_sets_manager)
    optimizer = GEPARootAgentPromptOptimizer(optimizer_config)

    # Step 3: Run optimization
    print("[3/4] Running GEPA optimization (this may take 10-20 minutes)...")
    optimization_result = asyncio.run(optimizer.optimize(root_agent, sampler))

    # Step 4: Output results
    print("[4/4] Results")
    print("=" * 80)

    best_idx = optimization_result.gepa_result["best_idx"]
    best_agent = optimization_result.optimized_agents[best_idx]

    print("Optimized root agent instruction:")
    print("-" * 80)
    print(best_agent.optimized_agent.instruction)
    print("-" * 80)

    print(f"\nBest variant: {best_idx}")
    print(f"Score: {best_agent.score}")

    if print_detailed and hasattr(optimization_result, "gepa_result"):
        gepa = optimization_result.gepa_result
        print(f"\nGEPA details:")
        print(f"  Generations: {gepa.get('num_generations', '?')}")
        print(f"  Population size: {gepa.get('population_size', '?')}")
        print(f"  Best index: {best_idx}")

    print("\n✓ Optimization complete")
    return optimization_result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    module_path = sys.argv[1] if len(sys.argv) > 1 else "src/agents/coordinator"
    sampler = sys.argv[2] if len(sys.argv) > 2 else SAMPLER_CONFIG
    optimizer = sys.argv[3] if len(sys.argv) > 3 else None
    run_optimize(module_path, sampler, optimizer)
