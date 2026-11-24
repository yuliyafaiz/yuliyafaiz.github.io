#!/usr/bin/env bash
# Symlink the Creative Studio node package into a ComfyUI installation.
# Usage: ./scripts/install_nodes.sh /path/to/ComfyUI   [--copy]
set -euo pipefail
COMFY="${1:-}"
[ -n "$COMFY" ] && [ -d "$COMFY/custom_nodes" ] || { echo "Usage: $0 /path/to/ComfyUI [--copy]  (folder must contain custom_nodes/)"; exit 1; }
SRC="$(cd "$(dirname "$0")/.." && pwd)/custom_nodes/comfyui-creative-studio-nodes"
DEST="$COMFY/custom_nodes/comfyui-creative-studio-nodes"
if [ -e "$DEST" ] || [ -L "$DEST" ]; then
  echo "Already present: $DEST"; ls -ld "$DEST"; exit 0
fi
if [ "${2:-}" = "--copy" ]; then cp -R "$SRC" "$DEST"; else ln -s "$SRC" "$DEST"; fi
echo "Installed → $DEST"
echo "Restart ComfyUI; the nodes appear under the 'Creative Studio' category."
