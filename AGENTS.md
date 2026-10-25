# AGENTS.md

Instructions for AI coding agents working in this repository. Humans: see README.md.

**Installing ffvd for a user** (rather than developing it)? Follow
[docs/agent-install.md](docs/agent-install.md) and stop reading here.

## What this is

ffvd is a Firefox extension that downloads videos via a local yt-dlp. It has two
parts that talk over [native messaging](https://developer.mozilla.org/docs/Mozilla/Add-ons/WebExtensions/Native_messaging):

- `extension/`: Manifest V3 WebExtension. No build step; plain JS, HTML and CSS.
  - `common.js`: shared by popup and background. Holds the `host()` RPC to the
    helper, `t()` for i18n, presets and settings.
  - `popup.*`: the toolbar UI. `background.js`: context menu.
  - `_locales/{en,ru}/messages.json`: every user-visible string.
- `host/ffvd_host.py`: native helper, Python 3 standard library only. It handles a
  single JSON command per framed message (`ping`, `info`, `download`, `jobs`,
  `cancel`, `clear`, `open`). Downloads run as detached `--worker` processes that
  write state to `~/.local/state/ffvd/jobs/<id>.json`.
- `install.sh`, `uninstall.sh`: register and remove the helper for the current user.
- `doctor.py`: installation health check (`--json` for machines).
- `sign.sh`: signs the extension on AMO (unlisted) into `dist/`.

## Commands

```sh
npm test            # helper tests: python3 -m unittest discover -s host (fake yt-dlp, no network)
npm run lint        # web-ext lint on extension/; must report 0 errors and 0 warnings
python3 doctor.py   # is everything installed on this machine?
./install.sh        # re-install the helper after changing host/ffvd_host.py
npm run run         # throwaway Firefox profile with the extension loaded
```

Run `npm test` and `npm run lint` before every commit.

## Rules

- **No secrets in the repo.** AMO API keys live in `~/.config/ffvd/amo.env`,
  outside the repo. Never print them, never commit them, never put them on a
  command line that ends up in shell history. `.gitignore` already blocks `*.env`,
  `dist/` and `.amo-upload-uuid`.
- **Never handle users' cookies yourself.** Only yt-dlp's
  `--cookies-from-browser firefox` reads them, and only when the user opts in.
- **Helper security invariants** (covered by tests; keep them): only `http(s)` URLs;
  the URL always goes after `--`; presets come from the `PRESETS` whitelist; job
  IDs must be 32 hex characters; `open` only opens paths recorded in a job; never
  `shell=True`.
- **Helper stays stdlib-only** and must not print anything to stdout except framed
  messages, because stdout is the native messaging channel.
- **i18n:** never hardcode user-visible text in `extension/`. Add the key to *both*
  `_locales/en` and `_locales/ru`. Use `t("key", ...subs)` in JS and `data-i18n`,
  `data-i18n-placeholder` or `data-i18n-title` in HTML. Helper errors use
  `HostError("<code>", "English text")`; add a matching `err_<code>` key.
- **Versions must match** in `extension/manifest.json`, `package.json` and
  `VERSION` in `host/ffvd_host.py`. A test enforces this.
- **The extension ID** `ffvd@apararti.local` is registered on AMO for this repo.
  Forks that sign their own build must change it in `extension/manifest.json` and
  `EXT_ID` in `install.sh`.
- Code comments and commit messages are in English. Keep diffs small and in the
  style of the surrounding code.

## Releasing (maintainer only; needs AMO keys)

1. Bump the version in the three places above. AMO never signs the same version twice.
2. `npm test && npm run lint`, then commit.
3. `npm run sign`, then rename the result:
   `mv dist/*-X.Y.Z.xpi dist/ffvd-X.Y.Z.xpi && cp dist/ffvd-X.Y.Z.xpi dist/ffvd.xpi`
4. `(cd dist && sha256sum ffvd-X.Y.Z.xpi ffvd.xpi > SHA256SUMS)`
5. `git tag -a vX.Y.Z -m "ffvd X.Y.Z" && git push origin main --follow-tags`
6. `gh release create vX.Y.Z dist/ffvd-X.Y.Z.xpi dist/ffvd.xpi dist/SHA256SUMS --title "ffvd X.Y.Z" --notes "..."`

Always attach `ffvd.xpi` and `SHA256SUMS`: docs/agent-install.md downloads them
from `releases/latest/download/`.
