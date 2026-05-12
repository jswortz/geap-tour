"""GEAP Coordinator Agent — self-contained module for ADK CLI deployment.

Integrates Vertex AI Agent Engine Memory Bank so the agent remembers user
interactions (past bookings, expense submissions, preferences) across sessions.
"""

import os
import re

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools import McpToolset
from google.adk.tools.mcp_tool.mcp_toolset import StreamableHTTPConnectionParams
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai.types import GenerateContentConfig, ModelArmorConfig, Content, Part

AGENT_MODEL = os.environ.get("AGENT_MODEL", "gemini-2.0-flash")
SEARCH_MCP_URL = os.environ.get("SEARCH_MCP_URL", "https://search-mcp-in2bk2mdwa-uc.a.run.app/mcp")
BOOKING_MCP_URL = os.environ.get("BOOKING_MCP_URL", "https://booking-mcp-in2bk2mdwa-uc.a.run.app/mcp")
EXPENSE_MCP_URL = os.environ.get("EXPENSE_MCP_URL", "https://expense-mcp-in2bk2mdwa-uc.a.run.app/mcp")

GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "wortz-project-352116")
GCP_REGION = os.environ.get("GCP_REGION", "us-central1")
AGENT_ENGINE_ID = os.environ.get("AGENT_ENGINE_ID", "1316648131831529472")

PROMPT_TEMPLATE = os.environ.get(
    "MODEL_ARMOR_PROMPT_TEMPLATE",
    f"projects/{GCP_PROJECT_ID}/locations/{GCP_REGION}/templates/geap-workshop-prompt",
)
RESPONSE_TEMPLATE = os.environ.get(
    "MODEL_ARMOR_RESPONSE_TEMPLATE",
    f"projects/{GCP_PROJECT_ID}/locations/{GCP_REGION}/templates/geap-workshop-response",
)

generate_config = GenerateContentConfig(
    model_armor_config=ModelArmorConfig(
        prompt_template_name=PROMPT_TEMPLATE,
        response_template_name=RESPONSE_TEMPLATE,
    ),
)

MAX_INPUT_LENGTH = 4000
BLOCKED_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\s*/?script", re.IGNORECASE),
]


def input_guardrail_callback(context):
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
        return Content(parts=[Part(text=f"Input too long ({len(user_message)} chars, max {MAX_INPUT_LENGTH}).")])
    for pattern in BLOCKED_PATTERNS:
        if pattern.search(user_message):
            return Content(parts=[Part(text="I'm sorry, I can't process that request.")])
    return None


travel_agent = LlmAgent(
    model=AGENT_MODEL,
    name="travel_agent",
    instruction="""\
You are a corporate travel assistant. Help employees search for and book flights and hotels.
When a user asks about travel:
1. Use the search tools to find available flights or hotels.
2. Present the options clearly with prices, times, and ratings.
3. When the user chooses, use the booking tools to confirm.
If the user asks about expenses, let them know to ask the expense assistant.""",
    tools=[
        McpToolset(connection_params=StreamableHTTPConnectionParams(url=SEARCH_MCP_URL)),
        McpToolset(connection_params=StreamableHTTPConnectionParams(url=BOOKING_MCP_URL)),
    ],
    generate_content_config=generate_config,
    before_agent_callback=input_guardrail_callback,
)

expense_agent = LlmAgent(
    model=AGENT_MODEL,
    name="expense_agent",
    instruction="""\
You are a corporate expense management assistant. Help employees submit expense reports and check policies.
Policy limits: meals ($75), transport ($200), lodging ($400), supplies ($100), entertainment ($150).
1. Check policy first with check_expense_policy.
2. Submit expenses with submit_expense.
3. View history with get_user_expenses.
If the user asks about travel, direct them to the travel assistant.""",
    tools=[
        McpToolset(connection_params=StreamableHTTPConnectionParams(url=EXPENSE_MCP_URL)),
    ],
    generate_content_config=generate_config,
    before_agent_callback=input_guardrail_callback,
)

async def save_memories_callback(callback_context: CallbackContext):
    """after_agent_callback: persist this session's events to Memory Bank.

    Memories are scoped to {user_id, app_name} so each user gets their own
    memory space. The agent can recall past bookings, expenses, and preferences.
    """
    await callback_context.add_session_to_memory()
    return None


root_agent = LlmAgent(
    model=AGENT_MODEL,
    name="coordinator_agent",
    instruction="""\
You are a corporate assistant coordinator. Route requests to the right specialist:
- Flight/hotel search and booking → delegate to travel_agent
- Expense submission, policy checks → delegate to expense_agent
- General travel info → use search tools directly

You have access to Memory Bank, which stores information from past conversations \
with each user. Use recalled memories to personalize your responses — for example, \
greeting returning users by referencing their recent bookings, preferred airlines, \
or past expense submissions. If a user asks "what did I book last time?" or \
similar, the memory tool will have that context.

Greet the user and ask how you can help if intent is unclear.""",
    tools=[
        McpToolset(connection_params=StreamableHTTPConnectionParams(url=SEARCH_MCP_URL)),
        # PreloadMemoryTool retrieves relevant memories at the start of each
        # turn and injects them into the system instruction.
        PreloadMemoryTool(),
    ],
    sub_agents=[travel_agent, expense_agent],
    generate_content_config=generate_config,
    before_agent_callback=input_guardrail_callback,
    after_agent_callback=save_memories_callback,
)
