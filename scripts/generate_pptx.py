"""Generate PowerPoint slide deck from GEAP workshop content."""

import os
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

DOCS = os.path.join(os.path.dirname(__file__), "..", "docs")
SCREENSHOTS = os.path.join(DOCS, "screenshots")
DIAGRAMS = os.path.join(os.path.dirname(__file__), "..", "diagrams", "outputs")
OUTPUT = os.path.join(DOCS, "slides.pptx")

BLUE = RGBColor(0x1A, 0x73, 0xE8)
GREEN = RGBColor(0x1E, 0x8E, 0x3E)
RED = RGBColor(0xD9, 0x30, 0x25)
YELLOW = RGBColor(0xF9, 0xAB, 0x00)
DARK = RGBColor(0x20, 0x21, 0x24)
GRAY = RGBColor(0x5F, 0x63, 0x68)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT = RGBColor(0xF8, 0xF9, 0xFA)
LIGHT_BLUE = RGBColor(0xE8, 0xF0, 0xFE)
DARK_BLUE = RGBColor(0x17, 0x4E, 0xA6)

FONT = "Calibri"
CODE_FONT = "Consolas"
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


def set_bg(slide, color):
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color


def set_bg_gradient(slide, color1, color2):
    bg = slide.background
    fill = bg.fill
    fill.gradient()
    fill.gradient_stops[0].color.rgb = color1
    fill.gradient_stops[0].position = 0.0
    fill.gradient_stops[1].color.rgb = color2
    fill.gradient_stops[1].position = 1.0


def add_text(slide, left, top, width, height, text, font_size=18,
             bold=False, color=DARK, align=PP_ALIGN.LEFT, font_name=FONT):
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(font_size)
    p.font.bold = bold
    p.font.color.rgb = color
    p.font.name = font_name
    p.alignment = align
    return txBox


def add_para(text_frame, text, font_size=18, bold=False, color=DARK,
             font_name=FONT, space_before=Pt(4), bullet=False, level=0):
    p = text_frame.add_paragraph()
    p.text = text
    p.font.size = Pt(font_size)
    p.font.bold = bold
    p.font.color.rgb = color
    p.font.name = font_name
    p.space_before = space_before
    p.level = level
    if bullet:
        p.level = level
    return p


def add_bullet_list(slide, left, top, width, height, items, font_size=18,
                    color=DARK, title=None, title_color=BLUE, title_size=22):
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True

    if title:
        p = tf.paragraphs[0]
        p.text = title
        p.font.size = Pt(title_size)
        p.font.bold = True
        p.font.color.rgb = title_color
        p.font.name = FONT
        p.space_after = Pt(8)

    for i, item in enumerate(items):
        if title or i > 0:
            p = tf.add_paragraph()
        else:
            p = tf.paragraphs[0]
        p.text = item
        p.font.size = Pt(font_size)
        p.font.color.rgb = color
        p.font.name = FONT
        p.space_before = Pt(6)
        p.level = 0
    return txBox


def add_code_block(slide, left, top, width, height, code_text, font_size=11):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = LIGHT
    shape.line.color.rgb = RGBColor(0xDA, 0xDC, 0xE0)
    shape.line.width = Pt(1)

    tf = shape.text_frame
    tf.word_wrap = True
    tf.margin_left = Pt(12)
    tf.margin_top = Pt(8)
    tf.margin_right = Pt(12)
    tf.margin_bottom = Pt(8)

    lines = code_text.strip().split("\n")
    for i, line in enumerate(lines):
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.text = line
        p.font.size = Pt(font_size)
        p.font.name = CODE_FONT
        p.font.color.rgb = DARK
        p.space_before = Pt(0)
        p.space_after = Pt(0)
    return shape


def add_card(slide, left, top, width, height, title, body, accent_color=BLUE):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = WHITE
    shape.line.color.rgb = accent_color
    shape.line.width = Pt(2)

    tf = shape.text_frame
    tf.word_wrap = True
    tf.margin_left = Pt(12)
    tf.margin_top = Pt(8)

    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = accent_color
    p.font.name = FONT

    p2 = tf.add_paragraph()
    p2.text = body
    p2.font.size = Pt(13)
    p2.font.color.rgb = GRAY
    p2.font.name = FONT
    p2.space_before = Pt(6)
    return shape


def add_table(slide, left, top, width, height, headers, rows, font_size=14):
    table_shape = slide.shapes.add_table(len(rows) + 1, len(headers), left, top, width, height)
    table = table_shape.table

    for i, h in enumerate(headers):
        cell = table.cell(0, i)
        cell.text = h
        for p in cell.text_frame.paragraphs:
            p.font.size = Pt(font_size)
            p.font.bold = True
            p.font.color.rgb = WHITE
            p.font.name = FONT
        cell.fill.solid()
        cell.fill.fore_color.rgb = BLUE

    for r_idx, row in enumerate(rows):
        for c_idx, val in enumerate(row):
            cell = table.cell(r_idx + 1, c_idx)
            cell.text = val
            for p in cell.text_frame.paragraphs:
                p.font.size = Pt(font_size - 1)
                p.font.color.rgb = DARK
                p.font.name = FONT
            if r_idx % 2 == 1:
                cell.fill.solid()
                cell.fill.fore_color.rgb = LIGHT
    return table_shape


def add_logo(slide, color=GRAY):
    add_text(slide, Inches(11), Inches(6.9), Inches(2), Inches(0.4),
             "Google Cloud", font_size=14, color=color, align=PP_ALIGN.RIGHT)


def add_image_safe(slide, path, left, top, width=None, height=None):
    if os.path.exists(path):
        kwargs = {"left": left, "top": top}
        if width:
            kwargs["width"] = width
        if height:
            kwargs["height"] = height
        slide.shapes.add_picture(path, **kwargs)
        return True
    return False


def build_deck():
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    blank = prs.slide_layouts[6]

    # ===== SLIDE 1: TITLE =====
    s = prs.slides.add_slide(blank)
    set_bg_gradient(s, DARK_BLUE, BLUE)
    add_text(s, Inches(0.8), Inches(0.6), Inches(5), Inches(0.4),
             "Google Cloud Workshop", 16, color=YELLOW, bold=True)
    add_text(s, Inches(0.8), Inches(1.5), Inches(11), Inches(2),
             "Gemini Enterprise\nAgent Platform Tour", 48, bold=True, color=WHITE)
    add_text(s, Inches(0.8), Inches(3.8), Inches(11), Inches(0.8),
             "Build, Deploy, Govern, Evaluate, and Optimize AI Agents", 24, color=RGBColor(0xCC, 0xCC, 0xCC))
    add_text(s, Inches(0.8), Inches(5.2), Inches(11), Inches(0.5),
             "ADK Agents  •  MCP Servers  •  Agent Gateway  •  Agent Registry  •  Model Armor  •  Evaluation Pipeline",
             18, color=RGBColor(0x99, 0x99, 0x99))
    add_logo(s, RGBColor(0x88, 0x88, 0x88))

    # ===== SLIDE 2: AGENDA =====
    s = prs.slides.add_slide(blank)
    add_text(s, Inches(0.8), Inches(0.5), Inches(6), Inches(0.8), "Agenda", 42, bold=True)
    add_table(s, Inches(0.8), Inches(1.6), Inches(11.5), Inches(4),
              ["Session", "Topic", "Duration", "Key Activities"],
              [
                  ["1", "AI Gateway / MCP Gateway", "~90 min", "Architecture, MCP servers, ADK agents, deployment, identity"],
                  ["", "Lunch Break", "~45 min", ""],
                  ["2", "AI Gateway / MCP Gateway (cont.)", "~75 min", "Agent Gateway, evaluation, observability, optimization"],
                  ["3", "Agent Registry", "~15 min", "Agent registration, discovery, governance"],
                  ["4", "Model Security / Model Armor", "~15 min", "Input/output screening, guardrails, content safety"],
                  ["", "Break", "~15 min", ""],
              ])
    add_logo(s)

    # ===== SLIDE 3: ARCHITECTURE =====
    s = prs.slides.add_slide(blank)
    add_text(s, Inches(0.8), Inches(0.3), Inches(8), Inches(0.8), "Platform Architecture", 42, bold=True)
    add_image_safe(s, os.path.join(SCREENSHOTS, "geap_architecture.png"),
                   Inches(1.5), Inches(1.4), width=Inches(10))
    add_text(s, Inches(1), Inches(6.5), Inches(11), Inches(0.5),
             "User → Frontend → Agent Gateway → Agent Identity (Runtime) → Agent Gateway → Agents, Tools, Models, APIs",
             16, color=GRAY, align=PP_ALIGN.CENTER)
    add_logo(s)

    # ===== SLIDE 4: IDENTITY MODEL =====
    s = prs.slides.add_slide(blank)
    add_text(s, Inches(0.8), Inches(0.3), Inches(8), Inches(0.8), "Agent Identity Model", 42, bold=True)
    add_image_safe(s, os.path.join(SCREENSHOTS, "identity_types.png"),
                   Inches(1), Inches(1.3), width=Inches(11))
    add_logo(s)

    # ===== SLIDE 5: SESSION 1 HEADER =====
    s = prs.slides.add_slide(blank)
    set_bg(s, BLUE)
    add_text(s, Inches(0.8), Inches(0.6), Inches(5), Inches(0.4),
             "Session 1", 16, color=RGBColor(0xCC, 0xDD, 0xFF), bold=True)
    add_text(s, Inches(0.8), Inches(1.5), Inches(11), Inches(1.2),
             "AI Gateway / MCP Gateway", 48, bold=True, color=WHITE)
    add_text(s, Inches(0.8), Inches(3.0), Inches(11), Inches(0.6),
             "Build, connect, and deploy agents with MCP tool servers", 22, color=RGBColor(0xCC, 0xDD, 0xFF))
    add_bullet_list(s, Inches(0.8), Inches(4.0), Inches(10), Inches(3),
                    ["Multi-agent architecture with MCP connectivity",
                     "FastMCP tool servers on Cloud Run",
                     "ADK agents deployed to Agent Runtime",
                     "SPIFFE-based workload identity"],
                    font_size=20, color=RGBColor(0xEE, 0xEE, 0xFF))
    add_logo(s, RGBColor(0x88, 0x99, 0xCC))

    # ===== SLIDE 6: MULTI-AGENT TOPOLOGY =====
    s = prs.slides.add_slide(blank)
    add_text(s, Inches(0.8), Inches(0.3), Inches(8), Inches(0.8),
             "Multi-Agent Topology", 36, bold=True)
    add_image_safe(s, os.path.join(DIAGRAMS, "01_multi_agent_topology.png"),
                   Inches(0.5), Inches(1.3), width=Inches(6))
    add_bullet_list(s, Inches(7), Inches(1.3), Inches(5.5), Inches(2.5),
                    ["Coordinator Agent — routes requests to specialists",
                     "Travel Agent — searches flights/hotels, makes bookings",
                     "Expense Agent — submits expenses, enforces policy limits"],
                    title="Three ADK Agents", title_color=BLUE)
    add_bullet_list(s, Inches(7), Inches(4.2), Inches(5.5), Inches(2.5),
                    ["Search MCP — shared by Travel + Coordinator",
                     "Booking MCP — flight/hotel reservations",
                     "Expense MCP — expense submission + policy checks"],
                    title="Three MCP Servers", title_color=BLUE)
    add_logo(s)

    # ===== SLIDE 7: MCP SERVER DEV =====
    s = prs.slides.add_slide(blank)
    add_text(s, Inches(0.8), Inches(0.3), Inches(8), Inches(0.8),
             "MCP Server Development", 36, bold=True)
    add_text(s, Inches(0.8), Inches(1.1), Inches(5), Inches(0.4),
             "FastMCP Pattern", 22, bold=True, color=BLUE)
    add_code_block(s, Inches(0.8), Inches(1.6), Inches(5.5), Inches(4.2),
                   'from fastmcp import FastMCP\n\nmcp = FastMCP("search-mcp")\n\n@mcp.tool()\ndef search_flights(\n    origin: str,\n    destination: str,\n    date: str | None = None\n) -> list[dict]:\n    """Search available flights."""\n    return flight_db.search(\n        origin, destination, date\n    )',
                   font_size=12)
    add_card(s, Inches(7), Inches(1.3), Inches(5.5), Inches(1.4),
             "StreamableHTTP Transport",
             "MCP servers run as standard HTTP services on Cloud Run with automatic scaling", BLUE)
    add_card(s, Inches(7), Inches(3.0), Inches(5.5), Inches(1.4),
             "Tool Discovery",
             "Agents dynamically discover available tools via MCP protocol introspection", GREEN)
    add_card(s, Inches(7), Inches(4.7), Inches(5.5), Inches(1.4),
             "1-to-Many Topology",
             "Multiple agents can share the same MCP server — no duplication needed", YELLOW)
    add_logo(s)

    # ===== SLIDE 8: ADK AGENTS =====
    s = prs.slides.add_slide(blank)
    add_text(s, Inches(0.8), Inches(0.3), Inches(8), Inches(0.8),
             "ADK Agent Architecture", 36, bold=True)
    add_text(s, Inches(0.8), Inches(1.1), Inches(5), Inches(0.4),
             "Agent Definition", 22, bold=True, color=BLUE)
    add_code_block(s, Inches(0.8), Inches(1.6), Inches(5.5), Inches(4.5),
                   'from google.adk.agents import LlmAgent\nfrom google.adk.tools import McpToolset\n\ntravel_agent = LlmAgent(\n  name="travel_agent",\n  model="gemini-2.0-flash",\n  instruction="""You are a travel\n  assistant...""",\n  tools=[\n    McpToolset(\n      connection_params=\n        StreamableHTTPConnectionParams(\n          url="https://search-mcp-..."\n        )\n    )\n  ]\n)',
                   font_size=11)
    add_card(s, Inches(7), Inches(1.3), Inches(5.5), Inches(1.4),
             "Coordinator Pattern",
             "Root agent uses sub_agents=[travel, expense] to delegate by intent", BLUE)
    add_card(s, Inches(7), Inches(3.0), Inches(5.5), Inches(1.4),
             "Session Management",
             "Each user gets isolated sessions with conversation history and state", GREEN)
    add_card(s, Inches(7), Inches(4.7), Inches(5.5), Inches(1.4),
             "OTel Tracing",
             "Every agent call produces OpenTelemetry spans — exported to Cloud Trace automatically", YELLOW)
    add_logo(s)

    # ===== SLIDE 9: DEPLOYMENT =====
    s = prs.slides.add_slide(blank)
    add_text(s, Inches(0.8), Inches(0.3), Inches(8), Inches(0.8),
             "Deployment Architecture", 36, bold=True)
    add_image_safe(s, os.path.join(DIAGRAMS, "02_deployment_architecture.png"),
                   Inches(0.5), Inches(1.3), width=Inches(6))
    add_card(s, Inches(7), Inches(1.3), Inches(5.5), Inches(1.5),
             "Cloud Run — MCP Servers",
             "StreamableHTTP transport, auto-scaling, IAM-secured endpoints", BLUE)
    add_card(s, Inches(7), Inches(3.1), Inches(5.5), Inches(1.5),
             "Agent Runtime — ADK Agents",
             "Vertex AI Agent Engine with built-in session management and memory", GREEN)
    txBox = add_text(s, Inches(7), Inches(5.0), Inches(5.5), Inches(1),
             "One command deploy: bash scripts/deploy_all.sh\nDeploys 3 MCP servers + coordinator agent in sequence",
             16, color=DARK)
    add_logo(s)

    # ===== SLIDE 10: CONSOLE — AGENT ENGINE =====
    s = prs.slides.add_slide(blank)
    set_bg(s, DARK)
    add_text(s, Inches(0.8), Inches(0.3), Inches(10), Inches(0.8),
             "Console: Deployments on Agent Runtime", 32, bold=True, color=WHITE)
    add_image_safe(s, os.path.join(SCREENSHOTS, "session1_agent_engine.png"),
                   Inches(0.8), Inches(1.3), width=Inches(11.5))
    add_logo(s, RGBColor(0x88, 0x88, 0x88))

    # ===== SLIDE 11: IDENTITY (SPIFFE) =====
    s = prs.slides.add_slide(blank)
    add_text(s, Inches(0.8), Inches(0.3), Inches(8), Inches(0.8),
             "Agent Identity — SPIFFE", 36, bold=True)
    add_image_safe(s, os.path.join(DIAGRAMS, "04_agent_identity_gateway.png"),
                   Inches(0.5), Inches(1.3), width=Inches(6))
    add_bullet_list(s, Inches(7), Inches(1.3), Inches(5.5), Inches(2),
                    ["Each agent gets a SPIFFE ID at deployment",
                     "Attestation policies verify agent identity at runtime",
                     "Agent Gateway enforces identity at network boundary"],
                    title="Workload Identity Federation", title_color=BLUE)
    add_table(s, Inches(7), Inches(4.0), Inches(5.5), Inches(2),
              ["Type", "Purpose"],
              [["ID-1: User", "Human accessing the app"],
               ["ID-2: Agent", "Agent's own authority"],
               ["ID-3: Delegated", "Agent on behalf of user"]],
              font_size=14)
    add_logo(s)

    # ===== SLIDE 12: CONSOLE — WORKLOAD IDENTITY =====
    s = prs.slides.add_slide(blank)
    set_bg(s, DARK)
    add_text(s, Inches(0.8), Inches(0.3), Inches(10), Inches(0.8),
             "Console: Workload Identity Pools", 32, bold=True, color=WHITE)
    add_image_safe(s, os.path.join(SCREENSHOTS, "session1_workload_identity.png"),
                   Inches(0.8), Inches(1.3), width=Inches(11.5))
    add_logo(s, RGBColor(0x88, 0x88, 0x88))

    # ===== SLIDE 13: SESSION 2 HEADER =====
    s = prs.slides.add_slide(blank)
    set_bg_gradient(s, DARK_BLUE, BLUE)
    add_text(s, Inches(0.8), Inches(0.6), Inches(5), Inches(0.4),
             "Session 2", 16, color=RGBColor(0xCC, 0xDD, 0xFF), bold=True)
    add_text(s, Inches(0.8), Inches(1.5), Inches(11), Inches(1.5),
             "AI Gateway / MCP Gateway\n(continued)", 44, bold=True, color=WHITE)
    add_text(s, Inches(0.8), Inches(3.5), Inches(11), Inches(0.6),
             "Gateway, evaluation, observability, and optimization", 22, color=RGBColor(0xCC, 0xDD, 0xFF))
    add_bullet_list(s, Inches(0.8), Inches(4.3), Inches(10), Inches(2.5),
                    ["Agent Gateway for ingress/egress control",
                     "Three-tier evaluation pipeline",
                     "Online monitors and failure cluster analysis",
                     "Agent optimization with GEPA algorithm"],
                    font_size=20, color=RGBColor(0xEE, 0xEE, 0xFF))
    add_logo(s, RGBColor(0x88, 0x99, 0xCC))

    # ===== SLIDE 14: AGENT GATEWAY =====
    s = prs.slides.add_slide(blank)
    add_text(s, Inches(0.8), Inches(0.3), Inches(8), Inches(0.8),
             "Agent Gateway — Dual Mode", 36, bold=True)
    add_text(s, Inches(0.8), Inches(1.1), Inches(5), Inches(0.4),
             "Ingress + Egress Governance", 22, bold=True, color=BLUE)
    add_table(s, Inches(0.8), Inches(1.6), Inches(5.8), Inches(1.5),
              ["Mode", "Gateway", "Controls"],
              [["Client-to-Agent", "geap-workshop-gateway", "Inbound user requests"],
               ["Agent-to-Anywhere", "geap-workshop-gateway-egress", "Gemini model calls, MCP tools, external APIs"]],
              font_size=13)
    txBox = add_text(s, Inches(0.8), Inches(3.4), Inches(5.8), Inches(0.8),
             "With egress gateway, ALL outbound traffic — including Gemini model calls — routes through governance (IAM Allow + SGP + Model Armor)",
             14, color=DARK)
    add_code_block(s, Inches(0.8), Inches(4.4), Inches(5.8), Inches(2.0),
                   'config = {\n  "agent_gateway_config": {\n    "client_to_agent_config": {"agent_gateway": INGRESS},\n    "agent_to_anywhere_config": {"agent_gateway": EGRESS},\n  },\n  "identity_type": "AGENT_IDENTITY",\n}',
                   font_size=11)
    add_text(s, Inches(0.8), Inches(6.5), Inches(5.8), Inches(0.4),
             "Requires Private Preview — gateway attachment via REST API PATCH",
             11, color=GRAY)
    add_image_safe(s, os.path.join(SCREENSHOTS, "session2_agent_gateway.png"),
                   Inches(7), Inches(1.3), width=Inches(5.8))
    add_logo(s)

    # ===== SLIDE 14b: AGENT TRACES =====
    s = prs.slides.add_slide(blank)
    set_bg(s, DARK)
    add_text(s, Inches(0.8), Inches(0.3), Inches(10), Inches(0.8),
             "Console: Agent Traces", 32, bold=True, color=WHITE)
    add_image_safe(s, os.path.join(SCREENSHOTS, "session2_agent_traces.png"),
                   Inches(0.8), Inches(1.3), width=Inches(11.5))
    add_text(s, Inches(1), Inches(6.5), Inches(11), Inches(0.5),
             "Session view showing model calls, tool calls, token usage, and duration per trace",
             16, color=RGBColor(0xAA, 0xAA, 0xAA), align=PP_ALIGN.CENTER)
    add_logo(s, RGBColor(0x88, 0x88, 0x88))

    # ===== SLIDE 14c: GOVERNANCE POLICIES =====
    s = prs.slides.add_slide(blank)
    add_text(s, Inches(0.8), Inches(0.3), Inches(10), Inches(0.8),
             "Governance — Three Policy Layers", 36, bold=True)
    add_table(s, Inches(0.8), Inches(1.3), Inches(6), Inches(2.2),
              ["Layer", "Type", "Enforces"],
              [["IAM Allow", "Static (CEL rules)", "Which MCP servers an agent can call"],
               ["SGP", "Runtime (natural language)", 'Business rules — e.g. "Booking < $5,000"'],
               ["Model Armor", "Content screening", "Prompt injection, jailbreak, PII, harmful content"]],
              font_size=13)
    txBox = add_text(s, Inches(0.8), Inches(3.8), Inches(6), Inches(0.8),
             "Layered defense: IAM Allow restricts where agents connect, SGP restricts what agents do, Model Armor restricts how content is screened",
             14, color=DARK)
    add_text(s, Inches(7), Inches(1.1), Inches(5.5), Inches(0.4),
             "IAM Allow Policy (CEL)", 18, bold=True, color=BLUE)
    add_code_block(s, Inches(7), Inches(1.6), Inches(5.5), Inches(1.8),
                   'resource.type == "networkservices"\n&& resource.service in [\n  "search-mcp",\n  "booking-mcp",\n  "expense-mcp"\n]',
                   font_size=11)
    add_text(s, Inches(7), Inches(3.6), Inches(5.5), Inches(0.4),
             "Semantic Governance Policy", 18, bold=True, color=BLUE)
    add_code_block(s, Inches(7), Inches(4.1), Inches(5.5), Inches(2),
                   'name: "booking-limit"\nrule: "Booking amounts must\n  not exceed $5,000 per\n  transaction"\naction: BLOCK',
                   font_size=11)
    add_logo(s)

    # ===== SLIDE 15: EVAL PIPELINE =====
    s = prs.slides.add_slide(blank)
    add_text(s, Inches(0.8), Inches(0.3), Inches(10), Inches(0.8),
             "Three-Tier Evaluation Pipeline", 36, bold=True)
    add_image_safe(s, os.path.join(DIAGRAMS, "03_eval_pipeline.png"),
                   Inches(1.5), Inches(1.1), width=Inches(10), height=Inches(3))
    add_card(s, Inches(0.8), Inches(4.5), Inches(3.6), Inches(2),
             "One-Time Eval",
             "Manual, on-demand evaluation with PointwiseMetric rubrics against a curated dataset", BLUE)
    add_card(s, Inches(4.8), Inches(4.5), Inches(3.6), Inches(2),
             "Online Monitors",
             "Continuous evaluation of live traffic via Cloud Trace telemetry on 10-min cycles", GREEN)
    add_card(s, Inches(8.8), Inches(4.5), Inches(3.6), Inches(2),
             "Simulated (CI/CD)",
             "Automated eval gate on PRs — score ≥ 3.0 to merge, blocks otherwise", YELLOW)
    add_logo(s)

    # ===== SLIDE 16: CONSOLE — EVALUATION =====
    s = prs.slides.add_slide(blank)
    set_bg(s, DARK)
    add_text(s, Inches(0.8), Inches(0.3), Inches(10), Inches(0.8),
             "Console: Evaluation Experiments", 32, bold=True, color=WHITE)
    add_image_safe(s, os.path.join(SCREENSHOTS, "session2_evaluation.png"),
                   Inches(0.8), Inches(1.3), width=Inches(11.5))
    add_logo(s, RGBColor(0x88, 0x88, 0x88))

    # ===== SLIDE 17: OBSERVABILITY =====
    s = prs.slides.add_slide(blank)
    add_text(s, Inches(0.8), Inches(0.3), Inches(8), Inches(0.8),
             "Observability Stack", 36, bold=True)
    add_image_safe(s, os.path.join(DIAGRAMS, "05_observability_stack.png"),
                   Inches(0.5), Inches(1.3), width=Inches(6))
    add_text(s, Inches(7), Inches(1.3), Inches(5.5), Inches(0.4),
             "End-to-End Tracing", 22, bold=True, color=BLUE)
    add_text(s, Inches(7), Inches(1.9), Inches(5.5), Inches(0.6),
             "Agent Call  →  OTel Spans  →  Cloud Trace  →  BigQuery",
             18, color=BLUE, font_name=FONT)
    add_bullet_list(s, Inches(7), Inches(3.0), Inches(5.5), Inches(3.5),
                    ["Cloud Trace captures every agent + tool call",
                     "Log sink exports structured data to BigQuery",
                     "Cloud Monitoring alerts on anomalies",
                     "Failure cluster analysis groups error patterns"],
                    title="Data Pipeline", title_color=BLUE)
    add_logo(s)

    # ===== SLIDE 18: CONSOLE — CLOUD TRACE =====
    s = prs.slides.add_slide(blank)
    set_bg(s, DARK)
    add_text(s, Inches(0.8), Inches(0.3), Inches(10), Inches(0.8),
             "Console: Cloud Trace", 32, bold=True, color=WHITE)
    add_image_safe(s, os.path.join(SCREENSHOTS, "session2_cloud_trace.png"),
                   Inches(0.8), Inches(1.3), width=Inches(11.5))
    add_logo(s, RGBColor(0x88, 0x88, 0x88))

    # ===== SLIDE 19: CI/CD =====
    s = prs.slides.add_slide(blank)
    add_text(s, Inches(0.8), Inches(0.3), Inches(8), Inches(0.8),
             "CI/CD — Simulated Eval Gate", 36, bold=True)
    add_image_safe(s, os.path.join(DIAGRAMS, "06_ci_cd_flow.png"),
                   Inches(0.5), Inches(1.3), width=Inches(6))
    add_text(s, Inches(7), Inches(1.3), Inches(5.5), Inches(0.4),
             "GitHub Actions Workflow", 22, bold=True, color=BLUE)
    add_text(s, Inches(7), Inches(1.9), Inches(5.5), Inches(0.6),
             "PR Opened  →  Generate Scenarios  →  Run Inference  →  Evaluate  →  Score ≥ 3.0?",
             16, color=BLUE)
    add_text(s, Inches(7), Inches(3.0), Inches(5.5), Inches(1),
             "✅  Pass — Merge allowed\n❌  Fail — PR blocked with failure report",
             18, color=DARK)
    add_logo(s)

    # ===== SLIDE 20: GEPA =====
    s = prs.slides.add_slide(blank)
    add_text(s, Inches(0.8), Inches(0.3), Inches(10), Inches(0.8),
             "Agent Optimization — GEPA Algorithm", 36, bold=True)
    add_bullet_list(s, Inches(0.8), Inches(1.3), Inches(5.5), Inches(3),
                    ["Generate prompt variants using LLM mutation",
                     "Evaluate each variant against test scenarios",
                     "Select top performers based on eval scores",
                     "Evolve over multiple generations"],
                    title="Gemini Evolutionary Prompt Algorithm", title_color=BLUE)
    txBox = add_text(s, Inches(0.8), Inches(4.8), Inches(5.5), Inches(1),
             "Result: Automatically discovers better agent instructions without manual prompt engineering",
             18, color=DARK)
    add_text(s, Inches(7), Inches(1.1), Inches(5.5), Inches(0.4),
             "Configuration", 22, bold=True, color=BLUE)
    add_code_block(s, Inches(7), Inches(1.6), Inches(5.5), Inches(3.5),
                   'optimizer = AgentOptimizer(\n  agent=coordinator_agent,\n  eval_dataset=eval_data,\n  metrics=[\n    "response_quality",\n    "tool_selection",\n    "safety"\n  ],\n  generations=5,\n  population_size=4\n)',
                   font_size=13)
    add_logo(s)

    # ===== SLIDE 21: SESSION 3 HEADER =====
    s = prs.slides.add_slide(blank)
    set_bg(s, DARK)
    add_text(s, Inches(0.8), Inches(0.6), Inches(5), Inches(0.4),
             "Session 3", 16, color=YELLOW, bold=True)
    add_text(s, Inches(0.8), Inches(2), Inches(11), Inches(1.5),
             "Agent Registry", 52, bold=True, color=WHITE)
    add_text(s, Inches(0.8), Inches(3.8), Inches(11), Inches(0.6),
             "Agent registration, discovery, and governance", 22, color=RGBColor(0x9A, 0xA0, 0xA6))
    add_logo(s, RGBColor(0x88, 0x88, 0x88))

    # ===== SLIDE 22: AGENT REGISTRY =====
    s = prs.slides.add_slide(blank)
    add_text(s, Inches(0.8), Inches(0.3), Inches(8), Inches(0.8),
             "Agent Registry & Discovery", 36, bold=True)
    add_bullet_list(s, Inches(0.8), Inches(1.3), Inches(5.5), Inches(2.5),
                    ["Register agents with metadata, toolspecs, and versioning",
                     "Discover available agents and their capabilities",
                     "Associate MCP tool specifications with agents",
                     "Govern agent lifecycle and access control"],
                    title="Registry Capabilities", title_color=BLUE)
    add_text(s, Inches(0.8), Inches(4.0), Inches(5.5), Inches(0.4),
             "Toolspec Association", 20, bold=True, color=BLUE)
    add_code_block(s, Inches(0.8), Inches(4.5), Inches(5.5), Inches(1.5),
                   'gcloud agent-platform agent-registry \\\n  toolspecs associate \\\n  --agent=geap-coordinator \\\n  --toolspec=search-mcp-spec.yaml',
                   font_size=12)
    add_image_safe(s, os.path.join(SCREENSHOTS, "session3_agent_registry_mcp.png"),
                   Inches(7), Inches(1.3), width=Inches(5.8))
    add_logo(s)

    # ===== SLIDE 23: CONSOLE — POLICIES =====
    s = prs.slides.add_slide(blank)
    set_bg(s, DARK)
    add_text(s, Inches(0.8), Inches(0.3), Inches(10), Inches(0.8),
             "Console: Business Policies", 32, bold=True, color=WHITE)
    add_image_safe(s, os.path.join(SCREENSHOTS, "session3_policies.png"),
                   Inches(0.8), Inches(1.3), width=Inches(11.5))
    add_logo(s, RGBColor(0x88, 0x88, 0x88))

    # ===== SLIDE 24: SESSION 4 HEADER =====
    s = prs.slides.add_slide(blank)
    set_bg_gradient(s, RGBColor(0xC5, 0x22, 0x1F), RED)
    add_text(s, Inches(0.8), Inches(0.6), Inches(5), Inches(0.4),
             "Session 4", 16, color=RGBColor(0xFF, 0xCC, 0xCC), bold=True)
    add_text(s, Inches(0.8), Inches(2), Inches(11), Inches(1.5),
             "Model Security /\nModel Armor", 48, bold=True, color=WHITE)
    add_text(s, Inches(0.8), Inches(4.2), Inches(11), Inches(0.6),
             "Input/output screening, guardrails, and content safety", 22, color=RGBColor(0xFF, 0xCC, 0xCC))
    add_logo(s, RGBColor(0xFF, 0x99, 0x99))

    # ===== SLIDE 25: MODEL ARMOR =====
    s = prs.slides.add_slide(blank)
    add_text(s, Inches(0.8), Inches(0.3), Inches(10), Inches(0.8),
             "Model Armor — Content Safety Integration", 36, bold=True)
    add_image_safe(s, os.path.join(DIAGRAMS, "07_agent_armor.png"),
                   Inches(0.5), Inches(1.3), width=Inches(6))
    add_card(s, Inches(7), Inches(1.3), Inches(5.5), Inches(1.5),
             "Input Screening",
             "Prompt injection detection, jailbreak prevention, PII filtering before model call", RED)
    add_card(s, Inches(7), Inches(3.1), Inches(5.5), Inches(1.5),
             "Output Screening",
             "Harmful content filtering, hallucination flags, safety score thresholds", BLUE)
    add_card(s, Inches(7), Inches(4.9), Inches(5.5), Inches(1.5),
             "ADK Guardrail Callbacks",
             "before_model_callback and after_model_callback hooks integrated into agent lifecycle", GREEN)
    add_logo(s)

    # ===== SLIDE 26: CONSOLE — MODEL ARMOR =====
    s = prs.slides.add_slide(blank)
    set_bg(s, DARK)
    add_text(s, Inches(0.8), Inches(0.3), Inches(10), Inches(0.8),
             "Console: Model Armor", 32, bold=True, color=WHITE)
    add_image_safe(s, os.path.join(SCREENSHOTS, "session4_model_armor.png"),
                   Inches(0.8), Inches(1.3), width=Inches(11.5))
    add_logo(s, RGBColor(0x88, 0x88, 0x88))

    # ===== SLIDE 27: SUMMARY =====
    s = prs.slides.add_slide(blank)
    add_text(s, Inches(0.8), Inches(0.3), Inches(8), Inches(0.8),
             "Platform Summary", 42, bold=True)
    cards = [
        ("Build", ["ADK agents with LlmAgent", "FastMCP tool servers", "Multi-agent coordination"], BLUE),
        ("Deploy", ["Cloud Run (MCP servers)", "Agent Runtime (agents)", "One-command deployment"], GREEN),
        ("Govern", ["SPIFFE identity", "Agent Gateway (dual)", "Agent Registry"], YELLOW),
        ("Secure", ["Model Armor templates", "Input/output screening", "Guardrail callbacks"], RED),
        ("Evaluate", ["One-time eval", "Online monitors", "CI/CD eval gate"], BLUE),
        ("Optimize", ["GEPA algorithm", "Prompt evolution", "OTel observability"], GREEN),
    ]
    for i, (title, items, color) in enumerate(cards):
        col = i % 3
        row = i // 3
        x = Inches(0.8 + col * 4.1)
        y = Inches(1.5 + row * 2.8)
        shape = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, Inches(3.7), Inches(2.4))
        shape.fill.solid()
        shape.fill.fore_color.rgb = WHITE
        shape.line.color.rgb = color
        shape.line.width = Pt(2)
        tf = shape.text_frame
        tf.word_wrap = True
        tf.margin_left = Pt(14)
        tf.margin_top = Pt(10)
        p = tf.paragraphs[0]
        p.text = title
        p.font.size = Pt(20)
        p.font.bold = True
        p.font.color.rgb = color
        p.font.name = FONT
        for item in items:
            p2 = tf.add_paragraph()
            p2.text = "• " + item
            p2.font.size = Pt(14)
            p2.font.color.rgb = GRAY
            p2.font.name = FONT
            p2.space_before = Pt(4)
    add_logo(s)

    # ===== SLIDE 28: RESOURCES =====
    s = prs.slides.add_slide(blank)
    set_bg_gradient(s, DARK_BLUE, BLUE)
    add_text(s, Inches(0.8), Inches(0.6), Inches(5), Inches(0.4),
             "Resources", 16, color=RGBColor(0xCC, 0xDD, 0xFF), bold=True)
    add_text(s, Inches(0.8), Inches(1.3), Inches(11), Inches(1),
             "Get Started", 48, bold=True, color=WHITE)
    resources = [
        "Workshop repo:  github.com/jswortz/geap-tour",
        "Workshop guide:  docs/workshop_guide.md",
        "Agent Development Kit:  google.github.io/adk-docs",
        "MCP Protocol:  modelcontextprotocol.io",
        "Agent Platform:  cloud.google.com/agent-platform",
    ]
    add_bullet_list(s, Inches(0.8), Inches(2.8), Inches(10), Inches(3),
                    resources, font_size=24, color=RGBColor(0xEE, 0xEE, 0xFF))
    add_text(s, Inches(0.8), Inches(6.0), Inches(11), Inches(0.5),
             "Thank you!", 22, color=RGBColor(0xAA, 0xBB, 0xDD), align=PP_ALIGN.LEFT)
    add_logo(s, RGBColor(0x88, 0x99, 0xCC))

    prs.save(OUTPUT)
    print(f"Saved {len(prs.slides)} slides to {OUTPUT}")
    print(f"File size: {os.path.getsize(OUTPUT) / 1024:.0f} KB")


if __name__ == "__main__":
    build_deck()
