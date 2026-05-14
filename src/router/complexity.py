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
    "- 0.0-0.19: Trivial — single intent, direct lookup, one tool call "
    '(e.g. "what is the meal limit?", "find hotels in Miami")\n'
    "- 0.20-0.39: Simple — single intent with light reasoning or formatting "
    '(e.g. "search flights and show cheapest", "submit a $30 expense")\n'
    "- 0.40-0.59: Moderate — 2 related intents or comparison requiring reasoning "
    '(e.g. "compare hotels in two cities and check policy", "book flight and submit expense")\n'
    "- 0.60-0.79: Complex — 3+ intents, cross-domain analysis, structured output "
    '(e.g. "review expense history, check policies, and submit a new one")\n'
    "- 0.80-1.0: Expert — multi-step planning, budget optimization, synthesis "
    "across many sources, strategic recommendations "
    '(e.g. "plan a multi-city trip for a team with budget constraints")\n\n'
    "Be conservative: single-action prompts should score below 0.20. "
    "Only score above 0.80 if the prompt requires 4+ distinct steps with synthesis.\n\n"
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
