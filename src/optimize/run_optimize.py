"""Agent optimization — wrapper around adk optimize (GEPA algorithm).

The GEPA algorithm iteratively refines agent system instructions by:
1. Running evaluation on the current instruction
2. Analyzing failure patterns
3. Generating instruction variants
4. Evaluating variants and selecting the best performer

Usage:
    uv run python -m src.optimize.run_optimize src/agents/travel_agent
    uv run python -m src.optimize.run_optimize src/agents/coordinator_agent
    uv run python -m src.optimize.run_optimize src/router --sampler-config src/optimize/router_sampler_config.json
"""

import os
import subprocess
import sys


SAMPLER_CONFIG = os.path.join(os.path.dirname(__file__), "sampler_config.json")


def run_optimize(
    agent_module_path: str = "src/agents/travel_agent",
    sampler_config_path: str = SAMPLER_CONFIG,
    optimizer_config_path: str | None = None,
    print_detailed: bool = True,
):
    """Run adk optimize on an agent module.

    Args:
        agent_module_path: File path to the agent module directory
            (must contain __init__.py exporting root_agent via agent namespace).
        sampler_config_path: Path to LocalEvalSampler config JSON.
        optimizer_config_path: Optional path to GEPA optimizer config JSON.
        print_detailed: Print detailed optimization results to console.
    """
    print(f"=== Agent Optimization (GEPA) ===")
    print(f"Agent module path: {agent_module_path}")
    print(f"Sampler config:    {sampler_config_path}")
    print()

    cmd = [
        "adk", "optimize",
        agent_module_path,
        "--sampler_config_file_path", sampler_config_path,
    ]

    if optimizer_config_path:
        cmd.extend(["--optimizer_config_file_path", optimizer_config_path])

    if print_detailed:
        cmd.append("--print_detailed_results")

    print(f"Running: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, capture_output=False)

    if result.returncode == 0:
        print("\n✓ Optimization complete — check output for improved instructions")
    else:
        print(f"\n✗ Optimization failed (exit code {result.returncode})")

    return result.returncode


if __name__ == "__main__":
    module_path = sys.argv[1] if len(sys.argv) > 1 else "src/agents/travel_agent"
    sampler = sys.argv[2] if len(sys.argv) > 2 else SAMPLER_CONFIG
    sys.exit(run_optimize(module_path, sampler))
