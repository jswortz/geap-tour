"""Orchestrator — runs all evaluations and produces a consolidated report.

Usage:
    uv run python -m src.eval.run_all_evals
    uv run python -m src.eval.run_all_evals --skip-traffic
    uv run python -m src.eval.run_all_evals --batch-only
    uv run python -m src.eval.run_all_evals --monitors-only
"""

import argparse
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

from src.config import (
    GCP_PROJECT_ID,
    GCP_REGION,
    AGENT_ENGINE_ID,
    EVAL_OUTPUT_DIR,
)


def _resolve_agent_resource_name(agent_id: str) -> str:
    if agent_id.startswith("projects/"):
        return agent_id
    return f"projects/{GCP_PROJECT_ID}/locations/{GCP_REGION}/reasoningEngines/{agent_id}"


def run_all_evals(
    agent_id: str = AGENT_ENGINE_ID,
    skip_traffic: bool = False,
    batch_only: bool = False,
    monitors_only: bool = False,
    threshold: float = 3.0,
):
    """Run the full evaluation pipeline and produce a consolidated report."""
    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_dir = Path(EVAL_OUTPUT_DIR) / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    agent_resource_name = _resolve_agent_resource_name(agent_id)

    print("=" * 70)
    print("  GEAP COMPREHENSIVE EVALUATION PIPELINE")
    print("=" * 70)
    print(f"  Run ID:    {run_id}")
    print(f"  Agent:     {agent_resource_name}")
    print(f"  Output:    {output_dir}")
    print(f"  Threshold: {threshold}")
    print()

    results = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "agent": agent_resource_name,
        "threshold": threshold,
    }

    # --- Phase 1: Setup ---
    print("[Phase 1/6] SETUP")
    try:
        from src.eval.manage_monitors import list_monitors
        list_monitors()
    except Exception as e:
        print(f"  Monitor check: {e}")
    print()

    if monitors_only:
        _run_monitors_phase(agent_resource_name, output_dir, results)
        _generate_report(output_dir, results)
        return results

    # --- Phase 2: Traffic Generation ---
    if not skip_traffic and not batch_only:
        print("[Phase 2/6] TRAFFIC GENERATION")
        try:
            from src.traffic.generate_traffic import generate_traffic
            generate_traffic(agent_resource_name, count=2)
            print("  Waiting 30s for trace ingestion...")
            time.sleep(30)
        except Exception as e:
            print(f"  Traffic generation failed: {e}")
            print("  Continuing with batch evals...")
        print()
    else:
        print("[Phase 2/6] TRAFFIC GENERATION (skipped)")
        print()

    # --- Phase 3: Batch Evaluations ---
    print("[Phase 3/6] BATCH EVALUATIONS")
    try:
        from src.eval.multi_agent_batch_eval import run_multi_agent_batch_eval
        batch_results = run_multi_agent_batch_eval(
            agent_id=agent_id,
            score_threshold=threshold,
            output_path=str(output_dir / "batch_results.json"),
        )
        results["batch"] = batch_results
    except Exception as e:
        print(f"  Batch eval failed: {e}")
        results["batch"] = {"status": "error", "error": str(e)}
    print()

    if batch_only:
        _generate_report(output_dir, results)
        return results

    # --- Phase 4: Simulated Evaluations ---
    print("[Phase 4/6] SIMULATED EVALUATIONS")
    sim_results = {}
    for agent_name in ["coordinator_agent", "travel_agent"]:
        try:
            from src.eval.simulated_eval import run_simulated_eval
            passed = run_simulated_eval(
                agent_resource_name,
                agent_name=agent_name,
                scenario_count=5,
                max_turns=3,
                score_threshold=threshold,
            )
            sim_results[agent_name] = {"passed": passed}
        except Exception as e:
            print(f"  Simulated eval for {agent_name} failed: {e}")
            sim_results[agent_name] = {"error": str(e)}
    results["simulated"] = sim_results

    with open(output_dir / "simulation_results.json", "w") as f:
        json.dump(sim_results, f, indent=2, default=str)
    print()

    # --- Phase 5: Complexity Evaluation ---
    print("[Phase 5/6] COMPLEXITY EVALUATION")
    try:
        from src.eval.complexity_metrics import (
            run_complexity_accuracy_eval,
            run_cost_efficiency_eval,
        )
        from src.eval.agent_eval_configs import ROUTER_EVAL_CASES

        accuracy_result = asyncio.run(run_complexity_accuracy_eval(ROUTER_EVAL_CASES))
        cost_result = asyncio.run(run_cost_efficiency_eval(ROUTER_EVAL_CASES))

        complexity_results = {
            "accuracy": accuracy_result,
            "cost_efficiency": cost_result,
        }
        results["complexity"] = complexity_results

        with open(output_dir / "complexity_eval.json", "w") as f:
            json.dump(complexity_results, f, indent=2, default=str)

        print(f"  Classifier accuracy: {accuracy_result['accuracy_pct']}")
        print(f"  Cost savings vs all-Opus: {cost_result['savings_pct']}%")
    except Exception as e:
        print(f"  Complexity eval failed: {e}")
        results["complexity"] = {"error": str(e)}
    print()

    # --- Phase 6: Monitor Verification ---
    _run_monitors_phase(agent_resource_name, output_dir, results)

    # --- Generate Report ---
    _generate_report(output_dir, results)

    return results


def _run_monitors_phase(agent_resource_name: str, output_dir: Path, results: dict):
    """Run monitor verification phase."""
    print("[Phase 6/6] MONITOR VERIFICATION")
    try:
        from src.eval.verify_monitors import verify_monitor_results, generate_markdown_report
        monitor_data = verify_monitor_results(output_format="json")
        results["monitors"] = monitor_data

        with open(output_dir / "monitor_status.json", "w") as f:
            json.dump(monitor_data, f, indent=2, default=str)

        if monitor_data and monitor_data.get("status") == "ok":
            md = generate_markdown_report(monitor_data)
            print(md)
        elif monitor_data:
            print(f"  Status: {monitor_data.get('status')}")
            print(f"  {monitor_data.get('message', '')}")
    except Exception as e:
        print(f"  Monitor verification failed: {e}")
        results["monitors"] = {"error": str(e)}
    print()


def _generate_report(output_dir: Path, results: dict):
    """Generate the final markdown report."""
    lines = [
        "# GEAP Comprehensive Evaluation Report",
        "",
        f"**Run ID:** {results['run_id']}",
        f"**Timestamp:** {results['timestamp']}",
        f"**Agent:** {results['agent']}",
        f"**Threshold:** {results.get('threshold', 3.0)}",
        "",
    ]

    # Batch results
    batch = results.get("batch", {})
    if batch and batch.get("agents"):
        lines.extend([
            "## Batch Evaluation Results",
            "",
            "| Agent | Status | Test Cases | Metrics |",
            "|-------|--------|-----------|---------|",
        ])
        for name, r in batch["agents"].items():
            status = r.get("status", "N/A")
            cases = r.get("test_cases", 0)
            metrics = r.get("metrics", {})
            metric_summary = ", ".join(
                f"{k}: {v['score']:.2f}" for k, v in metrics.items()
            ) if metrics else "N/A"
            lines.append(f"| {name} | {status} | {cases} | {metric_summary} |")
        lines.append("")

    # Simulated results
    sim = results.get("simulated", {})
    if sim:
        lines.extend(["## Simulated Evaluation Results", ""])
        for name, r in sim.items():
            status = "PASS" if r.get("passed") else r.get("error", "FAIL")
            lines.append(f"- **{name}:** {status}")
        lines.append("")

    # Complexity results
    comp = results.get("complexity", {})
    if comp and not comp.get("error"):
        acc = comp.get("accuracy", {})
        cost = comp.get("cost_efficiency", {})
        lines.extend([
            "## Complexity Routing Evaluation",
            "",
            f"- **Classifier accuracy:** {acc.get('accuracy_pct', 'N/A')}",
            f"- **Cost savings vs all-Opus:** {cost.get('savings_pct', 'N/A')}%",
            f"- **Routed cost:** ${cost.get('routed_cost_usd', 0):.6f}",
            f"- **All-Opus cost:** ${cost.get('all_opus_cost_usd', 0):.6f}",
            "",
        ])

        if acc.get("confusion_matrix"):
            lines.extend([
                "### Confusion Matrix",
                "",
                "| Expected \\ Actual | Low | Medium | High |",
                "|-------------------|-----|--------|------|",
            ])
            for level in ("low", "medium", "high"):
                row = acc["confusion_matrix"].get(level, {})
                lines.append(
                    f"| {level} | {row.get('low', 0)} | {row.get('medium', 0)} | {row.get('high', 0)} |"
                )
            lines.append("")

    # Monitor results
    monitors = results.get("monitors", {})
    if monitors and monitors.get("status") == "ok":
        from src.eval.verify_monitors import generate_markdown_report
        lines.append(generate_markdown_report(monitors))
        lines.append("")

    report = "\n".join(lines)
    report_path = output_dir / "report.md"
    with open(report_path, "w") as f:
        f.write(report)

    # Save full results
    with open(output_dir / "full_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"{'=' * 70}")
    print(f"  REPORT SAVED: {report_path}")
    print(f"  Full results: {output_dir / 'full_results.json'}")
    print(f"{'=' * 70}")


def main():
    parser = argparse.ArgumentParser(description="Run all GEAP evaluations")
    parser.add_argument("--agent-id", default=AGENT_ENGINE_ID, help="Agent Engine ID")
    parser.add_argument("--threshold", type=float, default=3.0, help="Score threshold")
    parser.add_argument("--skip-traffic", action="store_true", help="Skip traffic generation")
    parser.add_argument("--batch-only", action="store_true", help="Only run batch evals")
    parser.add_argument("--monitors-only", action="store_true", help="Only check monitors")
    args = parser.parse_args()

    run_all_evals(
        agent_id=args.agent_id,
        skip_traffic=args.skip_traffic,
        batch_only=args.batch_only,
        monitors_only=args.monitors_only,
        threshold=args.threshold,
    )


if __name__ == "__main__":
    main()
