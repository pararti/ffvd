# Installing ffvd — guide for AI agents

This is a step-by-step runbook for an AI coding agent (Claude Code, Codex, Cursor,
Gemini CLI, Copilot, Aider, …) that is asked to install ffvd on a user's machine.
Humans can follow it too.

**What gets installed:**
1. System packages: `yt-dlp`, `ffmpeg` and a JS runtime (`deno`, or `node` ≥ 20).
2. The native helper, user-local: `~/.local/share/ffvd/` plus
   `~/.mozilla/native-messaging-hosts/ffvd.json`.
3. The signed Firefox add-on `ffvd.xpi`.

At the end, `python3 doctor.py` must report `ffvd is ready.`

## Ground rules

- **Ask before using `sudo`.** Show the exact command and let the user run it or
  approve it. Everything else in this guide is user-local and needs no root.
- **The user must confirm the add-on install in Firefox.** Firefox shows an install
  prompt that only a human can accept. Do not try to bypass it. Never disable
  signature checks (`xpinstall.signatures.required`), and never copy files into
  Firefox profile folders.
- **Never read, copy or ask for the user's browser cookies or passwords.** ffvd's
  "Use Firefox login" option is handled locally by yt-dlp when the user enables it.
- **Verify the checksum** of `ffvd.xpi` before installing it (step 5).
- Prefer `python3 doctor.py --json` when you need to parse the state. Every check
  has `status` set to `ok`, `warn` or `fail`, plus a `hint` that says what to do.

## Step 1. Check the platform

```sh
uname -s            # must print: Linux
command -v firefox  # must print a path
```

- ffvd supports **Linux only** for now. On macOS or Windows, stop and tell the user.
- **Flatpak Firefox** (`flatpak info org.mozilla.firefox` succeeds and there is no
  `firefox` in `PATH`) cannot start native helpers. Stop and suggest the distro or
  Mozilla build of Firefox.
- **Snap Firefox** (Ubuntu's default) works only if `xdg-desktop-portal` is running.
  Continue, but mention it if the helper check fails later.

## Step 2. Get the source

If the user did not choose a location, use `~/.local/src/ffvd`:

```sh
git clone https://github.com/pararti/ffvd.git ~/.local/src/ffvd
cd ~/.local/src/ffvd
python3 doctor.py   # shows what is still missing; failures are expected at this point
```

If `git` is not available, download and extract
`https://github.com/pararti/ffvd/archive/refs/heads/main.tar.gz` instead.

## Step 3. Install dependencies (needs `sudo`, so ask first)

Detect the distro with `. /etc/os-release && echo "$ID $ID_LIKE"`.

| Distro | Command |
| --- | --- |
| Arch, Manjaro, EndeavourOS | `sudo pacman -S --needed yt-dlp deno ffmpeg` |
| Fedora | `sudo dnf install yt-dlp ffmpeg-free` (then a JS runtime, see below) |
| Debian, Ubuntu, Mint | `sudo apt install ffmpeg pipx` and then, without sudo, `pipx install "yt-dlp[default]"` |
| Other | `ffmpeg` from the distro, yt-dlp via `pipx install "yt-dlp[default]"` |

Notes:

- **Debian and Ubuntu:** do not use the `yt-dlp` apt package. It is usually too old
  for YouTube. pipx installs a current version into `~/.local/bin`, which ffvd
  checks even when Firefox's `PATH` does not include it.
- **JS runtime:** if neither `deno` nor `node` ≥ 20 is installed, YouTube downloads
  fail. Other sites still work. Options, best first:
  1. the distro package (`deno` or `nodejs`), if it is recent enough;
  2. the official deno installer, **only with the user's consent**, because it pipes
     a script into the shell: `curl -fsSL https://deno.land/install.sh | sh`. It
     installs into `~/.deno/bin`, which ffvd checks.
- yt-dlp also needs its `yt-dlp-ejs` component for YouTube. The Arch package,
  `pipx install "yt-dlp[default]"` and the official standalone binary all include it.

## Step 4. Install the native helper (no sudo)

```sh
./install.sh
```

This is idempotent, so it is safe to re-run. It prints which packages are still
missing.

## Step 5. Download the signed add-on and verify it

```sh
mkdir -p dist && cd dist
curl -fLO https://github.com/pararti/ffvd/releases/latest/download/ffvd.xpi
curl -fLO https://github.com/pararti/ffvd/releases/latest/download/SHA256SUMS
sha256sum -c --ignore-missing SHA256SUMS   # must print: ffvd.xpi: OK
cd ..
```

If the checksum does not match, stop. Delete the file and do not install it.

Alternatively, with GitHub CLI:
`gh release download --repo pararti/ffvd --pattern 'ffvd.xpi' --pattern SHA256SUMS --dir dist`.

## Step 6. Install the add-on in Firefox (the user confirms)

```sh
firefox dist/ffvd.xpi
```

This opens Firefox (or a new tab in the running Firefox) with an install prompt.
Tell the user:

> Firefox is asking to add **ffvd**. Click **Add**, then optionally pin the red
> download button to the toolbar via the puzzle-piece menu.

If the prompt does not appear, the user can do it manually: open `about:addons` →
⚙ → *Install Add-on From File…* → `dist/ffvd.xpi`.

Installing a newer `ffvd.xpi` over an older one upgrades it and keeps the settings.

## Step 7. Verify

```sh
python3 doctor.py
```

All checks must be `ok` (a `warn` on the JS runtime is acceptable if the user does
not need YouTube). Last line: `ffvd is ready.` Then ask the user to open any video
page and click the ffvd button.

## Troubleshooting

| Symptom (popup or doctor) | Fix |
| --- | --- |
| "Cannot reach the local ffvd helper" | Re-run `./install.sh`, then restart Firefox. |
| "yt-dlp is not installed" | Step 3. If yt-dlp is in a non-standard place, create `~/.config/ffvd/config.json` containing `{"ytdlp": "/full/path/to/yt-dlp"}`. |
| "Sign in to confirm you're not a bot" (YouTube) | The user ticks **Use Firefox login (cookies)** in the popup or clicks the retry button. They must be logged in to YouTube in Firefox. |
| A site worked before and now fails | Update yt-dlp: `sudo pacman -Syu yt-dlp`, `pipx upgrade yt-dlp`, or the distro's equivalent. |
| doctor: add-on `installed but disabled` | The user enables ffvd in `about:addons`. |
| doctor: add-on `(temporary)` | It was loaded via `about:debugging` and will vanish on restart. Do step 6. |
| doctor: `Update available` | Repeat steps 5 and 6 to install the latest release. |

## Updating

```sh
cd ~/.local/src/ffvd && git pull && ./install.sh
```

Then repeat steps 5–7.

## Uninstalling

```sh
cd ~/.local/src/ffvd && ./uninstall.sh   # helper and job state; downloaded videos are kept
```

The user removes the add-on in `about:addons`. The source folder can then be deleted.
