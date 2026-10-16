#!/usr/bin/env bash
# Renders every 3D shot. PY = a Python that has `bpy` (pip install bpy==5.2.2).
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-python3}
RES=${RES:-720x1280}
SAMPLES=${SAMPLES:-20}
for s in boring thumb glass_macro cap_macro label_macro whip drop sweep hero; do
  echo "== $s"
  "$PY" scripts/render_product.py "$s" --res "$RES" --samples "$SAMPLES" 2>&1 | grep -E "Saved|Error|Traceback" || true
done
echo DONE
