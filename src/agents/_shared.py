"""Shared helpers for the full-repo ADK agents (coordinator + travel + expense).

These three agents are always deployed together as part of the coordinator, which
ships the whole ``src`` tree (``deploy_agents.py`` uses ``extra_packages=["src"]``),
so they can share code freely from ``src``.

The **standalone** deploy targets deliberately do NOT import from here — they are
packaged on their own (``adk deploy agent_engine src/router`` /
``src/agents/coordinator``, each with its own ``requirements.txt``; Cloud Run
``--source app`` for ``app/``), so each keeps its own copy of these helpers on
purpose. Keep that duplication when editing — it is deployment isolation, not an
oversight.
"""

from google.adk.models.lite_llm import LiteLlm


def resolve_model(model_str: str):
    """Resolve a model string to what ADK's ``LlmAgent`` expects.

    Gemini 2.x / ``models/*`` are passed through as plain strings. Everything else
    (Gemini 3.x and Claude on Vertex) is wrapped in ``LiteLlm`` with
    ``vertex_location="global"``, which those model families require.
    """
    if model_str.startswith(("gemini-2", "models/")):
        return model_str
    if not model_str.startswith("vertex_ai/"):
        model_str = f"vertex_ai/{model_str}"
    return LiteLlm(model=model_str, vertex_location="global")
