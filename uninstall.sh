#!/usr/bin/env bash
# Removes the ffvd native host. Downloaded videos are not touched.
set -euo pipefail

rm -f "$HOME/.mozilla/native-messaging-hosts/ffvd.json"
rm -rf "${XDG_DATA_HOME:-$HOME/.local/share}/ffvd"
rm -rf "${XDG_STATE_HOME:-$HOME/.local/state}/ffvd"
echo "ffvd helper removed. Remove the add-on itself in about:addons."
