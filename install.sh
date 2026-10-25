#!/usr/bin/env bash
# Installs the ffvd native messaging host for Firefox (current user only, no sudo).
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXT_ID="ffvd@apararti.local"
HOST_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/ffvd"
MANIFEST_DIR="$HOME/.mozilla/native-messaging-hosts"

install -Dm755 "$SRC_DIR/host/ffvd_host.py" "$HOST_DIR/ffvd_host.py"
mkdir -p "$MANIFEST_DIR"
cat > "$MANIFEST_DIR/ffvd.json" <<EOF
{
  "name": "ffvd",
  "description": "ffvd video downloader helper (yt-dlp)",
  "path": "$HOST_DIR/ffvd_host.py",
  "type": "stdio",
  "allowed_extensions": ["$EXT_ID"]
}
EOF

echo "Helper installed: $HOST_DIR/ffvd_host.py"
echo "Manifest:         $MANIFEST_DIR/ffvd.json"

missing=()
command -v yt-dlp >/dev/null || missing+=(yt-dlp)
command -v ffmpeg >/dev/null || missing+=(ffmpeg)
command -v deno >/dev/null || missing+=(deno)
if ((${#missing[@]})); then
  echo
  echo "Missing packages: ${missing[*]}"
  echo "  sudo pacman -S ${missing[*]}"
  echo "(yt-dlp needs deno for YouTube; node is used as a fallback if present)"
fi
