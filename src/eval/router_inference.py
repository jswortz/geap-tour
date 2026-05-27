"""Direct model inference for router benchmark — Gemini via genai SDK, Claude via LiteLLM.

Bypasses ADK/MCP to produce clean apples-to-apples latency and cost numbers
across the 5 router tiers (lite, flash, pro, sonnet, opus).
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Optional

from google import genai
from google.genai.types import GenerateContentConfig

from src.config import GCP_PROJECT_ID
from src.router.cost_tracker import estimate_cost

# Gemini 3.x and Claude on Vertex are only served from location=global.
# Gemini 2.x is regional but we use global for everything for consistency.
VERTEX_LOCATION = "global"

DEFAULT_TIMEOUT_S = 60.0
DEFAULT_MAX_OUTPUT_TOKENS = 1024
RETRY_BACKOFF_S = 2.0
RETRY_ON_SUBSTRINGS = ("429", "503", "timeout", "deadline", "unavailable")


@dataclass
class InferenceResult:
    model: str
    prompt: str
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: float
    error: Optional[str] = None


def _is_gemini(model: str) -> bool:
    return model.startswith("gemini")


def _is_retryable(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(s in msg for s in RETRY_ON_SUBSTRINGS)


async def _call_gemini(
    model: str, prompt: str, system_instruction: str, max_output_tokens: int
) -> tuple[str, int, int]:
    client = genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=VERTEX_LOCATION)
    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=GenerateContentConfig(
            system_instruction=system_instruction,
            max_output_tokens=max_output_tokens,
            temperature=0.2,
        ),
    )
    text = response.text or ""
    usage = getattr(response, "usage_metadata", None)
    # candidates_token_count already includes thinking tokens for Gemini 3.x
    in_tok = getattr(usage, "prompt_token_count", 0) if usage else 0
    out_tok = getattr(usage, "candidates_token_count", 0) if usage else 0
    return text, int(in_tok or 0), int(out_tok or 0)


async def _call_claude_via_litellm(
    model: str, prompt: str, system_instruction: str, max_output_tokens: int
) -> tuple[str, int, int]:
    from litellm import acompletion

    full_model = model if model.startswith("vertex_ai/") else f"vertex_ai/{model}"
    response = await acompletion(
        model=full_model,
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_output_tokens,
        temperature=0.2,
        vertex_project=GCP_PROJECT_ID,
        vertex_location=VERTEX_LOCATION,
    )
    text = response["choices"][0]["message"]["content"] or ""
    usage = response.get("usage", {}) if isinstance(response, dict) else getattr(response, "usage", None)
    if usage is None:
        in_tok = out_tok = 0
    elif isinstance(usage, dict):
        in_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)
    else:
        in_tok = getattr(usage, "prompt_tokens", 0)
        out_tok = getattr(usage, "completion_tokens", 0)
    return text, int(in_tok or 0), int(out_tok or 0)


async def call_model(
    model: str,
    prompt: str,
    system_instruction: str,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> InferenceResult:
    """Single-shot model call. Returns InferenceResult with error set on failure (not raised)."""
    attempts = 0
    last_exc: Optional[BaseException] = None
    while attempts < 2:
        attempts += 1
        t0 = time.monotonic()
        try:
            if _is_gemini(model):
                coro = _call_gemini(model, prompt, system_instruction, max_output_tokens)
            else:
                coro = _call_claude_via_litellm(model, prompt, system_instruction, max_output_tokens)
            text, in_tok, out_tok = await asyncio.wait_for(coro, timeout=timeout_s)
            latency_ms = (time.monotonic() - t0) * 1000
            return InferenceResult(
                model=model,
                prompt=prompt,
                text=text,
                input_tokens=in_tok,
                output_tokens=out_tok,
                latency_ms=round(latency_ms, 1),
                cost_usd=estimate_cost(model, in_tok, out_tok),
            )
        except BaseException as exc:
            last_exc = exc
            if attempts < 2 and _is_retryable(exc):
                await asyncio.sleep(RETRY_BACKOFF_S)
                continue
            break
    latency_ms = (time.monotonic() - t0) * 1000
    return InferenceResult(
        model=model,
        prompt=prompt,
        text="",
        input_tokens=0,
        output_tokens=0,
        latency_ms=round(latency_ms, 1),
        cost_usd=0.0,
        error=f"{type(last_exc).__name__}: {last_exc}",
    )


async def call_all_models(
    prompt: str,
    models: list[str],
    system_instruction: str,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> dict[str, InferenceResult]:
    """Call all models in parallel for a single prompt."""
    results = await asyncio.gather(
        *(call_model(m, prompt, system_instruction, max_output_tokens=max_output_tokens) for m in models)
    )
    return {r.model: r for r in results}
