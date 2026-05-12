"""Prompt complexity classifier using Gemini Flash Lite as a micro-judge."""

import json
from dataclasses import dataclass

from google import genai
from google.genai.types import GenerateContentConfig

from .config import GCP_PROJECT_ID, GCP_REGION, COMPLEXITY_THRESHOLD_HIGH

CLASSIFIER_PROMPT_TEMPLATE = (
    "Rate the complexity of this user prompt on a 0-1 scale.\n\n"
    "Criteria:\n"
    '- 0.0-0.3: Single intent, direct lookup (e.g. "find flights to NYC")\n'
    "- 0.4-0.6: Moderate reasoning or 2 related intents\n"
    "- 0.7-1.0: Multi-step planning, cross-domain analysis, 3+ intents\n\n"
    'Return JSON with keys "score" (float) and "reason" (one sentence).\n\n'
    "Prompt: {prompt}"
)


@dataclass
class ComplexityResult:
    level: str  # "low", "medium", "high"
    score: float
    reason: str


def _score_to_level(score: float) -> str:
    if score >= COMPLEXITY_THRESHOLD_HIGH:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"


RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["score", "reason"],
}


async def classify_complexity(prompt: str) -> ComplexityResult:
    client = genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=GCP_REGION)
    response = await client.aio.models.generate_content(
        model="gemini-2.0-flash-lite",
        contents=CLASSIFIER_PROMPT_TEMPLATE.format(prompt=prompt),
        config=GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
            max_output_tokens=80,
            temperature=0.0,
        ),
    )
    data = json.loads(response.text)
    score = max(0.0, min(1.0, float(data["score"])))
    return ComplexityResult(
        level=_score_to_level(score),
        score=score,
        reason=data.get("reason", ""),
    )
