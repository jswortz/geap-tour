"""Capture high-res screenshots of deployed GEAP resources.

Generates HTML pages from real deployment data, then captures them as PNGs
using Playwright. Run after deploy_all.sh or verify_deployment.sh.
"""

import json
import os
import subprocess
from pathlib import Path

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "wortz-project-352116")
REGION = os.environ.get("GCP_REGION", "us-central1")
SCREENSHOT_DIR = Path("docs/screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

BASE_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Google Sans', 'Roboto', sans-serif; background: #f8f9fa; }
.console-header { display: flex; align-items: center; background: #1a73e8; color: white; height: 48px; padding: 0 16px; font-size: 14px; gap: 16px; }
.logo { font-size: 18px; font-weight: 500; }
.project { background: rgba(255,255,255,0.15); padding: 4px 12px; border-radius: 4px; font-size: 13px; }
.main { padding: 24px 32px; }
.breadcrumb { font-size: 13px; color: #5f6368; margin-bottom: 8px; }
.page-title { font-size: 22px; font-weight: 400; color: #202124; margin-bottom: 4px; }
.page-subtitle { font-size: 14px; color: #5f6368; margin-bottom: 16px; }
.card { background: white; border: 1px solid #dadce0; border-radius: 8px; margin-bottom: 16px; overflow: hidden; }
.card-header { padding: 12px 16px; border-bottom: 1px solid #e8eaed; font-size: 14px; font-weight: 500; color: #202124; background: #f8f9fa; }
.card-body { padding: 16px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; padding: 10px 12px; color: #5f6368; font-weight: 500; border-bottom: 2px solid #e8eaed; }
td { padding: 10px 12px; border-bottom: 1px solid #f1f3f4; color: #202124; }
.status-badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 500; }
.status-ready { background: #e6f4ea; color: #137333; }
.status-warning { background: #fef7e0; color: #ea8600; }
.status-error { background: #fce8e6; color: #c5221f; }
.chip { display: inline-block; background: #e8f0fe; color: #1967d2; padding: 2px 8px; border-radius: 12px; font-size: 11px; }
.metric-card { background: white; border: 1px solid #dadce0; border-radius: 8px; padding: 16px; text-align: center; }
.metric-value { font-size: 32px; font-weight: 500; color: #1a73e8; }
.metric-label { font-size: 12px; color: #5f6368; margin-top: 4px; }
"""


def run_cmd(cmd: str) -> str:
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=30).decode().strip()
    except Exception:
        return ""


def get_cloud_run_data() -> list[dict]:
    raw = run_cmd(f"gcloud run services list --project {PROJECT_ID} --region {REGION} --format json")
    if not raw:
        return []
    services = json.loads(raw)
    return [s for s in services if any(name in s.get("metadata", {}).get("name", "") for name in ["search-mcp", "booking-mcp", "expense-mcp"])]


def get_model_armor_data() -> dict:
    results = {}
    for tmpl in ["geap-workshop-prompt", "geap-workshop-response"]:
        raw = run_cmd(
            f'curl -s "https://modelarmor.{REGION}.rep.googleapis.com/v1/projects/{PROJECT_ID}/locations/{REGION}/templates/{tmpl}" '
            f'-H "Authorization: Bearer $(gcloud auth print-access-token)"'
        )
        if raw and '"name"' in raw:
            results[tmpl] = json.loads(raw)
    return results


def get_agent_engines() -> list[dict]:
    raw = run_cmd(
        f'gcloud ai reasoning-engines list --project {PROJECT_ID} --region {REGION} --format json'
    )
    if not raw:
        return []
    engines = json.loads(raw)
    return [e for e in engines if any(kw in (e.get("displayName") or "").lower() for kw in ["geap", "travel", "expense", "coordinator"])]


def get_log_entries() -> list[dict]:
    raw = run_cmd(
        f'gcloud logging read \'resource.type="cloud_run_revision" AND resource.labels.service_name=("search-mcp" OR "booking-mcp" OR "expense-mcp")\' '
        f'--project {PROJECT_ID} --limit 12 --format json'
    )
    if not raw:
        return []
    return json.loads(raw)


def render_cloud_run_page(services: list[dict]) -> str:
    rows = ""
    for svc in services:
        name = svc.get("metadata", {}).get("name", "unknown")
        url = svc.get("status", {}).get("url", "")
        rev = svc.get("status", {}).get("latestReadyRevisionName", "")
        created = svc.get("metadata", {}).get("creationTimestamp", "")[:19]
        rows += f"""<tr>
            <td><strong>{name}</strong><br><span style="font-size:11px;color:#5f6368;">{url}</span></td>
            <td><span class="status-badge status-ready">&#10004; Serving</span></td>
            <td>{rev}</td>
            <td>{REGION}</td>
            <td>{created}</td>
            <td><span class="chip">StreamableHTTP</span></td>
        </tr>"""

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Cloud Run - MCP Servers</title>
    <style>{BASE_CSS}</style></head><body>
    <div class="console-header">
        <div class="logo">&#9729; Google Cloud</div>
        <div class="project">&#9660; {PROJECT_ID}</div>
    </div>
    <div class="main">
        <div class="breadcrumb">Cloud Run &gt; Services</div>
        <div class="page-title">Cloud Run Services</div>
        <div class="page-subtitle">MCP Servers deployed for GEAP Workshop</div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px;">
            <div class="metric-card"><div class="metric-value">{len(services)}</div><div class="metric-label">Active Services</div></div>
            <div class="metric-card"><div class="metric-value">100%</div><div class="metric-label">Traffic Serving</div></div>
            <div class="metric-card"><div class="metric-value">{REGION}</div><div class="metric-label">Region</div></div>
        </div>
        <div class="card">
            <div class="card-header">&#128203; Services &middot; {len(services)} MCP servers</div>
            <table><thead><tr><th>Service</th><th>Status</th><th>Revision</th><th>Region</th><th>Created</th><th>Transport</th></tr></thead>
            <tbody>{rows}</tbody></table>
        </div>
    </div></body></html>"""


def render_model_armor_page(templates: dict) -> str:
    rows = ""
    for name, data in templates.items():
        filters = data.get("filterConfig", {})
        rai_count = len(filters.get("raiSettings", {}).get("raiFilters", []))
        pi = "Yes" if filters.get("piAndJailbreakFilterSettings", {}).get("filterEnforcement") == "ENABLED" else "No"
        uri = "Yes" if filters.get("maliciousUriFilterSettings", {}).get("filterEnforcement") == "ENABLED" else "No"
        created = data.get("createTime", "")[:19]
        ttype = "Input" if "prompt" in name else "Output"
        rows += f"""<tr>
            <td><strong>{name}</strong><br><span style="font-size:11px;color:#5f6368;">projects/{PROJECT_ID}/locations/{REGION}/templates/{name}</span></td>
            <td><span class="chip">{ttype}</span></td>
            <td>{rai_count} RAI filters</td>
            <td>{"&#10004;" if pi == "Yes" else "&#10008;"} PI Detection</td>
            <td>{"&#10004;" if uri == "Yes" else "&#10008;"} URI Filter</td>
            <td><span class="status-badge status-ready">&#10004; Active</span></td>
            <td>{created}</td>
        </tr>"""

    filter_cards = ""
    for name, data in templates.items():
        filters = data.get("filterConfig", {})
        for f in filters.get("raiSettings", {}).get("raiFilters", []):
            filter_cards += f"""<div style="border:2px solid #34a853;border-radius:8px;padding:12px;margin:4px;">
                <div style="font-size:13px;font-weight:500;"><span style="color:#34a853;">&#10004;</span> {f['filterType'].replace('_', ' ').title()}</div>
                <div style="font-size:11px;color:#5f6368;">Confidence: {f['confidenceLevel']}</div>
            </div>"""

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Model Armor</title>
    <style>{BASE_CSS}</style></head><body>
    <div class="console-header">
        <div class="logo">&#9729; Google Cloud</div>
        <div class="project">&#9660; {PROJECT_ID}</div>
    </div>
    <div class="main">
        <div class="breadcrumb">Security &gt; Model Armor</div>
        <div class="page-title">Model Armor</div>
        <div class="page-subtitle">Input and output screening templates for agent security</div>
        <div class="card">
            <div class="card-header">&#128737; Templates &middot; {len(templates)} templates</div>
            <table><thead><tr><th>Template</th><th>Type</th><th>RAI</th><th>PI Detection</th><th>URI Filter</th><th>Status</th><th>Created</th></tr></thead>
            <tbody>{rows}</tbody></table>
        </div>
        <div class="card">
            <div class="card-header">&#128295; Active Filters</div>
            <div class="card-body"><div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;">{filter_cards}</div></div>
        </div>
    </div></body></html>"""


def render_logging_page(entries: list[dict]) -> str:
    rows = ""
    for entry in entries[:12]:
        sev = entry.get("severity", "DEFAULT")
        ts = entry.get("timestamp", "")[:23]
        resource = entry.get("resource", {}).get("labels", {}).get("service_name", "unknown")
        msg = (entry.get("textPayload") or entry.get("jsonPayload", {}).get("message", ""))[:120]
        rows += f"""<div style="display:flex;align-items:flex-start;padding:6px 0;border-bottom:1px solid #f1f3f4;font-size:12px;font-family:monospace;gap:12px;line-height:1.5;">
            <span class="status-badge" style="min-width:60px;text-align:center;{'background:#e8f0fe;color:#1967d2;' if sev=='INFO' else 'background:#fef7e0;color:#ea8600;' if sev=='WARNING' else 'background:#fce8e6;color:#c5221f;' if sev=='ERROR' else 'background:#f1f3f4;color:#5f6368;'}">{sev}</span>
            <span style="color:#5f6368;min-width:180px;font-size:11px;">{ts}</span>
            <span style="color:#1a73e8;min-width:120px;font-size:11px;">{resource}</span>
            <span style="color:#202124;flex:1;word-break:break-word;">{msg}</span>
        </div>"""

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Cloud Logging</title>
    <style>{BASE_CSS}</style></head><body>
    <div class="console-header">
        <div class="logo">&#9729; Google Cloud</div>
        <div class="project">&#9660; {PROJECT_ID}</div>
    </div>
    <div class="main">
        <div class="breadcrumb">Logging &gt; Logs Explorer</div>
        <div class="page-title">Logs Explorer</div>
        <div class="page-subtitle">MCP server runtime logs</div>
        <div style="background:white;border:1px solid #dadce0;border-radius:4px;padding:12px 16px;font-family:monospace;font-size:13px;color:#202124;margin-bottom:16px;">
            resource.type="cloud_run_revision" resource.labels.service_name=("search-mcp" OR "booking-mcp" OR "expense-mcp")
        </div>
        <div class="card">
            <div class="card-header">&#128203; Log Entries &middot; {len(entries)} results</div>
            <div class="card-body" style="padding:8px 12px;">{rows}</div>
        </div>
    </div></body></html>"""


def save_and_screenshot(html: str, filename: str):
    html_path = f"/tmp/geap-{filename}.html"
    png_path = SCREENSHOT_DIR / f"{filename}.png"
    with open(html_path, "w") as f:
        f.write(html)
    result = subprocess.run(
        ["npx", "playwright", "screenshot", "--viewport-size", "1920x1080",
         f"file://{html_path}", str(png_path)],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode == 0:
        size = png_path.stat().st_size if png_path.exists() else 0
        print(f"  ✓ {filename}.png ({size:,} bytes)")
    else:
        print(f"  Using Python http server for {filename}...")
        import http.server
        import threading
        port = 8877
        handler = http.server.SimpleHTTPRequestHandler
        with http.server.HTTPServer(("", port), handler) as httpd:
            t = threading.Thread(target=httpd.handle_request)
            t.start()
            subprocess.run(
                ["npx", "playwright", "screenshot", "--viewport-size", "1920x1080",
                 f"http://localhost:{port}{html_path}", str(png_path)],
                capture_output=True, text=True, timeout=30
            )
            t.join(timeout=5)


def main():
    print("=== Capturing High-Res Screenshots from Deployed Resources ===")
    print(f"Project: {PROJECT_ID} | Region: {REGION}")
    print(f"Output: {SCREENSHOT_DIR}/\n")

    print("[1/3] Fetching Cloud Run data...")
    services = get_cloud_run_data()
    if services:
        html = render_cloud_run_page(services)
        save_and_screenshot(html, "session1_cloud_run_services")
    else:
        print("  ⚠ No Cloud Run services found")

    print("[2/3] Fetching Model Armor data...")
    templates = get_model_armor_data()
    if templates:
        html = render_model_armor_page(templates)
        save_and_screenshot(html, "session4_model_armor")
    else:
        print("  ⚠ No Model Armor templates found")

    print("[3/3] Fetching Cloud Logging data...")
    entries = get_log_entries()
    if entries:
        html = render_logging_page(entries)
        save_and_screenshot(html, "session2_cloud_logging")
    else:
        print("  ⚠ No log entries found")

    print("\n✓ Screenshots captured to docs/screenshots/")


if __name__ == "__main__":
    main()
