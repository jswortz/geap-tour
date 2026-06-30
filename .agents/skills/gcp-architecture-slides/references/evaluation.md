# GCP Architecture Diagram Self-Evaluation Rubric

Use this checklist to grade generated architecture diagrams before presenting them to the user. A diagram must score at least **9/10** on this rubric to be deemed ready for an enterprise architecture review or public publication.

---

## 📐 1. Visual Geometry & Layout (Weight: 3)
* [ ] **Grid Alignment**: Are all service blocks aligned horizontally and vertically along a clean grid?
* [ ] **Spacing Consistency**: Is the spacing between adjacent nodes uniform across the diagram?
* [ ] **Flow Direction**: Is the request or data flow logical and sequential (either left-to-right or top-to-bottom)?
* [ ] **Connector Arrows**: Do all connector lines have clear arrowheads that point in the direction of the flow? Do they attach cleanly to the node borders without overlapping?

## 🎨 2. Color Palette & Contrast (Weight: 2)
* [ ] **Background Contrast**: Is the background color clean white (`#ffffff`) or extremely light grey (`#f8f9fa`)?
* [ ] **Brand Palette**: Does the diagram restrict itself to official GCP colors (GCP Blue, Slate Grey, Charcoal)?
* [ ] **Accent Restraint**: Are warning colors (red, yellow) reserved strictly for alert conditions, thresholds, or status updates? No generic boxes should use red or yellow.

## ✍️ 3. Typography & Text Hygiene (Weight: 3)
* [ ] **No Overlaps**: Is all text placed clearly outside icons and lines? No text should overlap or be cut off by lines.
* [ ] **Horizontal Orientation**: Is all text oriented horizontally? No vertical or rotated labels.
* [ ] **Correct Product Names**: Are Google Cloud products named correctly according to official branding (e.g. "Cloud Logging", "Cloud Monitoring", "Cloud Run", "Artifact Registry")? Avoid legacy names (e.g. "Stackdriver", "GCR").
* [ ] **Minimalism**: Is text restricted to short labels and clean titles? Avoid long sentences or paragraphs inside the diagram.

## 🔍 4. Icon Authenticity (Weight: 2)
* [ ] **Flat 2D Style**: Are all service icons flat geometric shapes? No 3D perspectives or realistic textures.
* [ ] **Semantic Accuracy**: Does each icon match its service category (e.g. compute shapes for Cloud Run/GKE, storage cylinders for BigQuery/Cloud SQL, shield shapes for Cloud Armor)?

---

## 📈 Scoring & Action
- **10/10**: Perfect. Ready for public documentation.
- **9/10**: Good. Standard layout with minor spacing or label alignment tweaks.
- **8/10 or below**: **REJECTED**. The agent must refine the prompt and regenerate the image, specifying the failed criteria as corrections in the prompt.
