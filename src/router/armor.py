"""Router-local armor config — self-contained for Agent Runtime deployment."""

import os
import re

from google.genai.types import GenerateContentConfig, ModelArmorConfig

from src.config import GCP_PROJECT_ID, GCP_REGION


def get_model_armor_config() -> ModelArmorConfig:
    prompt_template = os.environ.get(
        "MODEL_ARMOR_PROMPT_TEMPLATE",
        f"projects/{GCP_PROJECT_ID}/locations/{GCP_REGION}/templates/geap-workshop-prompt",
    )
    response_template = os.environ.get(
        "MODEL_ARMOR_RESPONSE_TEMPLATE",
        f"projects/{GCP_PROJECT_ID}/locations/{GCP_REGION}/templates/geap-workshop-response",
    )
    return ModelArmorConfig(
        prompt_template_name=prompt_template,
        response_template_name=response_template,
    )


def get_armored_generate_config() -> GenerateContentConfig:
    return GenerateContentConfig(model_armor_config=get_model_armor_config())


MAX_INPUT_LENGTH = 4000

BLOCKED_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\s*/?script", re.IGNORECASE),
]

REJECTION_MESSAGE = "I'm sorry, I can't process that request. Please rephrase your question about travel or expenses."


def input_guardrail_callback(context):
    from google.genai.types import Content, Part

    user_message = ""
    if context.user_content:
        if isinstance(context.user_content, Content):
            for part in context.user_content.parts or []:
                if part.text:
                    user_message += part.text
        elif isinstance(context.user_content, str):
            user_message = context.user_content

    if not user_message:
        return None

    if len(user_message) > MAX_INPUT_LENGTH:
        return Content(parts=[Part(text=f"Input too long ({len(user_message)} chars, max {MAX_INPUT_LENGTH}). Please shorten your request.")])

    for pattern in BLOCKED_PATTERNS:
        if pattern.search(user_message):
            return Content(parts=[Part(text=REJECTION_MESSAGE)])

    return None
