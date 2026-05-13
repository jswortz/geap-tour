"""Tests for the multi-model prompt router."""

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from src.router.complexity import ComplexityResult, _score_to_level  # noqa: absolute for tests
from src.router.cost_tracker import CostTracker, RequestLog, estimate_cost  # noqa: absolute for tests


class TestComplexityScoring:
    def test_low_score(self):
        assert _score_to_level(0.1) == "low"
        assert _score_to_level(0.3) == "low"
        assert _score_to_level(0.0) == "low"

    def test_medium_score(self):
        assert _score_to_level(0.35) == "medium"
        assert _score_to_level(0.5) == "medium"
        assert _score_to_level(0.64) == "medium"

    def test_high_score(self):
        assert _score_to_level(0.65) == "high"
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

    def test_estimate_cost_opus(self):
        cost = estimate_cost("vertex_ai/claude-opus-4-7", 1_000_000, 1_000_000)
        assert cost == pytest.approx(15.00 + 75.00, rel=1e-4)

    def test_cost_ratio_lite_vs_opus(self):
        lite = estimate_cost("gemini-2.5-flash-lite", 200, 500)
        opus = estimate_cost("vertex_ai/claude-opus-4-7", 200, 500)
        assert opus / lite > 100

    def test_tracker_total(self, tmp_path):
        tracker = CostTracker(log_path=tmp_path / "test.jsonl")
        tracker.log_request(RequestLog(
            prompt="test", complexity_level="low", complexity_score=0.2,
            model_used="gemini-2.5-flash-lite",
            input_tokens=200, output_tokens=500, latency_ms=50, cost_usd=0.001,
        ))
        tracker.log_request(RequestLog(
            prompt="test2", complexity_level="high", complexity_score=0.9,
            model_used="vertex_ai/claude-opus-4-7",
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
            prompt="test", complexity_level="low", complexity_score=0.2,
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

    def test_resolve_model_litellm(self):
        from src.router.agents import _resolve_model
        from google.adk.models.lite_llm import LiteLlm
        result = _resolve_model("vertex_ai/claude-opus-4-7")
        assert isinstance(result, LiteLlm)

    def test_router_has_three_sub_agents(self):
        from src.router.agents import router_agent
        assert len(router_agent.sub_agents) == 3

    def test_sub_agent_names(self):
        from src.router.agents import router_agent
        names = {a.name for a in router_agent.sub_agents}
        assert names == {"lite_agent", "flash_agent", "opus_agent"}

    def test_router_has_callback(self):
        from src.router.agents import router_agent
        assert router_agent.before_agent_callback is not None
