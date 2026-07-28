"""A2A HTTP server for the GEAP Router Cost Visualizer (Cloud Run target).

Hosts the deterministic RouterCostExecutor (emits A2UI v0.8 DataParts tagged
``application/json+a2ui``) as an A2A service so Gemini Enterprise can render it in the canvas.
GE cannot invoke A2A agents on Vertex Agent Runtime, so this is served over HTTP on Cloud Run —
the proven GE + A2UI path from party-store-ge-a2ui / dg-ge-data-agent.

Card: https://<svc>/a2a/app/.well-known/agent-card.json (JSONRPC + A2UI v0.8 extension).
"""
import os

from a2a.server.apps import A2AFastAPIApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentExtension, AgentSkill
from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH
from fastapi import FastAPI
from vertexai.preview.reasoning_engines.templates.a2a import create_agent_card

from app.agent_executor import RouterCostExecutor

APP_NAME = os.getenv("A2A_APP_NAME", "app")
PORT = int(os.getenv("PORT", "8080"))
APP_URL = os.getenv(
    "APP_URL", "https://geap-router-cost-ui-679926387543.us-east1.run.app"
).rstrip("/")
RPC_PATH = f"/a2a/{APP_NAME}"
RPC_URL = f"{APP_URL}{RPC_PATH}"

A2UI_EXTENSION_URI = "https://a2ui.org/a2a-extension/a2ui/v0.8"
A2UI_CATALOG_ID = "https://a2ui.org/specification/v0_8/standard_catalog_definition.json"


def _build_agent_card():
    skill = AgentSkill(
        id="visualize_router_cost",
        name="Multi-Model Router Cost Visualizer",
        description="Visualizes how the complexity router accrues cost per prompt and the savings vs an all-frontier (all-Opus) baseline.",
        tags=["router", "cost", "finops", "multi-model", "evaluation"],
        examples=[
            "Show router cost accrual",
            "How much does the smart router save vs all-Opus?",
            "Visualize per-prompt routing cost",
        ],
    )
    card = create_agent_card(
        agent_name="GEAP Router Cost Visualizer",
        description="Shows the multi-model complexity router routing prompts to the cheapest capable tier, with a live cost-accrual chart vs an all-Opus baseline.",
        skills=[skill],
        streaming=False,
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain", "application/json"],
    )
    card.capabilities = AgentCapabilities(
        streaming=False,
        extensions=[
            AgentExtension(
                uri=A2UI_EXTENSION_URI,
                description="Ability to render A2UI",
                required=False,
                params={
                    "supportedCatalogIds": [A2UI_CATALOG_ID],
                    # The dashboard uses a custom WebFrameSrcdoc HTML panel; allow inline catalogs.
                    "acceptsInlineCatalogs": True,
                },
            )
        ],
    )
    card.url = RPC_URL
    card.preferred_transport = "JSONRPC"
    return card


_agent_card = _build_agent_card()
_request_handler = DefaultRequestHandler(
    agent_executor=RouterCostExecutor(),
    task_store=InMemoryTaskStore(),
)

app = FastAPI(
    title="GEAP Router Cost Visualizer",
    description="A2A server hosting the deterministic A2UI router cost-accrual dashboard.",
)

_a2a_app = A2AFastAPIApplication(agent_card=_agent_card, http_handler=_request_handler)
_a2a_app.add_routes_to_app(
    app,
    agent_card_url=f"{RPC_PATH}{AGENT_CARD_WELL_KNOWN_PATH}",
    rpc_url=RPC_PATH,
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
