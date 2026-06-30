---
name: gcp-architecture-slides
description: Create branded, high-resolution Google Cloud Platform architecture slides, diagrams, and vector assets that are brand perfect, pixel perfect, and pass enterprise architecture reviews. Use this skill when the user requests slide designs, architectural topology diagrams, flowcharts, or visual mockups of Google Cloud environments using Gemini Image Generation.
---

# GCP Architecture Slides & Diagrams Generator

Use this skill to design and generate high-fidelity, professional GCP architecture diagrams and presentation slides. It leverages the `generate_image` tool to produce clean, vector-style flat 2D visuals conforming to Google Cloud's official branding.

---

## 🎨 Visual Identity & Brand Guidelines

To ensure generated images look professional and ready for executive-level architecture reviews:

1. **Style**: Flat, clean 2D vector style. Avoid 3D perspective, glossy gradients, shadows, or photo-realistic renders.
2. **Colors**: Google Cloud palette:
   - Primary: Slate Grey (`#3c4043`), Google Blue (`#1a73e8`), Charcoal.
   - Accents: Green, Yellow, Red (only for specific highlights/indicators).
   - Background: Clean white (`#ffffff`) or extremely light grey (`#f8f9fa`) for readability.
3. **Icons**: Use flat, modern geometric shapes representing GCP services (e.g. hexagonal compute shapes, circular database cylinders, rectangular gateway boxes).
4. **Layout**: Symmetric, left-to-right or top-to-bottom flow. Clear separation of layers (Ingress, Runtime, Storage, Governance, Observability).
5. **No Device Frames**: Unless explicitly requested, always generate only the architecture diagram canvas itself. No laptops, phones, tablets, or generic mock presentation slides.

---

## ✍️ Prompt Engineering Guide for GCP Architecture

When calling the `generate_image` tool, follow these structures for the `Prompt` argument.

### 1. Ingress & Routing Diagrams
> **Prompt Pattern**: `Flat 2D vector architecture diagram showing Google Cloud network ingress. A user request flows from left to right through: Ingress Gateway (clean blue box), External HTTP(S) Load Balancer (circle icon), and Cloud Armor (shield icon), entering a secure VPC. Minimal flat design, corporate grey and blue color palette, clean white background, high resolution, professional, clear topology.`

### 2. Multi-Agent & Orchestration Pipelines
> **Prompt Pattern**: `Flat 2D vector flowchart of a multi-agent AI system on Google Cloud. Left layer shows User Request, middle layer shows Agent Coordinator (circle) orchestrating Travel Agent and Expense Agent sub-agents. Right layer shows FastMCP tool servers deployed on Cloud Run. Clean geometric lines, flat icons, minimal corporate aesthetic, white background.`

### 3. Data Processing & Analytics Pipelines
> **Prompt Pattern**: `Flat 2D vector data engineering architecture diagram. Flow from left to right: Pub/Sub (ingest circular node) -> Dataflow (transformation pipeline) -> BigQuery (data warehouse cylinder icon) -> Looker Studio (dashboard report chart). Clean flat icons, Google Cloud brand colors, professional, white background.`

### 4. GKE Enterprise Container Layouts
> **Prompt Pattern**: `Flat 2D vector system diagram showing Google Kubernetes Engine (GKE) cluster architecture. Inside a large VPC box: Control Plane, multiple Node Pools, pods running microservices, connected to Cloud SQL. Minimal design, flat corporate style, white background.`

---

## 🛠️ Execution Workflow

1. **Understand Requirements**: Clarify the specific GCP services involved, flow direction, and slide layout.
2. **Select Prompt Template**: Customize one of the prompt patterns above with the user's specific resources.
3. **Call `generate_image`**:
   - Provide a descriptive `ImageName` (e.g. `gke_enterprise_architecture`, `data_pipeline_flow`).
   - Run the tool to generate the high-res PNG image.
4. **Self-Evaluate Output**: Grade the generated diagram against the [Self-Evaluation Rubric](references/evaluation.md). If the score is 8/10 or below, adjust the prompt and regenerate.
5. **Link in Presentation**: Link the generated image in a markdown slide deck or PPTX presentation file.
