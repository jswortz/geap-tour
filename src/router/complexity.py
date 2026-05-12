"""Prompt complexity classifier using Gemini Flash Lite as a micro-judge."""

import json
from dataclasses import dataclass

from google import genai
from google.genai.types import GenerateContentConfig

from src.config import GCP_PROJECT_ID, GCP_REGION, COMPLEXITY_THRESHOLD_HIGH

CLASSIFIER_PROMPT_TEMPLATE = (
    "Rate the complexity of this user prompt on a 0-1 scale.\n\n"
    "Criteria:\n"
    "- 0.0-0.2: Single intent, direct lookup, one tool call "
    '(e.g. "find flights to NYC", "what is the meal limit?", "book flight FL001")\n'
    "- 0.3-0.5: Moderate reasoning or exactly 2 related intents "
    '(e.g. "compare hotels in two cities", "check history and flag issues")\n'
    "- 0.6-1.0: Multi-step planning, cross-domain analysis, 3+ intents, "
    "requires synthesizing information from multiple sources\n\n"
    "Be conservative: if a prompt has only ONE clear action, score it below 0.3. "
    "Only score above 0.6 if the prompt explicitly requires 3+ distinct steps.\n\n"
    'Return JSON with keys "score" (float) and "reason" (one sentence).\n\n'
    "Prompt: {prompt}"
)


@dataclass
class ComplexityResult:
    level: str  # "low", "medium", "high"
    score: float
    reason: str


COMPLEXITY_THRESHOLD_MEDIUM = 0.35


def _score_to_level(score: float) -> str:
    if score >= COMPLEXITY_THRESHOLD_HIGH:
        return "high"
    if score >= COMPLEXITY_THRESHOLD_MEDIUM:
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
