"""Tests for agent configurations — validates structure without requiring GCP."""


def test_travel_agent_config():
    from src.agents.travel_agent import travel_agent
    assert travel_agent.name == "travel_agent"
    assert len(travel_agent.tools) == 2


def test_expense_agent_config():
    from src.agents.expense_agent import expense_agent
    assert expense_agent.name == "expense_agent"
    assert len(expense_agent.tools) == 1


def test_coordinator_agent_config():
    from src.agents.coordinator_agent import coordinator_agent
    assert coordinator_agent.name == "coordinator_agent"
    assert len(coordinator_agent.tools) >= 4  # MCP + PreloadMemory + 2 AgentTools


def test_coordinator_uses_agent_tools():
    from src.agents.coordinator_agent import coordinator_agent
    from google.adk.tools.agent_tool import AgentTool
    agent_tools = [t for t in coordinator_agent.tools if isinstance(t, AgentTool)]
    assert len(agent_tools) == 2
