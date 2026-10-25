#!/usr/bin/env bash
# Signs the extension on addons.mozilla.org as "unlisted" (not published) and puts the .xpi into dist/.
# Keys are read from ~/.config/ffvd/amo.env:
#   AMO_JWT_ISSUER=user:12345:678
#   AMO_JWT_SECRET=...
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEYS="${XDG_CONFIG_HOME:-$HOME/.config}/ffvd/amo.env"

if [[ -z "${AMO_JWT_ISSUER:-}" || -z "${AMO_JWT_SECRET:-}" ]]; then
  if [[ ! -f "$KEYS" ]]; then
    echo "No API keys. Create $KEYS with AMO_JWT_ISSUER and AMO_JWT_SECRET" >&2
    echo "Get keys at https://addons.mozilla.org/developers/addon/api/key/" >&2
    exit 1
  fi
  set -a; source "$KEYS"; set +a
fi

cd "$SRC_DIR"
npx --yes web-ext@8 sign --channel unlisted \
  --source-dir extension --artifacts-dir dist \
  --api-key "$AMO_JWT_ISSUER" --api-secret "$AMO_JWT_SECRET"
echo
ls -1 dist/*.xpi
