"""Tests for agent configurations — validates structure without requiring GCP."""


def test_travel_agent_config():
    from src.agents.travel_agent import travel_agent
    assert travel_agent.name == "travel_agent"
    assert len(travel_agent.tools) == 2
    assert "gemini" in travel_agent.model.lower()


def test_expense_agent_config():
    from src.agents.expense_agent import expense_agent
    assert expense_agent.name == "expense_agent"
    assert len(expense_agent.tools) == 1
    assert "gemini" in expense_agent.model.lower()


def test_coordinator_agent_config():
    from src.agents.coordinator_agent import coordinator_agent
    assert coordinator_agent.name == "coordinator_agent"
    assert len(coordinator_agent.tools) >= 1
    assert len(coordinator_agent.sub_agents) == 2


def test_coordinator_has_sub_agents():
    from src.agents.coordinator_agent import coordinator_agent
    sub_names = [a.name for a in coordinator_agent.sub_agents]
    assert "travel_agent" in sub_names
    assert "expense_agent" in sub_names
