"""A2UI screen builders for the Router Cost Visualizer — Image docked in the GE side canvas.

In this Gemini Enterprise deployment only Image/WebFrame surfaces dock in the right-hand canvas panel
(native components render inline at the top of the chat, and WebFrame renders blank). To show the live
dashboard "on the side", each screen is a native **Image** pointing at a per-request PNG rendered from
the live accrual (`/panels/*.png?ctx=&v=`, see `app/panel_render.py` + `app/fast_api_app.py`), plus
native tab Buttons. The surfaceId is the reserved ``canvas-surface`` so GE docks it in the panel; both
tabs share it so a switch updates the same panel.
"""
from __future__ import annotations

from typing import List

from app.cost_model import Accrual  # noqa: F401  (kept for type hints / callers)

# "canvas-surface" is the reserved surfaceId GE renders in the right-hand canvas panel.
CANVAS_SURFACE = "canvas-surface"
DASHBOARD_SURFACE = CANVAS_SURFACE
ROUTING_SURFACE = CANVAS_SURFACE
SURFACE_ID = CANVAS_SURFACE


class _Screen:
    """Accumulates native A2UI components with unique ids and emits the command list."""

    def __init__(self) -> None:
        self.components: List[dict] = []
        self._n = 0

    def _id(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}-{self._n}"

    def image(self, url: str, alt: str = "") -> str:
        cid = self._id("img")
        self.components.append({"id": cid, "component": {"Image": {
            "url": {"literalString": url}, "altText": {"literalString": alt}, "fit": "contain"}}})
        return cid

    def canvas_trigger(self) -> str:
        """A tiny WebFrameSrcdoc whose presence makes GE dock this surface in the side canvas panel
        (rather than rendering inline). GE paints the WebFrame itself blank/zero-height, so it adds no
        visible content — the Image is what shows in the panel."""
        cid = self._id("wf")
        self.components.append({"id": cid, "component": {"WebFrameSrcdoc": {
            "htmlContent": {"literalString": "<!doctype html><title>panel</title>"}, "height": 1}}})
        return cid

    def button(self, label: str, action: str, primary: bool = False) -> str:
        eid = self._id("btn")
        tid = f"txt_{eid}"
        self.components.append({"id": eid, "component": {"Button": {
            "child": tid, "primary": primary, "action": {"name": action}}}})
        self.components.append({"id": tid, "component": {"Text": {
            "text": {"literalString": label}, "usageHint": "body"}}})
        return eid

    def build(self, root_child_ids: List[str], surface_id: str = CANVAS_SURFACE) -> List[dict]:
        self.components.insert(0, {"id": "root-layout", "component": {
            "Column": {"children": {"explicitList": root_child_ids}}}})
        return [
            {"beginRendering": {"surfaceId": surface_id, "root": "root-layout"}},
            {"surfaceUpdate": {"surfaceId": surface_id, "components": self.components}},
        ]


def build_dashboard_screen(acc: Accrual, image_url: str) -> List[dict]:
    """Cost dashboard: the live dashboard PNG (docked in the canvas) + tab/reset buttons."""
    sc = _Screen()
    img = sc.image(image_url, "Router cost accrual dashboard: Smart Router vs all-Opus")
    b1 = sc.button("🔬 Routing logic & scoring", "view_routing", primary=True)
    b2 = sc.button("↺ Reset session", "reset", primary=False)
    wf = sc.canvas_trigger()
    return sc.build([img, b1, b2, wf], DASHBOARD_SURFACE)


def build_routing_logic_screen(acc: Accrual, image_url: str) -> List[dict]:
    """Routing logic & scoring: the tokenomics/scoring PNG (docked in the canvas) + tab/reset buttons."""
    sc = _Screen()
    img = sc.image(image_url, "Routing logic and scoring: score to model tier and token rates")
    b1 = sc.button("📊 Cost dashboard", "view_dashboard", primary=True)
    b2 = sc.button("↺ Reset session", "reset", primary=False)
    wf = sc.canvas_trigger()
    return sc.build([img, b1, b2, wf], ROUTING_SURFACE)
