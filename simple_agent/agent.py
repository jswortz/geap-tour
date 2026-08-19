"""Minimal, self-contained ADK agent for the GEAP platform tutorial notebook.

Deployable to Vertex AI Agent Engine via ``agent_engines.create(agent=root_agent,
config={... "extra_packages": ["simple_agent"] ...})`` with NO dependency on the repo's
``src`` tree or MCP servers — so the tutorial's end-to-end run has few failure modes.

Key platform patterns demonstrated by this agent:
- **Gemini 3.x** on the **global** endpoint via the NATIVE ADK Gemini path
  (``Gemini(model=..., client_kwargs={"vertexai":True,"location":"global",...})``).
  LiteLLM is deliberately NOT used — its Vertex adapter mangles Gemini-3 *thought
  signatures* into bogus function calls, so tool-using agents never answer.
- **User-scoped Memory Bank**: ``PreloadMemoryTool`` recalls the current user's memories
  each turn, and ``after_agent_callback`` persists the session back to Memory Bank. The
  Agent Engine runtime auto-wires ``VertexAiMemoryBankService`` at its own engine id, and
  memory scope is ``{app_name, user_id}`` — i.e. per USER, across their sessions.
"""

import os
from datetime import datetime, timezone

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.google_llm import Gemini
from google.adk.tools.preload_memory_tool import PreloadMemoryTool

AGENT_MODEL = os.environ.get("AGENT_MODEL", "gemini-3.7-flash")


def _model():
    """Native Gemini pinned to the global endpoint (Gemini 3.x is global-only).

    Prefer GCP_PROJECT_ID (set from .env) over the ambient GOOGLE_CLOUD_PROJECT so a dev
    machine's ambient project isn't baked into the deployed agent.
    """
    if AGENT_MODEL.startswith(("gemini-2", "models/")):
        return AGENT_MODEL  # 2.x is regional — plain string is fine
    client_kwargs = {"vertexai": True, "location": "global"}
    proj = os.environ.get("GCP_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if proj:
        client_kwargs["project"] = proj
    return Gemini(model=AGENT_MODEL, client_kwargs=client_kwargs)


def get_current_time(timezone_name: str = "UTC") -> dict:
    """Return the current UTC date and time.

    Args:
        timezone_name: IANA-style label echoed back for display (e.g. 'UTC').
    Returns:
        dict with the ISO-8601 timestamp and the label.
    """
    now = datetime.now(timezone.utc)
    return {"timezone": timezone_name, "iso_time": now.isoformat(), "status": "ok"}


async def save_memories_callback(callback_context: CallbackContext):
    """after_agent_callback: persist this session to Memory Bank, scoped to the session's user."""
    try:
        await callback_context.add_session_to_memory()
    except Exception:
        # Memory service may be absent in some local contexts; never block the turn.
        pass
    return None


INSTRUCTION = (
    "You are a concise, friendly personal assistant.\n"
    "- Call the get_current_time tool whenever the user asks about the current date or time.\n"
    "- If a <PAST_CONVERSATIONS> block contains a user preference (e.g. a preferred name, home "
    "city, or seating preference), honor it and reference it naturally.\n"
    "- When a user tells you a preference to remember, acknowledge it clearly.\n"
    "Keep answers short."
)

root_agent = LlmAgent(
    model=_model(),
    name="simple_time_agent",
    instruction=INSTRUCTION,
    tools=[
        get_current_time,     # auto-wrapped in a FunctionTool by ADK
        PreloadMemoryTool(),  # injects the current user's recalled memories each turn
    ],
    after_agent_callback=save_memories_callback,
)
