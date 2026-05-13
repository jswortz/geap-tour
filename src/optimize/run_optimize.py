"""Agent optimization — wrapper around adk optimize (GEPA algorithm).

The GEPA algorithm iteratively refines agent system instructions by:
1. Running evaluation on the current instruction
2. Analyzing failure patterns
3. Generating instruction variants
4. Evaluating variants and selecting the best performer
"""

import subprocess
import sys

from src.config import GCP_PROJECT_ID, GCP_REGION


def run_optimize(
    agent_module: str = "src.agents.travel_agent",
    eval_dataset_path: str | None = None,
    iterations: int = 3,
):
    """Run adk optimize on an agent module.

    Args:
        agent_module: Python module path to the agent (must export the agent variable)
        eval_dataset_path: Path to eval dataset JSON. If None, uses generated scenarios.
        iterations: Number of optimization iterations
    """
    print("=== Agent Optimization (GEPA) ===")
    print(f"Agent module: {agent_module}")
    print(f"Iterations: {iterations}")
    print()

    cmd = [
        "adk", "optimize",
        "--agent-module", agent_module,
        "--project", GCP_PROJECT_ID,
        "--location", GCP_REGION,
        "--iterations", str(iterations),
    ]

    if eval_dataset_path:
        cmd.extend(["--eval-dataset", eval_dataset_path])

    print(f"Running: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, capture_output=False)

    if result.returncode == 0:
        print("\n✓ Optimization complete — check output for improved instructions")
    else:
        print(f"\n✗ Optimization failed (exit code {result.returncode})")

    return result.returncode


if __name__ == "__main__":
    module = sys.argv[1] if len(sys.argv) > 1 else "src.agents.travel_agent"
    dataset = sys.argv[2] if len(sys.argv) > 2 else None
    iters = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    sys.exit(run_optimize(module, dataset, iters))
