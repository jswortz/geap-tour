"""Tests for standalone model-tier agents and shared utilities."""

import pytest
from google.adk.models.lite_llm import LiteLlm


STANDALONE_AGENTS = ["lite_agent", "flash_agent", "pro_agent", "sonnet_agent", "opus_agent"]


class TestResolveModel:
    def test_gemini_2x_passthrough(self):
        from src.config import resolve_model
        result = resolve_model("gemini-2.5-flash")
        assert isinstance(result, str)
        assert result == "gemini-2.5-flash"

    def test_gemini_2x_models_prefix(self):
        from src.config import resolve_model
        result = resolve_model("models/gemini-2.5-flash")
        assert isinstance(result, str)

    def test_gemini_3x_wrapped_with_litellm(self):
        from src.config import resolve_model
        result = resolve_model("gemini-3.5-flash")
        assert isinstance(result, LiteLlm)

    def test_claude_wrapped_with_litellm(self):
        from src.config import resolve_model
        result = resolve_model("claude-sonnet-4-6")
        assert isinstance(result, LiteLlm)

    def test_litellm_adds_vertex_prefix(self):
        from src.config import resolve_model
        result = resolve_model("gemini-3.5-flash")
        assert "vertex_ai/" in result.model

    def test_already_prefixed_not_doubled(self):
        from src.config import resolve_model
        result = resolve_model("vertex_ai/gemini-3.5-flash")
        assert isinstance(result, LiteLlm)
        assert result.model == "vertex_ai/gemini-3.5-flash"


class TestDisablePyopenssl:
    def test_does_not_crash(self):
        from src.config import disable_pyopenssl
        disable_pyopenssl()

    def test_callable(self):
        from src.config import disable_pyopenssl
        assert callable(disable_pyopenssl)


class TestStandaloneAgentConfigs:
    @pytest.mark.parametrize("agent_name", STANDALONE_AGENTS)
    def test_agent_has_correct_name(self, agent_name):
        mod = __import__(f"src.agents.{agent_name}", fromlist=[agent_name])
        agent = getattr(mod, agent_name)
        assert agent.name == agent_name

    @pytest.mark.parametrize("agent_name", STANDALONE_AGENTS)
    def test_agent_has_tools(self, agent_name):
        mod = __import__(f"src.agents.{agent_name}", fromlist=[agent_name])
        agent = getattr(mod, agent_name)
        assert len(agent.tools) >= 4  # 3 MCP + PreloadMemoryTool

    @pytest.mark.parametrize("agent_name", STANDALONE_AGENTS)
    def test_agent_has_instruction(self, agent_name):
        mod = __import__(f"src.agents.{agent_name}", fromlist=[agent_name])
        agent = getattr(mod, agent_name)
        assert agent.instruction is not None
        assert len(agent.instruction) > 50  # GEPA-optimized instructions are substantial

    @pytest.mark.parametrize("agent_name", STANDALONE_AGENTS)
    def test_agent_has_root_agent(self, agent_name):
        mod = __import__(f"src.agents.{agent_name}", fromlist=["root_agent"])
        assert hasattr(mod, "root_agent")

    @pytest.mark.parametrize("agent_name", STANDALONE_AGENTS)
    def test_agent_has_namespace(self, agent_name):
        mod = __import__(f"src.agents.{agent_name}", fromlist=["agent"])
        assert hasattr(mod, "agent")
        assert hasattr(mod.agent, "root_agent")

    @pytest.mark.parametrize("agent_name", STANDALONE_AGENTS)
    def test_agent_exports_instruction(self, agent_name):
        mod = __import__(f"src.agents.{agent_name}", fromlist=["INSTRUCTION"])
        assert hasattr(mod, "INSTRUCTION")
        assert isinstance(mod.INSTRUCTION, str)


class TestStandaloneAgentEvalConfigs:
    @pytest.mark.parametrize("agent_name", STANDALONE_AGENTS)
    def test_build_agent_info(self, agent_name):
        from src.eval.agent_eval_configs import build_agent_info
        info = build_agent_info(agent_name)
        assert info is not None

    @pytest.mark.parametrize("agent_name", STANDALONE_AGENTS)
    def test_has_eval_cases(self, agent_name):
        from src.eval.agent_eval_configs import get_eval_cases
        cases = get_eval_cases(agent_name)
        assert len(cases) >= 10  # 10 travel + 10 expense

    @pytest.mark.parametrize("agent_name", STANDALONE_AGENTS)
    def test_eval_cases_have_reference(self, agent_name):
        from src.eval.agent_eval_configs import get_eval_cases
        cases = get_eval_cases(agent_name)
        for case in cases:
            assert "reference" in case, f"Missing 'reference' in: {case['prompt'][:50]}"


class TestTierEvalCases:
    def test_has_three_tiers(self):
        from src.eval.tier_eval_cases import TIER_EVAL_CASES
        assert set(TIER_EVAL_CASES.keys()) == {"low", "medium", "high"}

    @pytest.mark.parametrize("tier", ["low", "medium", "high"])
    def test_tier_has_cases(self, tier):
        from src.eval.tier_eval_cases import TIER_EVAL_CASES
        assert len(TIER_EVAL_CASES[tier]) >= 5

    @pytest.mark.parametrize("tier", ["low", "medium", "high"])
    def test_tier_cases_have_required_fields(self, tier):
        from src.eval.tier_eval_cases import TIER_EVAL_CASES
        for case in TIER_EVAL_CASES[tier]:
            assert "prompt" in case
            assert "reference" in case
            assert "category" in case
            assert "expected_tool" in case
            assert "expected_signals" in case
            assert "description" in case

    @pytest.mark.parametrize("tier", ["low", "medium", "high"])
    def test_tier_cases_match_category(self, tier):
        from src.eval.tier_eval_cases import TIER_EVAL_CASES
        for case in TIER_EVAL_CASES[tier]:
            assert case["category"] == tier

    def test_tool_names_use_mcp_prefix(self):
        from src.eval.tier_eval_cases import TIER_EVAL_CASES
        for tier, cases in TIER_EVAL_CASES.items():
            for case in cases:
                tool = case["expected_tool"]
                if tool != "multiple":
                    assert "_mcp_" in tool, f"Tool '{tool}' missing MCP prefix in {tier}: {case['prompt'][:50]}"


class TestDeployAgentSets:
    def test_all_agent_sets_have_required_keys(self):
        from src.deploy.deploy_agents import AGENT_SETS
        for name, entry in AGENT_SETS.items():
            assert "loader" in entry, f"Missing 'loader' in {name}"
            assert "engine_id" in entry, f"Missing 'engine_id' in {name}"
            assert "env_var" in entry, f"Missing 'env_var' in {name}"

    def test_standalone_agents_in_agent_sets(self):
        from src.deploy.deploy_agents import AGENT_SETS
        for name in ["lite", "flash", "pro", "sonnet", "opus"]:
            assert name in AGENT_SETS, f"Missing '{name}' in AGENT_SETS"

    def test_coordinator_and_router_in_agent_sets(self):
        from src.deploy.deploy_agents import AGENT_SETS
        assert "coordinator" in AGENT_SETS
        assert "router" in AGENT_SETS

    def test_env_var_names_are_consistent(self):
        from src.deploy.deploy_agents import AGENT_SETS
        for name, entry in AGENT_SETS.items():
            env_var = entry["env_var"]
            assert env_var.endswith("_ID") or env_var.endswith("_ENGINE_ID"), \
                f"Unexpected env_var format for {name}: {env_var}"


class TestGetMetrics:
    def test_returns_six_metrics(self):
        from src.eval.agent_eval_configs import get_metrics
        metrics = get_metrics("lite_agent")
        assert len(metrics) == 6

    def test_same_metrics_for_all_agents(self):
        from src.eval.agent_eval_configs import get_metrics
        lite = get_metrics("lite_agent")
        opus = get_metrics("opus_agent")
        assert len(lite) == len(opus)


class TestRouterImportsInstructions:
    def test_router_subagents_use_standalone_instructions(self):
        from src.router.agents import lite_agent as router_lite
        from src.agents.lite_agent import INSTRUCTION as LITE_INSTRUCTION
        assert router_lite.instruction == LITE_INSTRUCTION

    def test_all_router_subagents_have_instructions(self):
        from src.router.agents import (
            lite_agent, flash_agent, pro_agent, sonnet_agent, opus_agent
        )
        for agent in [lite_agent, flash_agent, pro_agent, sonnet_agent, opus_agent]:
            assert agent.instruction is not None
            assert len(agent.instruction) > 50
