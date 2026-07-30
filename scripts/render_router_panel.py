"""Render the branded router cost-accrual dashboard to app/assets/router_cost.png.

The Cloud Run app serves this PNG at ``/panels/router_cost.png`` and Gemini Enterprise displays it
via the native A2UI Image component in the agent canvas — GE does not render inline WebFrameSrcdoc
HTML in this deployment, so the live canvas shows the pre-rendered PNG. Run this before deploying
the router-UI whenever the dashboard HTML or the underlying cost model changes.

Run:
  uv run --with playwright python scripts/render_router_panel.py
  # (once) uv run --with playwright playwright install chromium
"""
from __future__ import annotations

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, REPO)

from app.ui_builder import build_cost_dashboard_html  # noqa: E402

ASSETS = os.path.join(REPO, "app", "assets")
OUT = os.path.join(ASSETS, "router_cost.png")
WIDTH = 860  # matches the .wrap max-width (840) + a little breathing room


def render_html_to_png(html: str, out_path: str, width: int = WIDTH) -> str:
    """Render self-contained HTML to a full-page PNG at 2x device scale."""
    from playwright.sync_api import sync_playwright

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        tmp = f.name
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=2)
            try:
                page.goto(f"file://{tmp}", wait_until="networkidle", timeout=30000)
            except Exception:
                page.goto(f"file://{tmp}", wait_until="load", timeout=30000)
            page.wait_for_timeout(700)  # let fonts + SVG settle
            page.screenshot(path=out_path, full_page=True)
            browser.close()
    finally:
        os.unlink(tmp)
    return out_path


def main() -> int:
    os.makedirs(ASSETS, exist_ok=True)
    print("Rendering router cost dashboard HTML -> PNG ...")
    render_html_to_png(build_cost_dashboard_html(), OUT, width=WIDTH)
    size = os.path.getsize(OUT)
    print(f"  wrote {OUT} ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
