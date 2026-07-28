"""A2A executor for the live Router Cost Visualizer (Gemini Enterprise).

For each prompt the user sends to the GE agent, this classifies the prompt, routes it to the cheapest
capable model tier, ACTUALLY invokes that model (real tokens + cost), accrues the result per GE
session, and renders a native A2UI dashboard. Two tabs are switched by Button userActions:
``view_dashboard`` / ``view_routing`` / ``reset``. Nav/reset actions re-render from accrued state
without calling a model.

Served over HTTP on Cloud Run (GE cannot invoke A2A agents on Vertex Agent Runtime). A2UI DataParts
are tagged ``application/json+a2ui`` and the requested A2A extension is echoed so GE renders the canvas.
"""
import os

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import DataPart, Part, TextPart
from a2a.utils import new_task

from app import session_store
from app.router_logic import route_and_run
from app.ui_builder import build_dashboard_screen, build_routing_logic_screen

A2UI_MIMETYPE = "application/json+a2ui"
APP_URL = os.getenv("APP_URL", "https://geap-router-cost-ui-679926387543.us-east1.run.app").rstrip("/")


def _panel_url(name: str, ctx_id: str, acc) -> str:
    """URL of the per-request dashboard PNG (docked in the GE canvas). ``v`` (step count) is a
    cache-buster so GE refetches after each prompt."""
    from urllib.parse import quote
    return f"{APP_URL}/panels/{name}.png?ctx={quote(ctx_id or '_default')}&v={len(acc.steps)}"


def _parts(text: str, ui_messages: list) -> list:
    parts = [Part(root=TextPart(text=text))]
    for msg in ui_messages:
        parts.append(Part(root=DataPart(data=msg, metadata={"mimeType": A2UI_MIMETYPE})))
    return parts


def _parse(context: RequestContext):
    """Return (userAction_name, text) from the incoming A2A message."""
    action, text = None, ""
    if context.message and context.message.parts:
        for part in context.message.parts:
            root = part.root
            if isinstance(root, DataPart) and isinstance(root.data, dict) and "userAction" in root.data:
                action = (root.data["userAction"] or {}).get("name")
            elif isinstance(root, TextPart) and root.text:
                text = root.text
    if not text:
        try:
            text = context.get_user_input() or ""
        except Exception:  # noqa: BLE001
            text = ""
    return action, text


class RouterCostExecutor(AgentExecutor):
    """Live per-prompt routing + cost dashboard, rendered as a native A2UI canvas."""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # Echo requested A2A extension(s) so GE accepts the A2UI response and renders the canvas.
        for ext in (context.requested_extensions or []):
            try:
                context.add_activated_extension(ext)
            except Exception:  # noqa: BLE001
                pass

        # Task lifecycle: enqueue a new task and start_work() early so GE tracks it while we run models.
        task = context.current_task
        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work()

        ctx_id = task.context_id or ""
        action, text = _parse(context)
        low = text.lower().strip()

        # Nav is detected by SUBSTRING (GE may reword/annotate the prompt text, so exact matches
        # are unreliable) or by an explicit Button userAction.
        is_reset = action == "reset" or "reset" in low or low in ("clear", "start over")
        is_routing = action == "view_routing" or "routing logic" in low or "scoring" in low \
            or ("rout" in low and "logic" in low)
        is_dashboard = action == "view_dashboard" or "dashboard" in low or "cost dashboard" in low

        try:
            if is_reset:
                acc = session_store.reset(ctx_id)
                summary = "🔄 Session reset — cost accrual cleared. Send a prompt to start routing again."
                commands = build_dashboard_screen(acc, _panel_url("dashboard", ctx_id, acc))
            elif is_routing:
                acc = session_store.get(ctx_id)
                summary = "Here's how prompts get scored and routed across the model tiers (see the canvas)."
                commands = build_routing_logic_screen(acc, _panel_url("routing", ctx_id, acc))
            elif is_dashboard or not low:
                acc = session_store.get(ctx_id)
                summary = "Here's the live router cost dashboard (see the canvas on the right)."
                commands = build_dashboard_screen(acc, _panel_url("dashboard", ctx_id, acc))
            else:
                # A real workload prompt: classify → route → actually run the tier model → accrue.
                acc = session_store.get(ctx_id)
                routed = await route_and_run(text)
                step = acc.add(text, routed)
                answer = (routed.get("answer") or "").strip()
                note = (f"— routed to **{step.tier}** ({step.model}) · complexity {step.score:.2f} · "
                        f"{step.input_tokens:,} in / {step.output_tokens:,} out · ${step.request_cost:.6f} "
                        f"(session total ${acc.router_total:.6f}, {acc.savings_pct:.1f}% vs all-Opus)")
                if routed.get("error") and not answer:
                    summary = f"⚠️ The {step.tier} model call failed: {routed['error']}\n\n{note}"
                else:
                    summary = f"{answer}\n\n{note}" if answer else note
                commands = build_dashboard_screen(acc, _panel_url("dashboard", ctx_id, acc))
        except Exception as exc:  # noqa: BLE001 — never fail the A2A task; render an empty dashboard
            acc = session_store.get(ctx_id)
            summary = f"⚠️ Sorry, I hit an error: {type(exc).__name__}: {exc}"
            commands = build_dashboard_screen(acc, _panel_url("dashboard", ctx_id, acc))

        await updater.add_artifact(_parts(summary, commands), name="response")
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("cancel is not supported")
