"""Agent optimization — Python-native GEPA / SimplePromptOptimizer wrapper.

Calls the ADK optimizer API directly (not via subprocess). The router evalsets
carry ``expected_complexity`` at the eval-case top level (which ADK's ``EvalCase``
permits via ``extra="allow"``) rather than inside a strict sub-model, so no
runtime monkey-patching of ADK is required.

Two optimizers are supported (the phase-3 "Optimize" step of the Quality
Flywheel, see https://docs.cloud.google.com/gemini-enterprise-agent-platform/
optimize/evaluation/optimize-agent):
  - "gepa"   (default) — GEPARootAgentPromptOptimizer, evolutionary prompt search.
  - "simple"           — google.adk.optimization.SimplePromptOptimizer, a lighter
                         iterative tuner; falls back to GEPA if unavailable in the
                         installed ADK version.

Usage:
    uv run python -m src.optimize.run_optimize src/agents/coordinator
    uv run python -m src.optimize.run_optimize src/agents/coordinator --optimizer simple
    uv run python -m src.optimize.run_optimize src/router --sampler-config src/optimize/router_sampler_config.json
"""

import asyncio
import json
import logging
import os
import sys

log = logging.getLogger(__name__)

SAMPLER_CONFIG = os.path.join(os.path.dirname(__file__), "sampler_config.json")


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


def _ensure_vertex_env() -> None:
    """Route ADK/genai model calls through Vertex AI (ADC) instead of the Gemini Developer API.

    The GEPA optimizer's sampler + reflection model call ``google.genai`` directly; without these the
    client raises "No API key was provided". Set them from src.config if unset (no overwrite)."""
    from src.config import GCP_PROJECT_ID, GCP_REGION

    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", GCP_PROJECT_ID)
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", GCP_REGION)


def run_optimize(
    agent_module_path: str = "src/agents/coordinator",
    sampler_config_path: str = SAMPLER_CONFIG,
    optimizer_config_path: str | None = None,
    print_detailed: bool = True,
    optimizer: str = "gepa",
    max_metric_calls: int | None = None,
):
    """Run prompt optimization with ADK patches applied.

    Args:
        agent_module_path: Path to the agent module directory.
        sampler_config_path: Path to LocalEvalSampler config JSON.
        optimizer_config_path: Optional GEPA optimizer config JSON.
        print_detailed: Print detailed results to console.
        optimizer: Which optimizer to use — "gepa" (default) or "simple".
            "simple" uses google.adk.optimization.SimplePromptOptimizer and
            falls back to GEPA if that class is unavailable in the installed ADK.
    """
    _ensure_vertex_env()

    print(f"=== Agent Optimization ({optimizer}) ===")
    print(f"Agent:   {agent_module_path}")
    print(f"Sampler: {sampler_config_path}")
    print()

    # Step 1: Load agent and configs (shared by all optimizers)
    print("[1/3] Loading agent and configs...")
    from google.adk.evaluation.local_eval_sets_manager import LocalEvalSetsManager
    from google.adk.optimization.local_eval_sampler import (
        LocalEvalSampler,
        LocalEvalSamplerConfig,
    )

    root_agent = _load_agent(agent_module_path)
    print(f"  Agent: {root_agent.name}")
    print(f"  Sub-agents: {[a.name for a in root_agent.sub_agents]}")

    app_name = os.path.basename(agent_module_path)
    agents_dir = os.path.dirname(agent_module_path)

    # The sampler configs use the deterministic `response_match_score` metric ONLY. LLM/rubric judges
    # (final_response_match_v2, safety_v1) can return a None score on a flaky case, and the installed
    # ADK crashes the whole GEPA run on it — google/adk/optimization/local_eval_sampler.py::
    # _extract_eval_data does `round(eval_metric_result.score, 2)` with no None guard
    # ("TypeError: type NoneType doesn't define __round__"). response_match_score always returns a float
    # (every eval case has a reference), so it avoids that upstream bug.
    with open(sampler_config_path, "r") as f:
        sampler_config = LocalEvalSamplerConfig.model_validate_json(f.read())

    if sampler_config.app_name != app_name:
        print(f"  Warning: app_name mismatch (config={sampler_config.app_name}, dir={app_name})")
        print(f"  Overriding sampler app_name to '{app_name}'")
        sampler_config.app_name = app_name

    eval_sets_manager = LocalEvalSetsManager(agents_dir=agents_dir)
    sampler = LocalEvalSampler(sampler_config, eval_sets_manager)

    # Step 3: Run optimization
    optimization_result = None

    if optimizer == "simple":
        try:
            from google.adk.optimization import (
                SimplePromptOptimizer,
                SimplePromptOptimizerConfig,
            )

            print("[2/3] Running SimplePromptOptimizer (iterative prompt tuner)...")
            simple_config = SimplePromptOptimizerConfig(num_iterations=5, batch_size=10)
            optimization_result = asyncio.run(
                SimplePromptOptimizer(simple_config).optimize(root_agent, sampler)
            )
        except ImportError:
            print(
                "  SimplePromptOptimizer is unavailable in the installed ADK "
                "version; falling back to the GEPA optimizer."
            )
            optimizer = "gepa"

    if optimization_result is None:
        # GEPA path — the default, and the fallback when "simple" is unavailable.
        from google.adk.optimization.gepa_root_agent_prompt_optimizer import (
            GEPARootAgentPromptOptimizer,
            GEPARootAgentPromptOptimizerConfig,
        )

        if optimizer_config_path:
            with open(optimizer_config_path, "r") as f:
                optimizer_config = GEPARootAgentPromptOptimizerConfig.model_validate_json(f.read())
        elif max_metric_calls:
            # Bound the search for a demo-length run (default is 100 metric calls ~ 10-20 min).
            optimizer_config = GEPARootAgentPromptOptimizerConfig(max_metric_calls=max_metric_calls)
        else:
            optimizer_config = GEPARootAgentPromptOptimizerConfig()

        gepa_optimizer = GEPARootAgentPromptOptimizer(optimizer_config)

        budget = getattr(optimizer_config, "max_metric_calls", "?")
        print(f"[2/3] Running GEPA optimization (max_metric_calls={budget}; live agent runs)...")
        optimization_result = asyncio.run(gepa_optimizer.optimize(root_agent, sampler))

    # Step 3: Output results
    print("[3/3] Results")
    print("=" * 80)

    if hasattr(optimization_result, "gepa_result"):
        best_idx = optimization_result.gepa_result["best_idx"]
        best_agent = optimization_result.optimized_agents[best_idx]

        print("Optimized root agent instruction:")
        print("-" * 80)
        print(best_agent.optimized_agent.instruction)
        print("-" * 80)

        print(f"\nBest variant: {best_idx}")
        best_scores = getattr(best_agent, "scores", getattr(best_agent, "score", None))
        print(f"Scores: {best_scores}")

        if print_detailed:
            gepa = optimization_result.gepa_result
            print(f"\nGEPA details:")
            print(f"  Generations: {gepa.get('num_generations', '?')}")
            print(f"  Population size: {gepa.get('population_size', '?')}")
            print(f"  Best index: {best_idx}")
    else:
        # SimplePromptOptimizer (or another optimizer) — result shape may differ.
        print("Optimization result:")
        print(optimization_result)

    print("\n✓ Optimization complete")
    return optimization_result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Simple arg parsing: pull out `--optimizer {gepa,simple}` (also supports
    # `--optimizer=simple`) while keeping the existing positional args working:
    #   run_optimize.py [agent_module_path] [sampler_config] [optimizer_config]
    _argv = sys.argv[1:]
    optimizer_choice = "gepa"
    positional: list[str] = []
    _i = 0
    while _i < len(_argv):
        _arg = _argv[_i]
        if _arg == "--optimizer" and _i + 1 < len(_argv):
            optimizer_choice = _argv[_i + 1]
            _i += 2
            continue
        if _arg.startswith("--optimizer="):
            optimizer_choice = _arg.split("=", 1)[1]
            _i += 1
            continue
        positional.append(_arg)
        _i += 1

    if optimizer_choice not in ("gepa", "simple"):
        print(f"Unknown --optimizer '{optimizer_choice}'; using 'gepa'. (choices: gepa, simple)")
        optimizer_choice = "gepa"

    module_path = positional[0] if len(positional) > 0 else "src/agents/coordinator"
    sampler_cfg = positional[1] if len(positional) > 1 else SAMPLER_CONFIG
    optimizer_cfg = positional[2] if len(positional) > 2 else None
    run_optimize(module_path, sampler_cfg, optimizer_cfg, optimizer=optimizer_choice)
