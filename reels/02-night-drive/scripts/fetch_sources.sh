#!/usr/bin/env bash
# Download the Mixkit source clips into source/ (they are not committed: ~650 MB of 4K).
# Mixkit License: free for commercial and personal use, no attribution required.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p source
ids=$(python3 -c "import sys; sys.path.insert(0,'scripts'); import timeline as T; print(' '.join(T.CLIPS))")
for id in $ids; do
  [ -s "source/$id.mp4" ] && continue
  for r in 2160 1080 720; do
    if curl -sf -m 600 -o "source/$id.mp4" "https://assets.mixkit.co/videos/$id/$id-$r.mp4"; then
      echo "$id ($r)"; break
    fi
  done
done
