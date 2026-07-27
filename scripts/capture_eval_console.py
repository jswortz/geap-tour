#!/usr/bin/env python3
"""Capture LIVE GCP Console screenshots for the GEAP agent-evaluation evidence.

Runs a HEADED Chromium on a virtual X display (Xvfb :1, exposed over VNC) so an
operator can sign in to the Google Cloud Console ONCE. The browser uses a
persistent profile (~/.geap-eval-chrome), so the Google auth session survives
and is reused on later runs.

Prereqs (see scripts/vnc_setup.sh):
    bash scripts/vnc_setup.sh          # start Xvfb + fluxbox + x11vnc on :1/5901
    ssh -L 5901:localhost:5901 <host>  # tunnel, connect a VNC viewer
    # sign in to the GCP Console once in the VNC desktop
    DISPLAY=:1 python3 scripts/capture_eval_console.py

Contrast with scripts/capture_eval_screenshots.py, which renders headless HTML
mockups and needs no login. This script photographs the REAL console UI.
"""

import argparse
import os
import sys
from pathlib import Path

# --- Environment defaults (must be set before launching the browser) ---------
os.environ.setdefault("DISPLAY", ":1")
os.environ.setdefault(
    "PLAYWRIGHT_BROWSERS_PATH", os.path.expanduser("~/.cache/ms-playwright")
)

# --- Guarded Playwright import ----------------------------------------------
try:
    from playwright.sync_api import sync_playwright
except ImportError:  # checked in capture(); keeps py_compile/import lightweight
    sync_playwright = None

SCREENSHOT_DIR = Path("docs/screenshots")
USER_DATA_DIR = os.path.expanduser("~/.geap-eval-chrome")
PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "wortz-project-352116")

# ---------------------------------------------------------------------------
# EDIT ME: (screenshot_name, console_url) pairs to capture.
#
# These point at the REAL Google Cloud Console. After you sign in via VNC, adjust
# each URL to the exact "Agent Platform > Agents > Evaluation" deep link for your
# tenant — the console URL scheme may differ (the Agent Platform / Gemini
# Enterprise surfaces can live under a different path than the Vertex AI ones
# used as defaults below). Add or remove entries freely.
# ---------------------------------------------------------------------------
CONSOLE_TARGETS: list[tuple[str, str]] = [
    (
        "eval_console_evaluation_tab",
        f"https://console.cloud.google.com/vertex-ai/agents/agent-engines?project={PROJECT_ID}",
    ),
    (
        "eval_console_online_monitors",
        f"https://console.cloud.google.com/vertex-ai/agents?project={PROJECT_ID}",
    ),
    (
        "eval_console_metrics_registry",
        f"https://console.cloud.google.com/vertex-ai/agents?project={PROJECT_ID}",
    ),
    (
        "eval_console_traces",
        f"https://console.cloud.google.com/traces/list?project={PROJECT_ID}",
    ),
    (
        "eval_console_monitoring_alerts",
        f"https://console.cloud.google.com/monitoring/alerting?project={PROJECT_ID}",
    ),
]


def _looks_like_login(url: str) -> bool:
    """True if the current URL indicates a Google sign-in / consent page."""
    lowered = (url or "").lower()
    return "accounts.google.com" in lowered or "signin" in lowered


def _install_hint() -> None:
    print("ERROR: Playwright is not installed / importable.")
    print("  Install it, then the cached Chromium, with:")
    print("    pip install playwright")
    print("    npx playwright install chromium")
    print("    #  or:  python -m playwright install chromium")


def capture(no_wait: bool = False, only: str | None = None) -> int:
    if sync_playwright is None:
        _install_hint()
        return 1

    targets = CONSOLE_TARGETS
    if only:
        targets = [t for t in CONSOLE_TARGETS if t[0] == only]
        if not targets:
            names = ", ".join(name for name, _ in CONSOLE_TARGETS)
            print(f"ERROR: no CONSOLE_TARGETS entry named {only!r}.")
            print(f"  Available names: {names}")
            return 1

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    print("=== GEAP eval — live GCP Console capture ===")
    print(f"DISPLAY={os.environ.get('DISPLAY')}  profile={USER_DATA_DIR}")
    print(f"Output: {SCREENSHOT_DIR}/  ({len(targets)} target(s))\n")

    saved = 0
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            viewport={"width": 1920, "height": 1080},
            args=["--start-maximized"],
        )
        page = context.pages[0] if context.pages else context.new_page()

        # Open the first target and detect whether a Google sign-in is needed.
        first_url = targets[0][1]
        try:
            page.goto(first_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:  # noqa: BLE001
            print(f"  (initial navigation warning: {e})")
        page.wait_for_timeout(3000)

        if _looks_like_login(page.url):
            if no_wait:
                print("  Not signed in and --no-wait set; screenshots may show the login page.")
            else:
                print(
                    "\n  >>> Please complete Google sign-in in the VNC session, "
                    "then press ENTER here."
                )
                try:
                    input()
                except EOFError:
                    print("  (no interactive stdin available; continuing without waiting)")

        for name, url in targets:
            try:
                # Console pages hold long-poll connections open, so networkidle
                # can time out even when the UI has fully rendered — screenshot
                # anyway rather than skipping the target.
                try:
                    page.goto(url, wait_until="networkidle", timeout=60000)
                except Exception as nav_err:  # noqa: BLE001
                    print(f"    (nav settle warning for {name}: {nav_err})")
                page.wait_for_timeout(4000)
                png_path = SCREENSHOT_DIR / f"{name}.png"
                page.screenshot(path=str(png_path), full_page=False)
                size = png_path.stat().st_size if png_path.exists() else 0
                print(f"  ✓ {png_path} ({size:,} bytes)")
                saved += 1
            except Exception as e:  # noqa: BLE001
                print(f"  ✗ {name}: {e}")

        context.close()

    print(f"\n✓ Captured {saved}/{len(targets)} console screenshot(s) to {SCREENSHOT_DIR}/")
    return 0 if saved else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture live GCP Console screenshots for GEAP eval evidence.",
    )
    parser.add_argument(
        "--display",
        default=None,
        help="X display to use (e.g. :1). Overrides $DISPLAY for this run.",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Do not pause for interactive sign-in (for automation).",
    )
    parser.add_argument(
        "--targets-only",
        metavar="NAME",
        default=None,
        help="Capture only the CONSOLE_TARGETS entry with this screenshot name.",
    )
    args = parser.parse_args(argv)

    if args.display:
        os.environ["DISPLAY"] = args.display

    return capture(no_wait=args.no_wait, only=args.targets_only)


if __name__ == "__main__":
    sys.exit(main())
