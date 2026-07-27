"""Tests for the GEAP 'Optimize > Evaluation' 100%-coverage feature.

All offline (no live API): validates the new metric registry, multi-turn metrics,
loss taxonomy, quality-drift policy, offline-trace fixture, the demo package, the
notebook, the OTEL config, and that the coverage matrix in eval_operations.md maps
every doc page to a file that actually exists.
"""

import json
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
EVAL_DIR = REPO / "src" / "eval"
DOCS = REPO / "docs"

# The nine "Optimize > Evaluation" doc-page slugs that must be covered.
DOC_SLUGS = [
    "agent-evaluation",
    "evaluate-agents",
    "evaluate-offline",
    "evaluate-simulated",
    "evaluate-online",
    "manage-metrics",
    "view-results",
    "quality-alerts",
    "optimize-agent",
]

# Coverage-matrix mapping: each doc page -> at least one repo artifact that must exist.
COVERAGE_ARTIFACTS = {
    "agent-evaluation": ["src/eval/demo/full_eval_demo.py", "docs/evaluation_demo.md"],
    "evaluate-agents": ["src/eval/one_time_eval.py", "src/eval/multi_agent_batch_eval.py"],
    "evaluate-offline": ["src/eval/offline_trace_eval.py", "src/eval/sample_traces.jsonl"],
    "evaluate-simulated": ["src/eval/simulated_eval.py", "src/eval/env_simulation.py"],
    "evaluate-online": ["src/eval/setup_online_evaluators.py"],
    "manage-metrics": ["src/eval/metric_registry.py"],
    "view-results": ["src/eval/failure_clusters.py", "src/eval/loss_taxonomy.py"],
    "quality-alerts": ["src/eval/quality_alerts.py", "src/eval/policies/quality_drift_policy.yaml"],
    "optimize-agent": ["src/eval/sdk_optimize.py", "src/eval/agents_cli_demo.sh", "src/optimize/run_optimize.py"],
}


class TestMetricRegistry:
    def test_code_execution_metric_defines_evaluate(self):
        from src.eval.metric_registry import CODE_POLICY_LIMIT_METRIC

        assert CODE_POLICY_LIMIT_METRIC is not None
        assert "def evaluate" in (CODE_POLICY_LIMIT_METRIC.custom_function or "")

    def test_exact_match_reference_based_metric_builds(self):
        from src.eval.metric_registry import EXACT_MATCH_METRIC

        assert EXACT_MATCH_METRIC is not None

    def test_custom_metrics_present(self):
        from src.eval.metric_registry import custom_metrics

        names = {getattr(m, "name", type(m).__name__) for m in custom_metrics()}
        assert "policy_compliance" in names
        assert "policy_limit_exact" in names

    def test_code_metric_logic(self):
        """The embedded evaluate() should score correct/incorrect policy limits."""
        from src.eval.metric_registry import _CODE_POLICY_LIMIT_FN

        ns: dict = {}
        exec(_CODE_POLICY_LIMIT_FN, ns)
        evaluate = ns["evaluate"]
        assert evaluate({"response": "The meal limit is $75 per day"}) == 1.0
        assert evaluate({"response": "The meal limit is $99"}) == 0.0


class TestMultiTurnMetrics:
    def test_multi_turn_rubric_metrics_resolve(self):
        from src.eval.metric_registry import MULTI_TURN_RUBRIC_METRICS

        # At least task-success + tool-use + trajectory should resolve on a
        # modern SDK; guard for older SDKs by requiring at least one.
        assert len(MULTI_TURN_RUBRIC_METRICS) >= 1

    def test_get_multi_turn_metrics(self):
        from src.eval.agent_eval_configs import get_multi_turn_metrics

        metrics = get_multi_turn_metrics("coordinator_agent")
        assert isinstance(metrics, list) and len(metrics) >= 1


class TestMetricSelectionWiring:
    def test_custom_metrics_wired_for_expense(self):
        from src.eval.agent_eval_configs import get_metrics

        names = {getattr(m, "name", getattr(m, "value", str(m))) for m in get_metrics("expense_agent")}
        # expense agent gets the policy/tool custom metrics on top of base rubrics
        assert names & {"policy_compliance", "geap_tool_use", "policy_limit_exact"}

    def test_base_only_mode(self):
        from src.eval.agent_eval_configs import get_metrics

        assert len(get_metrics("coordinator_agent", include_custom=False)) == 3


class TestLossTaxonomy:
    def test_taxonomies_non_empty(self):
        from src.eval import loss_taxonomy as t

        assert t.TASK_SUCCESS_TAXONOMY and t.TOOL_USE_QUALITY_TAXONOMY
        assert len(t.ALL_PATTERNS) >= 20

    def test_map_cluster_to_taxonomy(self):
        from src.eval.loss_taxonomy import map_cluster_to_taxonomy

        r = map_cluster_to_taxonomy({"title": "Incorrect Tool Selection", "description": ""})
        assert r["category"] == "Tool Calling"
        assert map_cluster_to_taxonomy({"title": "totally unrelated"})["pattern"] == "Uncategorized"


class TestQualityDriftPolicy:
    def test_policy_yaml_exists_and_references_native_metric(self):
        path = EVAL_DIR / "policies" / "quality_drift_policy.yaml"
        assert path.exists()
        text = path.read_text()
        assert "aiplatform.googleapis.com/online_evaluator/scores" in text
        assert "evaluation_metric_name" in text

    def test_policy_yaml_parses_if_pyyaml_available(self):
        yaml = pytest.importorskip("yaml")
        path = EVAL_DIR / "policies" / "quality_drift_policy.yaml"
        data = yaml.safe_load(path.read_text())
        assert isinstance(data, dict)
        assert "conditions" in data or "displayName" in data


class TestOfflineTraceFixture:
    def test_sample_traces_parse(self):
        path = EVAL_DIR / "sample_traces.jsonl"
        assert path.exists()
        records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        assert len(records) >= 6
        for rec in records:
            assert rec.get("prompt") and rec.get("response")


class TestOtelConfig:
    def test_multimodal_upload_vars_present(self):
        from src.config import OTEL_ENV_VARS

        assert OTEL_ENV_VARS.get("OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK") == "upload"
        assert OTEL_ENV_VARS.get("OTEL_INSTRUMENTATION_GENAI_UPLOAD_FORMAT") == "jsonl"
        assert OTEL_ENV_VARS.get("OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH", "").startswith("gs://")


class TestDemoImports:
    @pytest.mark.parametrize("module", [
        "src.eval.demo.steps",
        "src.eval.demo.full_eval_demo",
        "src.eval.metric_registry",
        "src.eval.offline_trace_eval",
        "src.eval.sdk_optimize",
        "src.eval.loss_taxonomy",
        "src.eval.env_simulation",
    ])
    def test_module_imports(self, module):
        import importlib

        assert importlib.import_module(module) is not None

    def test_steps_expose_all_features(self):
        from src.eval.demo import steps

        for fn in ["register_metrics", "rapid_eval", "testcase_eval", "simulate",
                   "environment_simulation", "offline_eval", "online_monitors",
                   "analyze", "optimize", "quality_alerts"]:
            assert callable(getattr(steps, fn))


class TestNotebookValidity:
    def test_notebook_parses_and_has_cells(self):
        path = EVAL_DIR / "demo" / "evaluation_demo.ipynb"
        assert path.exists()
        nb = json.loads(path.read_text())
        assert nb.get("nbformat") == 4
        assert len(nb.get("cells", [])) >= 10


class TestCoverageMatrix:
    def test_all_doc_slugs_linked_in_eval_operations(self):
        text = (DOCS / "eval_operations.md").read_text()
        for slug in DOC_SLUGS:
            assert f"evaluation/{slug}" in text, f"Doc page not linked in eval_operations.md: {slug}"

    def test_all_doc_slugs_linked_in_demo_walkthrough(self):
        text = (DOCS / "evaluation_demo.md").read_text()
        for slug in DOC_SLUGS:
            assert f"evaluation/{slug}" in text, f"Doc page not linked in evaluation_demo.md: {slug}"

    @pytest.mark.parametrize("slug", DOC_SLUGS)
    def test_coverage_artifacts_exist(self, slug):
        for rel in COVERAGE_ARTIFACTS[slug]:
            assert (REPO / rel).exists(), f"Coverage artifact missing for {slug}: {rel}"
