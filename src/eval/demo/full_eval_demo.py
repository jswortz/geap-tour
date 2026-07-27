"""Full GEAP evaluation demo — runs the Quality Flywheel end-to-end.

Executes one step per feature in Google's Gemini Enterprise Agent Platform
"Optimize > Evaluation" documentation, in flywheel order
(Design -> Execution -> Scoring -> Refinement), each tagged with the doc page it
covers. Defaults to running LIVE against the deployed AGENT_ENGINE_ID; individual
steps degrade gracefully (status="skipped") when a credential/engine/feature is
unavailable, so the orchestrator always completes and emits a JSON report.

Usage:
    uv run python -m src.eval.demo.full_eval_demo                       # live, default engine
    uv run python -m src.eval.demo.full_eval_demo --agent-id <ID>       # live, specific engine
    uv run python -m src.eval.demo.full_eval_demo --offline             # skip live-inference steps
    uv run python -m src.eval.demo.full_eval_demo --emit-json eval_outputs/demo/full_demo.json
    uv run python -m src.eval.demo.full_eval_demo --register-metrics    # also register metrics in the registry

Coverage matrix: docs/eval_operations.md §0 · Walkthrough: docs/evaluation_demo.md
"""

import argparse
import json
import os
from datetime import datetime, timezone

from src.config import AGENT_ENGINE_ID, EVAL_OUTPUT_DIR
from src.eval.demo import steps


def _strip_raw(d: dict) -> dict:
    """Drop non-JSON-serializable raw SDK objects before writing the report."""
    return {k: v for k, v in d.items() if k != "raw"}


def run_demo(agent_id: str = AGENT_ENGINE_ID, agent_name: str = "coordinator_agent",
             offline: bool = False, register: bool = False, timestamp: str | None = None) -> dict:
    """Run every doc feature and return a consolidated, JSON-serializable report."""
    resource = steps.resolve_resource(agent_id)
    client = None if offline else steps.make_client()

    banner = "OFFLINE (fixtures/fallbacks)" if offline else f"LIVE against {resource}"
    print("=" * 78)
    print(f"  GEAP EVALUATION DEMO — 100% coverage of Optimize > Evaluation  [{banner}]")
    print("=" * 78)

    results: list[dict] = []

    def run(label, fn):
        print(f"\n>>> [{label}]")
        out = fn()
        tag = out.get("status", "?").upper()
        print(f"    step {out.get('step')} — {out.get('title')} :: {tag}")
        if out.get("status") == "skipped":
            print(f"    reason: {out.get('reason')}")
        results.append(out)
        return out

    # -- Phase 1: Design / metric setup ------------------------------------
    print("\n----- Phase 1: Design (define metrics) -----")
    run("manage-metrics", lambda: steps.register_metrics(client, do_register=register))

    # -- Phase 2: Execution ------------------------------------------------
    print("\n----- Phase 2: Execution (run inferences, generate traces) -----")
    if not offline:
        run("evaluate-agents/rapid", lambda: steps.rapid_eval(client, resource))
        run("evaluate-agents/testcase", lambda: steps.testcase_eval(agent_id, agent_name))
        run("evaluate-simulated", lambda: steps.simulate(resource, agent_name))
    else:
        print("    (offline: skipping live rapid/testcase/simulate inference steps)")
    run("evaluate-simulated/env", steps.environment_simulation)
    run("evaluate-offline", lambda: steps.offline_eval(client, agent_name))

    # -- Phase 3: Scoring in production ------------------------------------
    print("\n----- Phase 3: Scoring (production monitoring) -----")
    run("evaluate-online", lambda: steps.online_monitors(do_setup=not offline))

    # -- Phase 4: Refinement ----------------------------------------------
    print("\n----- Phase 4: Refinement (analyze -> optimize) -----")
    if not offline:
        run("view-results", lambda: steps.analyze(agent_id))
    else:
        print("    (offline: skipping live failure-cluster analysis)")
    run("optimize-agent", lambda: steps.optimize(client))
    run("quality-alerts", steps.quality_alerts)

    ts = timestamp or datetime.now(timezone.utc).isoformat()
    ok = sum(1 for r in results if r.get("status") == "ok")
    report = {
        "generated": ts,
        "mode": "offline" if offline else "live",
        "agent_engine": resource,
        "agent_name": agent_name,
        "steps_total": len(results),
        "steps_ok": ok,
        "steps_skipped": len(results) - ok,
        "steps": [_strip_raw(r) for r in results],
    }

    print("\n" + "=" * 78)
    print(f"  DEMO COMPLETE — {ok}/{len(results)} steps ran live; "
          f"{len(results) - ok} skipped (offline/no-cred).")
    print("=" * 78)
    return report


def main():
    p = argparse.ArgumentParser(description="Run the full GEAP evaluation flywheel demo.")
    p.add_argument("--agent-id", default=AGENT_ENGINE_ID, help=f"Agent Engine ID (default {AGENT_ENGINE_ID})")
    p.add_argument("--agent-name", default="coordinator_agent")
    p.add_argument("--offline", action="store_true", help="Skip live-inference steps (use fixtures/fallbacks)")
    p.add_argument("--register-metrics", action="store_true", help="Register custom metrics in the Metric Registry")
    p.add_argument("--emit-json", default=None, help="Write the JSON report to this path")
    args = p.parse_args()

    report = run_demo(agent_id=args.agent_id, agent_name=args.agent_name,
                      offline=args.offline, register=args.register_metrics)

    out_path = args.emit_json or os.path.join(EVAL_OUTPUT_DIR, "demo", "full_demo.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nReport written to: {out_path}")


if __name__ == "__main__":
    main()
