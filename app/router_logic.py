"""Live per-prompt routing + real model execution for the Router Cost Visualizer.

Async and self-contained (no ``src.*`` / ADK imports) so the Cloud Run image stays lean. Mirrors the
validated dual-client pattern in ``src/eval/router_inference.py`` and the classifier in
``src/router/complexity.py``:

  * Gemini tiers (lite / flash / pro) + the complexity classifier  → ``google-genai`` (Vertex,
    location="global"); real usage from ``usage_metadata`` (candidates_token_count already includes
    Gemini 3.x thinking tokens).
  * Claude tiers (sonnet / opus)  → ``AsyncAnthropicVertex`` (Vertex Model Garden, region="global"),
    pure GCP ADC (no API key); real usage from ``msg.usage.input_tokens / output_tokens``.

Every prompt is actually classified AND the routed tier model is actually invoked, so tokens and cost
are measured, not estimated. The all-Opus baseline is priced at Opus rates on the SAME real token
counts (we never call Opus just for the baseline).
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Tuple

from google import genai
from google.genai.types import GenerateContentConfig

from app.cost_model import BASELINE_MODEL, estimate_cost

GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "wortz-project-352116")
# Gemini 3.x and Claude on Vertex are only served from location=global.
VERTEX_LOCATION = os.environ.get("CLASSIFIER_LOCATION", "global")

def _norm(model: str) -> str:
    """Bare Vertex model id — strip a litellm-style ``vertex_ai/`` prefix if present."""
    return model[len("vertex_ai/"):] if model.startswith("vertex_ai/") else model


# Tier model ids — mirror src/router/config.py (normalized to bare Vertex ids).
LITE_MODEL = _norm(os.environ.get("LITE_MODEL", "gemini-3.1-flash-lite"))
FLASH_MODEL = _norm(os.environ.get("FLASH_MODEL", "gemini-3.5-flash"))
PRO_MODEL = _norm(os.environ.get("PRO_MODEL", "gemini-2.5-pro"))
SONNET_MODEL = _norm(os.environ.get("SONNET_MODEL", "claude-sonnet-4-5"))
OPUS_MODEL = _norm(os.environ.get("OPUS_MODEL", "claude-opus-4-6"))
CLASSIFIER_MODEL = _norm(os.environ.get("CLASSIFIER_MODEL", "gemini-3.5-flash"))

TIER_MODEL = {
    "lite": LITE_MODEL,
    "flash": FLASH_MODEL,
    "sonnet": SONNET_MODEL,
    "pro": PRO_MODEL,
    "opus": OPUS_MODEL,
}
TIER_LABEL = {"lite": "Lite", "flash": "Flash", "sonnet": "Sonnet", "pro": "Pro", "opus": "Opus"}

# Within-tier model-selection boundaries (mirror src/router/complexity.py).
THRESHOLDS = {"lite": 0.30, "flash": 0.45, "sonnet": 0.60, "pro": 0.80}  # else -> opus

DEFAULT_TIMEOUT_S = float(os.environ.get("ROUTER_MODEL_TIMEOUT_S", "45"))
ANSWER_MAX_TOKENS = int(os.environ.get("ROUTER_ANSWER_MAX_TOKENS", "1024"))
RETRY_ON = ("429", "503", "timeout", "deadline", "unavailable", "resource exhausted")

ANSWER_SYSTEM_INSTRUCTION = (
    "You are a corporate travel & expense assistant. Answer the user's request concisely and "
    "helpfully. If a request would require live booking/search tools you don't have, give the best "
    "structured answer you can and note any assumptions."
)

# Classifier prompt + schema — copied verbatim from src/router/complexity.py.
CLASSIFIER_PROMPT_TEMPLATE = (
    "Rate the complexity of this user prompt on a 0-1 scale.\n\n"
    "Criteria:\n"
    "- 0.0-0.29: Simple — single intent, direct lookup, one tool call, or a single action "
    '(e.g. "what is the meal limit?", "find hotels in Miami", "book flight FL001")\n'
    "- 0.30-0.59: Moderate — 2 related intents, comparison across options, or multi-step lookup "
    '(e.g. "compare flights by airline", "search hotels then check policy", "check two policy categories")\n'
    "- 0.60-1.0: Complex — 3+ intents, cross-domain analysis, multi-step planning, "
    "budget optimization, or strategic synthesis "
    '(e.g. "plan a multi-city trip with budget constraints", "review expenses and submit new ones")\n\n'
    "Scoring guidance:\n"
    "- Single lookups and simple bookings: 0.0–0.29.\n"
    "- Any comparison or 2-tool task: 0.30–0.59.\n"
    "- 3+ distinct tasks or cross-domain analysis: 0.60–0.79.\n"
    "- Team planning, budget optimization, or multi-city trips: 0.80–1.0.\n\n"
    'Return JSON with keys "score" (float) and "reason" (one sentence).\n\n'
    "Prompt: {prompt}"
)
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"score": {"type": "number"}, "reason": {"type": "string"}},
    "required": ["score", "reason"],
}

# Lazy module-singleton clients — created once per warm instance (avoids per-request re-auth and
# never blocks the event loop with sync construction inside the request path).
_genai_client = None
_anthropic_client = None


def _genai_c():
    global _genai_client
    if _genai_client is None:
        _genai_client = genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=VERTEX_LOCATION)
    return _genai_client


def _anthropic_c():
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import AsyncAnthropicVertex

        _anthropic_client = AsyncAnthropicVertex(project_id=GCP_PROJECT_ID, region=VERTEX_LOCATION)
    return _anthropic_client


def score_to_tier(score: float) -> str:
    """Map a 0-1 complexity score to a tier key. Mirrors complexity.score_to_model_tier."""
    if score < THRESHOLDS["lite"]:
        return "lite"
    if score < THRESHOLDS["flash"]:
        return "flash"
    if score < THRESHOLDS["sonnet"]:
        return "sonnet"
    if score < THRESHOLDS["pro"]:
        return "pro"
    return "opus"


def _retryable(exc: BaseException) -> bool:
    m = str(exc).lower()
    return any(s in m for s in RETRY_ON)


async def classify(prompt: str) -> dict:
    """Real complexity classification via the Flash-Lite/Flash classifier. Returns score+reason+usage."""
    resp = await _genai_c().aio.models.generate_content(
        model=CLASSIFIER_MODEL,
        contents=CLASSIFIER_PROMPT_TEMPLATE.format(prompt=prompt),
        config=GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
            max_output_tokens=2048,  # 3.x thinking models spend output tokens on reasoning
            temperature=0.0,
        ),
    )
    u = getattr(resp, "usage_metadata", None)
    ci = int(getattr(u, "prompt_token_count", 0) or 0) if u else 0
    co = int(getattr(u, "candidates_token_count", 0) or 0) if u else 0
    text = resp.text
    if not text:
        return {"score": 0.1, "reason": "classifier returned empty response",
                "classifier_in": ci, "classifier_out": co}
    data = json.loads(text)
    score = max(0.0, min(1.0, float(data["score"])))
    return {"score": score, "reason": data.get("reason", ""), "classifier_in": ci, "classifier_out": co}


async def _run_gemini(model: str, prompt: str) -> Tuple[str, int, int]:
    resp = await _genai_c().aio.models.generate_content(
        model=model,
        contents=prompt,
        config=GenerateContentConfig(
            system_instruction=ANSWER_SYSTEM_INSTRUCTION,
            max_output_tokens=ANSWER_MAX_TOKENS,
            temperature=0.2,
        ),
    )
    u = getattr(resp, "usage_metadata", None)
    i = int(getattr(u, "prompt_token_count", 0) or 0) if u else 0
    o = int(getattr(u, "candidates_token_count", 0) or 0) if u else 0  # includes 3.x thinking tokens
    return (resp.text or ""), i, o


async def _run_claude(model: str, prompt: str) -> Tuple[str, int, int]:
    msg = await _anthropic_c().messages.create(
        model=model,
        max_tokens=ANSWER_MAX_TOKENS,
        temperature=0.2,
        system=ANSWER_SYSTEM_INSTRUCTION,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    return text, int(msg.usage.input_tokens), int(msg.usage.output_tokens)


async def _invoke(model: str, prompt: str) -> Tuple[str, int, int]:
    coro = _run_gemini(model, prompt) if model.startswith("gemini") else _run_claude(model, prompt)
    return await asyncio.wait_for(coro, timeout=DEFAULT_TIMEOUT_S)


async def route_and_run(prompt: str) -> dict:
    """Classify the prompt, route to a tier, ACTUALLY invoke that model, and price the result.

    Returns a dict consumed by app.cost_model.Accrual.add() and the UI builder. Never raises — on a
    model error it returns a step with zero tokens/cost and an ``error`` string so the A2A task still
    completes and the canvas renders.
    """
    t0 = time.monotonic()
    c = await classify(prompt)
    tier = score_to_tier(c["score"])
    model = TIER_MODEL[tier]

    answer, i, o, err = "", 0, 0, ""
    attempts = 0
    while attempts < 2:
        attempts += 1
        try:
            answer, i, o = await _invoke(model, prompt)
            break
        except BaseException as exc:  # noqa: BLE001 — never fail the A2A task
            err = f"{type(exc).__name__}: {exc}"
            if attempts < 2 and _retryable(exc):
                await asyncio.sleep(2.0)
                err = ""
                continue
            break

    classifier_cost = estimate_cost("classifier", c["classifier_in"], c["classifier_out"])
    cost = estimate_cost(model, i, o) + classifier_cost
    baseline_cost = estimate_cost(BASELINE_MODEL, i, o)  # all-Opus on the SAME real tokens
    return {
        "score": c["score"],
        "reason": c["reason"],
        "tier": tier,
        "tier_label": TIER_LABEL[tier],
        "model": model,
        "answer": answer,
        "input_tokens": i,
        "output_tokens": o,
        "classifier_in": c["classifier_in"],
        "classifier_out": c["classifier_out"],
        "cost": cost,
        "baseline_cost": baseline_cost,
        "latency_ms": round((time.monotonic() - t0) * 1000, 1),
        "error": err,
    }
