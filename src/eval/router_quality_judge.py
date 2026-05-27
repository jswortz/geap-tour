"""LLM-as-judge: single-call comparative rubric across all routed-model responses.

The judge sees all responses anonymized (A, B, C, ...) with order shuffled per
call to mitigate ordering bias. It does NOT see model names. Rubric is 4 dims,
each 1-5, normalized to an overall 1-5 score.
"""

import asyncio
import json
import random
import string
import time
from dataclasses import dataclass, field
from typing import Optional

from google import genai
from google.genai.types import GenerateContentConfig

from src.config import GCP_PROJECT_ID, PRO_MODEL

JUDGE_LOCATION = "global"
JUDGE_MAX_OUTPUT_TOKENS = 8192  # bumped — thinking models eat output tokens on reasoning
JUDGE_FALLBACK_MODEL = "gemini-2.5-pro"  # non-thinking; retry target on empty/incomplete response
JUDGE_TIMEOUT_S = 120.0
JUDGE_TEMPERATURE = 0.0
RUBRIC_DIMS = ("plan_completeness", "correctness", "reasoning_clarity", "tool_awareness")

JUDGE_SYSTEM_INSTRUCTION = (
    "You are a strict but fair evaluator of corporate travel/expense assistant responses. "
    "Score each candidate response on 4 dimensions, each on an integer 1-5 scale.\n\n"
    "Dimensions:\n"
    "- plan_completeness: Does the response cover ALL sub-tasks/intents in the prompt? "
    "(1=missing most, 5=covers everything)\n"
    "- correctness: Is the plan factually right? No hallucinated tools, policies, or steps. "
    "(1=many errors, 5=no errors)\n"
    "- reasoning_clarity: Is the response well-structured, traceable, and easy to follow? "
    "(1=incoherent, 5=crystal clear)\n"
    "- tool_awareness: Does it name appropriate tools (search_flights, search_hotels, "
    "check_policy, submit_expense, book_flight) without inventing tools? (1=no tools/wrong tools, 5=perfect)\n\n"
    "Return STRICT JSON only — no preamble, no markdown fences. Schema:\n"
    '{"scores": {"<label>": {"plan_completeness": int, "correctness": int, '
    '"reasoning_clarity": int, "tool_awareness": int, "notes": "<one sentence>"}, ...}}'
)

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "plan_completeness": {"type": "integer", "minimum": 1, "maximum": 5},
                    "correctness": {"type": "integer", "minimum": 1, "maximum": 5},
                    "reasoning_clarity": {"type": "integer", "minimum": 1, "maximum": 5},
                    "tool_awareness": {"type": "integer", "minimum": 1, "maximum": 5},
                    "notes": {"type": "string"},
                },
                "required": ["plan_completeness", "correctness", "reasoning_clarity", "tool_awareness"],
            },
        },
    },
    "required": ["scores"],
}


@dataclass
class JudgeScore:
    model: str
    plan_completeness: int
    correctness: int
    reasoning_clarity: int
    tool_awareness: int
    overall: float
    notes: str = ""
    latency_ms: float = 0.0
    error: Optional[str] = None
    label: str = ""

    @classmethod
    def empty(cls, model: str, error: str) -> "JudgeScore":
        return cls(
            model=model,
            plan_completeness=0,
            correctness=0,
            reasoning_clarity=0,
            tool_awareness=0,
            overall=0.0,
            error=error,
        )


def _make_labels(n: int) -> list[str]:
    return list(string.ascii_uppercase[:n])


def _build_user_prompt(prompt: str, labelled_responses: list[tuple[str, str]]) -> str:
    parts = [f"USER PROMPT:\n{prompt}\n\nCANDIDATE RESPONSES:"]
    for label, text in labelled_responses:
        snippet = (text or "(empty)").strip()
        parts.append(f"\n--- Response {label} ---\n{snippet}")
    parts.append(
        "\n\nReturn JSON with one entry per label. The label keys MUST be exactly: "
        + ", ".join(label for label, _ in labelled_responses)
        + "."
    )
    return "\n".join(parts)


def _overall(dim_scores: dict) -> float:
    vals = [dim_scores[d] for d in RUBRIC_DIMS]
    return round(sum(vals) / len(vals), 3)


async def _judge_call(
    judge_model: str, prompt: str, labelled_responses: list[tuple[str, str]]
) -> tuple[dict, float]:
    client = genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=JUDGE_LOCATION)
    t0 = time.monotonic()
    response = await asyncio.wait_for(
        client.aio.models.generate_content(
            model=judge_model,
            contents=_build_user_prompt(prompt, labelled_responses),
            config=GenerateContentConfig(
                system_instruction=JUDGE_SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=RESPONSE_SCHEMA,
                max_output_tokens=JUDGE_MAX_OUTPUT_TOKENS,
                temperature=JUDGE_TEMPERATURE,
            ),
        ),
        timeout=JUDGE_TIMEOUT_S,
    )
    latency_ms = (time.monotonic() - t0) * 1000
    text = response.text
    if not text:
        raise ValueError("judge returned empty response")
    data = json.loads(text)
    return data, latency_ms


async def judge_responses(
    prompt: str,
    model_to_response: dict[str, str],
    judge_model: str = PRO_MODEL,
) -> dict[str, JudgeScore]:
    """Score all model responses for one prompt in a single comparative judge call.

    Anonymizes responses (A, B, C, ...) and shuffles order per call.
    Falls back to JudgeScore.empty(...) entries on parse failure (not raised).
    """
    models = list(model_to_response.keys())
    if not models:
        return {}

    pairs = list(model_to_response.items())
    random.shuffle(pairs)
    labels = _make_labels(len(pairs))
    label_to_model = {label: model for label, (model, _) in zip(labels, pairs)}
    labelled = [(label, text) for label, (_, text) in zip(labels, pairs)]

    expected_labels = set(label_to_model.keys())

    async def _attempt(jm: str) -> tuple[dict | None, float, BaseException | None]:
        try:
            d, lat = await _judge_call(jm, prompt, labelled)
            return d, lat, None
        except BaseException as exc:
            return None, 0.0, exc

    last_exc: Optional[BaseException] = None
    data, latency_ms = None, 0.0
    # First try: primary judge model
    data, latency_ms, exc = await _attempt(judge_model)
    if data is None or set((data.get("scores") or {}).keys()) < expected_labels:
        last_exc = exc
        await asyncio.sleep(2.0)
        # Fallback: try non-thinking judge (gemini-2.5-pro), which is more reliable for structured output
        fallback_model = JUDGE_FALLBACK_MODEL if judge_model != JUDGE_FALLBACK_MODEL else judge_model
        data2, latency2, exc2 = await _attempt(fallback_model)
        if data2 is not None and (data is None or set(data2.get("scores", {}).keys()) >= set((data or {}).get("scores", {}).keys())):
            data, latency_ms = data2, latency2
        elif exc2 is not None:
            last_exc = exc2

    if data is None:
        return {
            model: JudgeScore.empty(model, error=f"judge failed: {type(last_exc).__name__}: {last_exc}")
            for model in models
        }

    scores = data.get("scores", {})
    results: dict[str, JudgeScore] = {}
    for label, model in label_to_model.items():
        entry = scores.get(label)
        if not entry:
            results[model] = JudgeScore.empty(model, error=f"judge omitted label {label}")
            continue
        try:
            dim_vals = {d: int(entry[d]) for d in RUBRIC_DIMS}
            for d, v in dim_vals.items():
                if not 1 <= v <= 5:
                    raise ValueError(f"{d}={v} out of range [1,5]")
            results[model] = JudgeScore(
                model=model,
                **dim_vals,
                overall=_overall(dim_vals),
                notes=entry.get("notes", ""),
                latency_ms=round(latency_ms, 1),
                label=label,
            )
        except (KeyError, ValueError, TypeError) as exc:
            results[model] = JudgeScore.empty(model, error=f"parse error: {exc}")
    return results
