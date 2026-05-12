"""ADK agent entry point for deployment via `adk deploy agent_engine`."""

from .agents import router_agent

root_agent = router_agent
