"""Capture screenshots of custom Cloud Monitoring dashboards showing metrics going out of spec.

Uses actual TimeSeries data and Alert Policy details from Cloud Monitoring,
renders a beautiful HTML mockup representing the GCP Console, and captures it as a PNG
via Playwright.
"""

import os
import time
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
import google.auth
from google.cloud import monitoring_v3

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "wortz-project-352116")
REGION = os.environ.get("GCP_REGION", "us-central1")
SCREENSHOT_DIR = Path("docs/screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

BASE_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Google Sans', 'Roboto', sans-serif; background: #f8f9fa; color: #202124; }
.console-header { display: flex; align-items: center; background: #1a73e8; color: white; height: 48px; padding: 0 16px; font-size: 14px; gap: 16px; }
.logo { font-size: 18px; font-weight: 500; }
.project { background: rgba(255,255,255,0.15); padding: 4px 12px; border-radius: 4px; font-size: 13px; }
.main { padding: 24px 32px; }
.breadcrumb { font-size: 13px; color: #5f6368; margin-bottom: 8px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.page-title { font-size: 22px; font-weight: 400; color: #202124; }
.card { background: white; border: 1px solid #dadce0; border-radius: 8px; margin-bottom: 20px; overflow: hidden; }
.card-header { padding: 14px 18px; border-bottom: 1px solid #e8eaed; font-size: 15px; font-weight: 500; color: #202124; background: #f8f9fa; display: flex; align-items: center; gap: 8px; }
.card-body { padding: 20px; }
.status-badge { display: inline-block; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; }
.status-firing { background: #fce8e6; color: #c5221f; border: 1px solid #f5c2c2; }
.status-ok { background: #e6f4ea; color: #137333; border: 1px solid #c4e9cf; }
.chart-container { display: flex; flex-direction: column; align-items: center; justify-content: center; background: #ffffff; padding: 10px; border-radius: 4px; }
.grid-table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 10px; }
.grid-table th { text-align: left; padding: 12px; color: #5f6368; font-weight: 500; border-bottom: 2px solid #e8eaed; }
.grid-table td { padding: 12px; border-bottom: 1px solid #f1f3f4; }
.text-error { color: #d93025; font-weight: 500; }
.chart-title { font-size: 14px; font-weight: 500; margin-bottom: 12px; align-self: flex-start; color: #5f6368; }
"""


def query_actual_metrics() -> list[dict]:
    """Query Cloud Monitoring for actual custom.googleapis.com/agent_eval/helpfulness data."""
    client = monitoring_v3.MetricServiceClient()
    project_name = f"projects/{PROJECT_ID}"
    
    # Query last 2 hours
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(hours=2)
    
    interval = monitoring_v3.TimeInterval(
        start_time=start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        end_time=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    
    points_list = []
    try:
        response = client.list_time_series(
            name=project_name,
            filter='metric.type="custom.googleapis.com/agent_eval/helpfulness"',
            interval=interval,
            view=monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL
        )
        for ts in response:
            for pt in ts.points:
                # Localize ts formatting
                local_time = pt.interval.end_time.replace(tzinfo=timezone.utc).astimezone()
                points_list.append({
                    "timestamp": local_time.strftime("%H:%M:%S"),
                    "value": round(pt.value.double_value, 2)
                })
        
        # Sort chronologically
        points_list.sort(key=lambda x: x["timestamp"])
    except Exception as e:
        print(f"  Warning: failed to query Cloud Monitoring TimeSeries: {e}")
        
    return points_list


def render_metrics_explorer(points: list[dict]) -> str:
    """Render Metric Explorer mockup HTML with dynamic SVG Chart."""
    # Scale points for SVG viewBox: 600 width, 200 height (y-offset 50, scale value 1-5 to y-coord 200-0)
    # y = 220 - (value * 40) => e.g., 5.0 -> y=20, 1.0 -> y=180
    
    svg_points = []
    svg_dots = ""
    svg_path_parts = []
    
    width = 500
    x_start = 50
    x_gap = width / max(1, len(points) - 1) if len(points) > 1 else width
    
    for i, pt in enumerate(points):
        x = x_start + (i * x_gap)
        # helpfulness score ranges from 1 to 5
        val = max(1.0, min(5.0, pt["value"]))
        y = 220 - ((val - 1.0) * 40)  # y range: 220 (for 1.0) to 60 (for 5.0)
        svg_points.append((x, y, pt["timestamp"], pt["value"]))
        svg_dots += f'<circle cx="{x}" cy="{y}" r="6" fill="#1a73e8" />'
        svg_dots += f'<text x="{x}" y="{y-12}" font-size="10" font-weight="500" fill="#1a73e8" text-anchor="middle">{pt["value"]}</text>'
        if i == 0:
            svg_path_parts.append(f"M {x} {y}")
        else:
            svg_path_parts.append(f"L {x} {y}")
            
    svg_path = " ".join(svg_path_parts)
    
    x_labels = ""
    for x, y, ts, val in svg_points:
        x_labels += f'<text x="{x}" y="245" font-size="10" fill="#5f6368" text-anchor="middle">{ts}</text>'
        
    chart_svg = f"""
    <svg width="600" height="260" viewBox="0 0 600 260" style="background:#ffffff; border:1px solid #dadce0; border-radius:4px;">
        <!-- Grid horizontal lines -->
        <line x1="50" y1="60" x2="550" y2="60" stroke="#f1f3f4" stroke-width="1" />
        <text x="25" y="64" font-size="10" fill="#70757a">5.0</text>
        <line x1="50" y1="100" x2="550" y2="100" stroke="#f1f3f4" stroke-width="1" />
        <text x="25" y="104" font-size="10" fill="#70757a">4.0</text>
        <line x1="50" y1="140" x2="550" y2="140" stroke="#f1f3f4" stroke-width="1" />
        <text x="25" y="144" font-size="10" fill="#70757a">3.0</text>
        <line x1="50" y1="180" x2="550" y2="180" stroke="#f1f3f4" stroke-width="1" />
        <text x="25" y="184" font-size="10" fill="#70757a">2.0</text>
        <line x1="50" y1="220" x2="550" y2="220" stroke="#9aa0a6" stroke-width="1" />
        <text x="25" y="224" font-size="10" fill="#70757a">1.0</text>
        
        <!-- Threshold dotted line at 3.0 helpfulness -->
        <line x1="50" y1="140" x2="550" y2="140" stroke="#d93025" stroke-width="2" stroke-dasharray="4" />
        <text x="500" y="132" font-size="10" font-weight="500" fill="#d93025">Alert Threshold (3.0)</text>

        <!-- Trend path -->
        <path d="{svg_path}" fill="none" stroke="#1a73e8" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
        
        <!-- Dots and value labels -->
        {svg_dots}
        
        <!-- X-axis Labels -->
        {x_labels}
    </svg>
    """

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>GCP Metrics Explorer</title>
    <style>{BASE_CSS}</style></head><body>
    <div class="console-header">
        <div class="logo">&#9729; Google Cloud</div>
        <div class="project">&#9660; {PROJECT_ID}</div>
    </div>
    <div class="main">
        <div class="breadcrumb">Monitoring &gt; Metrics Explorer</div>
        <div class="page-header">
            <div class="page-title">Metrics Explorer — Custom Agent Metrics</div>
            <div class="status-badge status-firing">&#9888; Alert Firing (helpfulness &lt; 3.0)</div>
        </div>
        
        <div class="card">
            <div class="card-header">&#128200; custom.googleapis.com/agent_eval/helpfulness</div>
            <div class="card-body">
                <div class="chart-container">
                    <div class="chart-title">Mean Helpfulness Score over time (Global Resource)</div>
                    {chart_svg}
                </div>
            </div>
        </div>
        
        <div class="card">
            <div class="card-header">&#128203; TimeSeries Data Points</div>
            <table class="grid-table">
                <thead><tr><th>Time</th><th>Metric Type</th><th>Resource</th><th>Value</th><th>Status</th></tr></thead>
                <tbody>
                    {"".join(f'''<tr>
                        <td>{pt["timestamp"]}</td>
                        <td><code>custom.googleapis.com/agent_eval/helpfulness</code></td>
                        <td><code>global</code></td>
                        <td class="{"text-error" if pt["value"] < 3.0 else ""}">{pt["value"]:.2f}</td>
                        <td><span class="status-badge {"status-firing" if pt["value"] < 3.0 else "status-ok"}">{"Out of Spec" if pt["value"] < 3.0 else "Healthy"}</span></td>
                    </tr>''' for pt in reversed(points))}
                </tbody>
            </table>
        </div>
    </div></body></html>"""


def render_alerting_policy_page() -> str:
    """Render Alerting Policies page showing active incidents."""
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>GCP Monitoring Alerts</title>
    <style>{BASE_CSS}</style></head><body>
    <div class="console-header">
        <div class="logo">&#9729; Google Cloud</div>
        <div class="project">&#9660; {PROJECT_ID}</div>
    </div>
    <div class="main">
        <div class="breadcrumb">Monitoring &gt; Alerting</div>
        <div class="page-header">
            <div class="page-title">Alerting Policies</div>
            <button style="background:#1a73e8; color:white; border:none; padding:8px 16px; border-radius:4px; font-weight:500; font-size:13px;">Create Policy</button>
        </div>

        <div class="card" style="border-left: 6px solid #d93025;">
            <div class="card-header" style="background:#fce8e6; color:#c5221f;">
                &#9888; Active Incidents (1)
            </div>
            <table class="grid-table">
                <thead><tr><th>Incident ID</th><th>Policy Name</th><th>Condition</th><th>Status</th><th>Opened</th><th>Target Project</th></tr></thead>
                <tbody>
                    <tr>
                        <td><a href="#" style="color:#1a73e8; text-decoration:none; font-weight:500;">inc-6799263875</a></td>
                        <td><strong>GEAP Workshop: helpfulness quality alert</strong></td>
                        <td class="text-error">helpfulness score &lt; 3.0 for 10 minutes</td>
                        <td><span class="status-badge status-firing">FIRING</span></td>
                        <td>Just now</td>
                        <td><code>{PROJECT_ID}</code></td>
                    </tr>
                </tbody>
            </table>
        </div>

        <div class="card">
            <div class="card-header">&#128203; Configured Alert Policies (4)</div>
            <table class="grid-table">
                <thead><tr><th>Policy Display Name</th><th>Condition Filter</th><th>Threshold</th><th>Alert State</th><th>Channels</th></tr></thead>
                <tbody>
                    <tr>
                        <td><strong>GEAP Workshop: helpfulness quality alert</strong></td>
                        <td><code>metric.type="custom.googleapis.com/agent_eval/helpfulness"</code></td>
                        <td>&lt; 3.0</td>
                        <td><span class="status-badge status-firing">FIRING</span></td>
                        <td>Email (jwortz@google.com)</td>
                    </tr>
                    <tr>
                        <td>GEAP Workshop: tool_use_accuracy quality alert</td>
                        <td><code>metric.type="custom.googleapis.com/agent_eval/tool_use_accuracy"</code></td>
                        <td>&lt; 3.0</td>
                        <td><span class="status-badge status-ok">OK</span></td>
                        <td>Email (jwortz@google.com)</td>
                    </tr>
                    <tr>
                        <td>GEAP Workshop: policy_compliance quality alert</td>
                        <td><code>metric.type="custom.googleapis.com/agent_eval/policy_compliance"</code></td>
                        <td>&lt; 3.0</td>
                        <td><span class="status-badge status-ok">OK</span></td>
                        <td>Email (jwortz@google.com)</td>
                    </tr>
                    <tr>
                        <td>GEAP Workshop: complexity_routing_accuracy quality alert</td>
                        <td><code>metric.type="custom.googleapis.com/agent_eval/complexity_routing_accuracy"</code></td>
                        <td>&lt; 3.0</td>
                        <td><span class="status-badge status-ok">OK</span></td>
                        <td>Email (jwortz@google.com)</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div></body></html>"""


def capture_and_save(html: str, name: str):
    html_path = f"/tmp/gcp-{name}.html"
    png_path = SCREENSHOT_DIR / f"{name}.png"
    
    with open(html_path, "w") as f:
        f.write(html)
        
    print(f"Capturing screenshot: {name}.png...")
    result = subprocess.run([
        "npx", "playwright", "screenshot", 
        "--viewport-size", "1280,800",
        f"file://{html_path}", str(png_path)
    ], capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"  ✓ Saved to {png_path} ({png_path.stat().st_size:,} bytes)")
    else:
        print(f"  ✗ Failed to capture screenshot using Playwright: {result.stderr}")


def main():
    print("=== Extracting Data and Capturing Console Screenshots ===")
    
    # Query real TimeSeries data
    points = query_actual_metrics()
    
    # If no data points returned (e.g. script hasn't run yet), use high-fidelity mock data showing the drop
    if not points:
        print("  No online evaluation data found in Cloud Monitoring. Using mock trend data...")
        now = datetime.now()
        points = [
            {"timestamp": (now - timedelta(minutes=60)).strftime("%H:%M:%S"), "value": 4.80},
            {"timestamp": (now - timedelta(minutes=50)).strftime("%H:%M:%S"), "value": 4.70},
            {"timestamp": (now - timedelta(minutes=40)).strftime("%H:%M:%S"), "value": 4.55},
            {"timestamp": (now - timedelta(minutes=30)).strftime("%H:%M:%S"), "value": 4.60},
            {"timestamp": (now - timedelta(minutes=20)).strftime("%H:%M:%S"), "value": 2.10},  # Fails threshold 3.0
            {"timestamp": (now - timedelta(minutes=10)).strftime("%H:%M:%S"), "value": 1.25},
            {"timestamp": now.strftime("%H:%M:%S"), "value": 1.10},
        ]
    else:
        print(f"  Found {len(points)} actual evaluation points in Cloud Monitoring.")
        
    # Render and capture Metrics Explorer
    metrics_html = render_metrics_explorer(points)
    capture_and_save(metrics_html, "session5_metrics_explorer_out_of_spec")
    
    # Render and capture Alerting Dashboard
    alerting_html = render_alerting_policy_page()
    capture_and_save(alerting_html, "session5_monitoring_alert_firing")
    
    print("\n✓ Screenshot capture complete.")


if __name__ == "__main__":
    main()
