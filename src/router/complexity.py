"""Prompt complexity classifier using a lightweight model as a micro-judge.

Classifies prompts into 3 logical tiers, with score-based model selection
within the medium and high tiers:

  low    (0.0–0.30)  → LITE_MODEL
  medium (0.30–0.60) → FLASH_MODEL (0.30–0.45) or SONNET_MODEL (0.45–0.60)
  high   (0.60–1.0)  → PRO_MODEL (0.60–0.80) or OPUS_MODEL (0.80–1.0)
"""

import json
from dataclasses import dataclass

from google import genai
from google.genai.types import GenerateContentConfig

from .config import GCP_PROJECT_ID, GCP_REGION, CLASSIFIER_MODEL

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


@dataclass
class ComplexityResult:
    level: str
    score: float
    reason: str


# 3 logical tiers with sub-tiers for model selection
THRESHOLDS = [0.30, 0.60]
LEVELS = ["low", "medium", "high"]

# Within-tier model selection boundaries
MEDIUM_SPLIT = 0.45  # below → FLASH_MODEL, above → SONNET_MODEL
HIGH_SPLIT = 0.80    # below → PRO_MODEL, above → OPUS_MODEL


def _score_to_level(score: float) -> str:
    for threshold, level in zip(THRESHOLDS, LEVELS):
        if score < threshold:
            return level
    return LEVELS[-1]


def score_to_model_tier(score: float) -> str:
    """Map a complexity score to a specific model tier for routing.

    Returns one of: 'lite', 'flash', 'sonnet', 'pro', 'opus'
    """
    if score < 0.30:
        return "lite"
    elif score < MEDIUM_SPLIT:
        return "flash"
    elif score < 0.60:
        return "sonnet"
    elif score < HIGH_SPLIT:
        return "pro"
    else:
        return "opus"


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
        model=CLASSIFIER_MODEL,
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
