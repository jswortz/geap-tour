"""Tests for the 5-tier multi-model prompt router."""

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from src.router.complexity import ComplexityResult, _score_to_level
from src.router.cost_tracker import CostTracker, RequestLog, estimate_cost


class TestComplexityScoring:
    def test_low_score(self):
        assert _score_to_level(0.0) == "low"
        assert _score_to_level(0.1) == "low"
        assert _score_to_level(0.19) == "low"

    def test_medium_low_score(self):
        assert _score_to_level(0.20) == "medium_low"
        assert _score_to_level(0.30) == "medium_low"
        assert _score_to_level(0.39) == "medium_low"

    def test_medium_score(self):
        assert _score_to_level(0.40) == "medium"
        assert _score_to_level(0.50) == "medium"
        assert _score_to_level(0.59) == "medium"

    def test_medium_high_score(self):
        assert _score_to_level(0.60) == "medium_high"
        assert _score_to_level(0.70) == "medium_high"
        assert _score_to_level(0.79) == "medium_high"

    def test_high_score(self):
        assert _score_to_level(0.80) == "high"
        assert _score_to_level(0.9) == "high"
        assert _score_to_level(1.0) == "high"

    def test_complexity_result_dataclass(self):
        r = ComplexityResult(level="high", score=0.85, reason="multi-step planning")
        assert r.level == "high"
        assert r.score == 0.85
        assert r.reason == "multi-step planning"


class TestCostTracker:
    def test_estimate_cost_flash_lite(self):
        cost = estimate_cost("gemini-2.5-flash-lite", 1_000_000, 1_000_000)
        assert cost == pytest.approx(0.075 + 0.30, rel=1e-4)

    def test_estimate_cost_flash(self):
        cost = estimate_cost("gemini-2.5-flash", 1_000_000, 1_000_000)
        assert cost == pytest.approx(0.15 + 0.60, rel=1e-4)

    def test_estimate_cost_pro(self):
        cost = estimate_cost("gemini-2.5-pro", 1_000_000, 1_000_000)
        assert cost == pytest.approx(1.25 + 10.00, rel=1e-4)

    def test_estimate_cost_sonnet(self):
        cost = estimate_cost("claude-sonnet-4-6", 1_000_000, 1_000_000)
        assert cost == pytest.approx(3.00 + 15.00, rel=1e-4)

    def test_estimate_cost_opus(self):
        cost = estimate_cost("claude-opus-4-6", 1_000_000, 1_000_000)
        assert cost == pytest.approx(15.00 + 75.00, rel=1e-4)

    def test_cost_ratio_lite_vs_opus(self):
        lite = estimate_cost("gemini-2.5-flash-lite", 200, 500)
        opus = estimate_cost("claude-opus-4-6", 200, 500)
        assert opus / lite > 100

    def test_cost_curve_is_monotonic(self):
        models = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro", "claude-sonnet-4-6", "claude-opus-4-6"]
        costs = [estimate_cost(m, 1000, 1000) for m in models]
        for i in range(len(costs) - 1):
            assert costs[i] < costs[i + 1], f"{models[i]} should be cheaper than {models[i+1]}"

    def test_tracker_total(self, tmp_path):
        tracker = CostTracker(log_path=tmp_path / "test.jsonl")
        tracker.log_request(RequestLog(
            prompt="test", complexity_level="low", complexity_score=0.1,
            model_used="gemini-2.5-flash-lite",
            input_tokens=200, output_tokens=500, latency_ms=50, cost_usd=0.001,
        ))
        tracker.log_request(RequestLog(
            prompt="test2", complexity_level="high", complexity_score=0.9,
            model_used="claude-opus-4-6",
            input_tokens=200, output_tokens=500, latency_ms=2000, cost_usd=0.04,
        ))
        assert tracker.total_cost() == pytest.approx(0.041)
        assert len(tracker.cost_by_model()) == 2

    def test_tracker_jsonl_output(self, tmp_path):
        log_file = tmp_path / "test.jsonl"
        tracker = CostTracker(log_path=log_file)
        tracker.log_request(RequestLog(
            prompt="test", complexity_level="low", complexity_score=0.1,
            model_used="gemini-2.5-flash-lite",
            input_tokens=100, output_tokens=200, latency_ms=30, cost_usd=0.0001,
        ))
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["model_used"] == "gemini-2.5-flash-lite"
        assert data["complexity_level"] == "low"

    def test_generate_report(self, tmp_path):
        tracker = CostTracker(log_path=tmp_path / "test.jsonl")
        tracker.log_request(RequestLog(
            prompt="test", complexity_level="low", complexity_score=0.1,
            model_used="gemini-2.5-flash-lite",
            input_tokens=200, output_tokens=500, latency_ms=50, cost_usd=0.001,
        ))
        report = tracker.generate_report()
        assert "Cost Summary" in report
        assert "gemini-2.5-flash-lite" in report


class TestAgentConfig:
    def test_resolve_model_gemini(self):
        from src.router.agents import _resolve_model
        assert _resolve_model("gemini-2.5-flash") == "gemini-2.5-flash"
        assert _resolve_model("gemini-2.5-flash-lite") == "gemini-2.5-flash-lite"
        assert _resolve_model("gemini-2.5-pro") == "gemini-2.5-pro"

    def test_resolve_model_litellm(self):
        from src.router.agents import _resolve_model
        from google.adk.models.lite_llm import LiteLlm
        result = _resolve_model("claude-opus-4-6")
        assert isinstance(result, LiteLlm)
        result2 = _resolve_model("claude-sonnet-4-6")
        assert isinstance(result2, LiteLlm)

    def test_router_has_five_sub_agents(self):
        from src.router.agents import router_agent
        assert len(router_agent.sub_agents) == 5

    def test_sub_agent_names(self):
        from src.router.agents import router_agent
        names = {a.name for a in router_agent.sub_agents}
        assert names == {"lite_agent", "flash_agent", "pro_agent", "sonnet_agent", "opus_agent"}

    def test_router_has_callback(self):
        from src.router.agents import router_agent
        assert router_agent.before_agent_callback is not None
