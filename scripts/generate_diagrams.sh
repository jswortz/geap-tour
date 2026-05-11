#!/usr/bin/env bash
# Generate GEAP workshop architecture diagrams using Paper Banana.
#
# Prerequisites:
#   pip install paperbanana
#   Set GOOGLE_API_KEY or OPENAI_API_KEY in your environment (or .env file).
#
# Usage:
#   ./scripts/generate_diagrams.sh            # default: optimize + 3 iterations
#   ./scripts/generate_diagrams.sh --auto     # loop until critic is satisfied
#
# Output:
#   docs/diagrams/outputs/batch_<timestamp>/   (individual diagrams + composite)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST="${REPO_ROOT}/docs/diagrams/manifest.yaml"
OUTPUT_DIR="${REPO_ROOT}/docs/diagrams/outputs"

if [ ! -f "${MANIFEST}" ]; then
  echo "ERROR: Manifest not found at ${MANIFEST}" >&2
  exit 1
fi

# Ensure output directory exists
mkdir -p "${OUTPUT_DIR}"

echo "=== Generating GEAP workshop diagrams ==="
echo "Manifest:   ${MANIFEST}"
echo "Output dir: ${OUTPUT_DIR}"
echo ""

paperbanana batch \
  --manifest "${MANIFEST}" \
  --output-dir "${OUTPUT_DIR}" \
  --optimize \
  --format png \
  "$@"

echo ""
echo "=== Done ==="
echo "Diagrams saved to: ${OUTPUT_DIR}"
echo ""
echo "To generate a human-readable report:"
echo "  paperbanana batch-report --batch-dir ${OUTPUT_DIR}/batch_* --format markdown"
