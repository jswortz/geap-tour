"""Prompt complexity classifier using Gemini Flash Lite as a micro-judge.

Classifies prompts into 5 tiers for multi-model routing:
  low → medium_low → medium → medium_high → high
"""

import json
from dataclasses import dataclass

from google import genai
from google.genai.types import GenerateContentConfig

from .config import GCP_PROJECT_ID, GCP_REGION

CLASSIFIER_PROMPT_TEMPLATE = (
    "Rate the complexity of this user prompt on a 0-1 scale.\n\n"
    "Criteria:\n"
    "- 0.0-0.19: Trivial — a single read-only lookup with no reasoning "
    '(e.g. "what is the meal limit?", "find hotels in Miami", "show expenses for EMP001")\n'
    "- 0.20-0.39: Simple — a single action (booking, submission) or a lookup with formatting/sorting "
    '(e.g. "book flight FL001 for Alice", "submit a $30 expense", "find flights and show cheapest")\n'
    "- 0.40-0.59: Moderate — 2 distinct tool calls or comparison across multiple results "
    '(e.g. "find flights to NYC and compare by airline", "search hotels then check lodging policy")\n'
    "- 0.60-0.79: Complex — 3+ tool calls across different domains, or structured multi-factor analysis "
    '(e.g. "compare flights on two routes plus hotels and meal costs in each city")\n'
    "- 0.80-1.0: Expert — multi-step planning for a group/trip, budget optimization, or strategic synthesis "
    '(e.g. "plan a 5-day trip for a team of 4 with flights, hotels, and expense policies")\n\n'
    "Scoring guidance:\n"
    "- Any booking or submission action is at least 0.20.\n"
    "- Any comparison across options is at least 0.40.\n"
    "- Mentioning 3+ distinct tasks or cross-domain analysis is at least 0.60.\n"
    "- Team planning, budget constraints, or multi-city optimization is at least 0.80.\n\n"
    'Return JSON with keys "score" (float) and "reason" (one sentence).\n\n'
    "Prompt: {prompt}"
)


@dataclass
class ComplexityResult:
    level: str
    score: float
    reason: str


THRESHOLDS = [0.20, 0.40, 0.60, 0.80]
LEVELS = ["low", "medium_low", "medium", "medium_high", "high"]


def _score_to_level(score: float) -> str:
    for threshold, level in zip(THRESHOLDS, LEVELS):
        if score < threshold:
            return level
    return LEVELS[-1]


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
        model="gemini-2.5-flash-lite",
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
