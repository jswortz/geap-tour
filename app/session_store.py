"""In-memory per-session accrual store for the Router Cost Visualizer.

Gemini Enterprise reuses one ``contextId`` per chat session, and every turn hits this Cloud Run
service. We key a live ``Accrual`` by that contextId so cost/routing accumulate across the prompts the
user actually sends. Deploy pinned to a single instance (``--min-instances=1 --max-instances=1``) so
all turns of a session land on the same process memory.

Caveat: this state is per-instance and ephemeral — it is lost on redeploy or instance recycle. That is
acceptable for a live demo; the durable upgrade would be Firestore keyed by contextId.
"""
from __future__ import annotations

from typing import Dict

from app.cost_model import Accrual

_SESSIONS: Dict[str, Accrual] = {}


def get(context_id: str) -> Accrual:
    """Return the session's accrual, creating an empty one on first use."""
    key = context_id or "_default"
    acc = _SESSIONS.get(key)
    if acc is None:
        acc = Accrual()
        _SESSIONS[key] = acc
    return acc


def reset(context_id: str) -> Accrual:
    """Clear the session's accrual and return a fresh one."""
    key = context_id or "_default"
    acc = Accrual()
    _SESSIONS[key] = acc
    return acc
