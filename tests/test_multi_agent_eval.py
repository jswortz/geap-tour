"""Tests for multi-agent eval infrastructure — validates configs, eval cases, and evalset files."""

import json
from pathlib import Path

import pytest

EVALSETS_DIR = Path(__file__).parent.parent / "src" / "eval" / "evalsets"
SCENARIOS_DIR = Path(__file__).parent.parent / "src" / "eval" / "scenarios"

EVALSET_FILES = [
    "coordinator.evalset.json",
    "travel_agent.evalset.json",
    "expense_agent.evalset.json",
    "router_agent.evalset.json",
]

SCENARIO_FILES = [
    "coordinator_scenarios.json",
    "travel_scenarios.json",
    "expense_scenarios.json",
    "router_scenarios.json",
]


class TestAgentInfoBuilder:
    def test_coordinator_agent_info(self):
        from src.eval.agent_eval_configs import build_agent_info

        info = build_agent_info("coordinator_agent")
        assert info is not None

    def test_travel_agent_info(self):
        from src.eval.agent_eval_configs import build_agent_info

        info = build_agent_info("travel_agent")
        assert info is not None

    def test_expense_agent_info(self):
        from src.eval.agent_eval_configs import build_agent_info

        info = build_agent_info("expense_agent")
        assert info is not None

    def test_router_agent_info(self):
        from src.eval.agent_eval_configs import build_agent_info

        info = build_agent_info("router_agent")
        assert info is not None

    def test_unknown_agent_raises(self):
        from src.eval.agent_eval_configs import build_agent_info

        with pytest.raises(ValueError):
            build_agent_info("nonexistent_agent")


class TestEvalCasesPerAgent:
    def test_coordinator_has_cases(self):
        from src.eval.agent_eval_configs import get_eval_cases

        cases = get_eval_cases("coordinator_agent")
        assert len(cases) >= 8

    def test_travel_has_cases(self):
        from src.eval.agent_eval_configs import get_eval_cases

        cases = get_eval_cases("travel_agent")
        assert len(cases) >= 8

    def test_expense_has_cases(self):
        from src.eval.agent_eval_configs import get_eval_cases

        cases = get_eval_cases("expense_agent")
        assert len(cases) >= 8

    def test_router_has_cases(self):
        from src.eval.agent_eval_configs import get_eval_cases

        cases = get_eval_cases("router_agent")
        assert len(cases) >= 8

    def test_router_cases_have_expected_complexity(self):
        from src.eval.agent_eval_configs import ROUTER_EVAL_CASES

        for case in ROUTER_EVAL_CASES:
            assert "expected_complexity" in case, f"Missing expected_complexity in: {case.get('prompt', '?')}"
            assert case["expected_complexity"] in ("low", "medium", "high")


class TestEvalCaseRequiredFields:
    @pytest.fixture(params=["coordinator_agent", "travel_agent", "expense_agent", "router_agent"])
    def agent_cases(self, request):
        from src.eval.agent_eval_configs import get_eval_cases

        return get_eval_cases(request.param)

    def test_prompt_present(self, agent_cases):
        for case in agent_cases:
            assert "prompt" in case, f"Missing 'prompt' field in case: {case}"
            assert len(case["prompt"]) > 0

    def test_category_present(self, agent_cases):
        for case in agent_cases:
            assert "category" in case, f"Missing 'category' field in case: {case}"

    def test_expected_tool_present(self, agent_cases):
        for case in agent_cases:
            assert "expected_tool" in case, f"Missing 'expected_tool' field in case: {case}"


class TestComplexityMetricDefined:
    def test_complexity_routing_metric_exists(self):
        from src.eval.complexity_metrics import COMPLEXITY_ROUTING_METRIC

        assert COMPLEXITY_ROUTING_METRIC is not None

    def test_check_complexity_routing_callable(self):
        from src.eval.complexity_metrics import check_complexity_routing
        import asyncio

        assert callable(check_complexity_routing)


class TestEvalsetFilesValidJson:
    @pytest.mark.parametrize("filename", EVALSET_FILES)
    def test_evalset_parses(self, filename):
        path = EVALSETS_DIR / filename
        assert path.exists(), f"Evalset file not found: {path}"
        with open(path) as f:
            data = json.load(f)
        assert "eval_set_id" in data
        assert "eval_cases" in data
        assert len(data["eval_cases"]) > 0

    @pytest.mark.parametrize("filename", EVALSET_FILES)
    def test_evalset_cases_have_required_fields(self, filename):
        path = EVALSETS_DIR / filename
        with open(path) as f:
            data = json.load(f)
        for case in data["eval_cases"]:
            assert "eval_id" in case, f"Missing eval_id in {filename}"
            assert "conversation" in case, f"Missing conversation in {filename}"
            assert len(case["conversation"]) > 0
            turn = case["conversation"][0]
            assert "user_content" in turn
            assert "final_response" in turn
            assert "intermediate_data" in turn
            assert "tool_uses" in turn["intermediate_data"]

    @pytest.mark.parametrize("filename", EVALSET_FILES)
    def test_evalset_unique_eval_ids(self, filename):
        path = EVALSETS_DIR / filename
        with open(path) as f:
            data = json.load(f)
        ids = [c["eval_id"] for c in data["eval_cases"]]
        assert len(ids) == len(set(ids)), f"Duplicate eval_ids in {filename}: {[x for x in ids if ids.count(x) > 1]}"


class TestEvalConfigFiles:
    def test_static_eval_config(self):
        path = EVALSETS_DIR / "eval_config.json"
        assert path.exists()
        with open(path) as f:
            data = json.load(f)
        assert "criteria" in data
        assert "response_match_score" in data["criteria"]

    def test_dynamic_eval_config(self):
        path = SCENARIOS_DIR / "eval_config.json"
        assert path.exists()
        with open(path) as f:
            data = json.load(f)
        assert "criteria" in data
        assert "user_simulator_config" in data


class TestScenarioFiles:
    @pytest.mark.parametrize("filename", SCENARIO_FILES)
    def test_scenario_parses(self, filename):
        path = SCENARIOS_DIR / filename
        assert path.exists(), f"Scenario file not found: {path}"
        with open(path) as f:
            data = json.load(f)
        assert "scenarios" in data
        assert len(data["scenarios"]) > 0

    @pytest.mark.parametrize("filename", SCENARIO_FILES)
    def test_scenarios_have_required_fields(self, filename):
        path = SCENARIOS_DIR / filename
        with open(path) as f:
            data = json.load(f)
        for scenario in data["scenarios"]:
            assert "starting_prompt" in scenario, f"Missing starting_prompt in {filename}"
            assert "conversation_plan" in scenario, f"Missing conversation_plan in {filename}"
            assert "user_persona" in scenario, f"Missing user_persona in {filename}"

    def test_session_input_exists(self):
        path = SCENARIOS_DIR / "session_input.json"
        assert path.exists()
        with open(path) as f:
            data = json.load(f)
        assert "app_name" in data
        assert "user_id" in data

    def test_user_sim_config(self):
        path = SCENARIOS_DIR / "user_sim_config.json"
        assert path.exists()
        with open(path) as f:
            data = json.load(f)
        assert "count" in data
        assert "model_name" in data


class TestRouterEvalsetComplexityLevels:
    def test_has_all_complexity_levels(self):
        path = EVALSETS_DIR / "router_agent.evalset.json"
        with open(path) as f:
            data = json.load(f)
        levels = set()
        for case in data["eval_cases"]:
            complexity = case["conversation"][0]["intermediate_data"].get("expected_complexity")
            if complexity:
                levels.add(complexity)
        assert levels == {"low", "medium", "high"}, f"Missing complexity levels: {{'low', 'medium', 'high'}} - {levels}"

    def test_min_cases_per_level(self):
        path = EVALSETS_DIR / "router_agent.evalset.json"
        with open(path) as f:
            data = json.load(f)
        counts = {"low": 0, "medium": 0, "high": 0}
        for case in data["eval_cases"]:
            complexity = case["conversation"][0]["intermediate_data"].get("expected_complexity")
            if complexity in counts:
                counts[complexity] += 1
        for level, count in counts.items():
            assert count >= 2, f"Need at least 2 cases for {level}, got {count}"
