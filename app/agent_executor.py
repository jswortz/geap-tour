"""Deterministic A2A executor for the Router Cost Visualizer (Gemini Enterprise).

Mirrors party-store-ge-a2ui/app/agent_executor.py: rather than relying on an LLM to emit UI,
it builds the A2UI screen in Python and emits each command as a DataPart tagged
``mimeType=application/json+a2ui`` (without that tag GE silently drops the canvas). Served over
HTTP on Cloud Run because GE cannot invoke A2A agents on Vertex Agent Runtime.
"""
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import DataPart, Part, TextPart
from a2a.utils import new_task

from app.cost_model import build_accrual
from app.ui_builder import build_cost_dashboard_command

A2UI_MIMETYPE = "application/json+a2ui"


def _parts(text: str, ui_messages: list) -> list:
    parts = [Part(root=TextPart(text=text))]
    for msg in ui_messages:
        parts.append(Part(root=DataPart(data=msg, metadata={"mimeType": A2UI_MIMETYPE})))
    return parts


class RouterCostExecutor(AgentExecutor):
    """Renders the multi-model router's cost-accrual dashboard as an A2UI canvas."""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # Echo the requested A2A extension(s) back so Gemini Enterprise accepts the
        # A2UI response and renders the canvas. Without this, the reply omits the
        # X-A2A-Extensions header and GE silently drops the application/json+a2ui
        # DataParts (blank agent panel). Matches the party-store / dg-ge reference.
        for ext in (context.requested_extensions or []):
            try:
                context.add_activated_extension(ext)
            except Exception:
                pass

        acc = build_accrual()
        commands = build_cost_dashboard_command(acc)
        summary = (
            f"Across {len(acc.steps)} prompts the smart router spent "
            f"${acc.router_total:.4f} vs ${acc.baseline_total:.4f} all-Opus — "
            f"{acc.savings_pct:.1f}% savings. Frontier (Opus) was used for only "
            f"{acc.tier_counts.get('Opus', 0)} genuinely complex prompts."
        )

        # Full task lifecycle, matching the proven party-store executor: a new task must be
        # enqueued before start_work()/add_artifact() so GE tracks it and renders the canvas.
        task = context.current_task
        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work()
        await updater.add_artifact(_parts(summary, commands), name="router_cost_dashboard")
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("cancel is not supported")
