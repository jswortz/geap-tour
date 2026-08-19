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

import os

from google.adk.models.lite_llm import LiteLlm


def resolve_model(model_str: str):
    """Resolve a model string to what ADK's ``LlmAgent`` expects.

    - Gemini 2.x / ``models/*`` — regional; pass through as plain strings.
    - Gemini 3.x — served only on the **global** endpoint. Use the NATIVE Gemini path pinned
      to global via ``client_kwargs`` (per-model, so the engine's region is untouched). NOT
      LiteLLM: its Vertex adapter mangles Gemini-3 thought signatures into bogus function
      calls, so tool-using agents never produce a real answer.
    - Claude (and anything else) — LiteLlm at ``vertex_location="global"``.
    """
    if model_str.startswith(("gemini-2", "models/")):
        return model_str
    if model_str.startswith("gemini-"):
        from google.adk.models.google_llm import Gemini
        client_kwargs = {"vertexai": True, "location": "global"}
        # Prefer GCP_PROJECT_ID (set from .env) over the ambient GOOGLE_CLOUD_PROJECT, which on
        # some dev machines points at a different project and would be baked into the deployed agent.
        proj = os.environ.get("GCP_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
        if proj:
            client_kwargs["project"] = proj
        return Gemini(model=model_str, client_kwargs=client_kwargs)
    if not model_str.startswith("vertex_ai/"):
        model_str = f"vertex_ai/{model_str}"
    return LiteLlm(model=model_str, vertex_location="global")
