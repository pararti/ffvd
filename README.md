# ffvd — Firefox Video Downloader

**English** · [Русский](README.ru.md)

Download videos, clips, reels and shorts from YouTube, X/Twitter, Instagram, TikTok,
VK, Reddit, Twitch, Vimeo and [1800+ other sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)
right from Firefox.

## How it works

The extension (`extension/`) does not download anything itself. It hands the URL over
[native messaging](https://developer.mozilla.org/docs/Mozilla/Add-ons/WebExtensions/Native_messaging)
to a small local helper (`host/ffvd_host.py`, Python standard library only), which
runs [yt-dlp](https://github.com/yt-dlp/yt-dlp).

- No third-party servers and no telemetry. Everything runs on your machine.
- Downloads run as detached background jobs, so they keep going after you close the
  popup or even Firefox.
- The helper accepts only `http(s)` URLs, a fixed set of quality presets and job IDs
  it created itself. It never runs a shell, and the URL is always passed after `--`.

## Features

- **Toolbar popup:** picks up the current tab's URL and shows the title, thumbnail and
  available quality. Choose anything from 360p to 4K, or audio only (mp3/m4a). It
  shows progress and speed, and lets you cancel, open the file or open the folder.
- **Context menu:** right-click a link, video or page → *Download video (ffvd)*.
  On X, right-click the post's timestamp, which links to the post.
- **Playlists:** download a whole playlist into its own folder.
- **Use Firefox login (cookies):** passes `--cookies-from-browser firefox` to yt-dlp.
  YouTube often answers *"Sign in to confirm you're not a bot"* without it, and some
  X, Instagram and Vimeo videos need a login. The cookies never leave your computer.
  When a login error appears, the popup offers a one-click retry.
- Desktop notification when a download finishes.
- UI in English and Russian, following your Firefox language.

## Installation (Linux)

1. Install the dependencies. `deno` is the JS runtime yt-dlp needs for YouTube;
   if `deno` is missing, ffvd falls back to `node`.

   ```sh
   # Arch / Manjaro
   sudo pacman -S yt-dlp deno ffmpeg
   ```

2. Install the native helper for the current user (no root needed):

   ```sh
   ./install.sh
   ```

   This copies the helper to `~/.local/share/ffvd/` and registers it in
   `~/.mozilla/native-messaging-hosts/ffvd.json`.

3. Load the extension. Release Firefox only installs signed add-ons, so you have two
   options:

   - **Try it out:** open `about:debugging#/runtime/this-firefox` →
     *Load Temporary Add-on…* → `extension/manifest.json`. It is removed when
     Firefox restarts.
   - **Permanent:** sign it yourself, for free, as an *unlisted* add-on. It is not
     published on AMO and is reviewed automatically.
     1. Create API keys at <https://addons.mozilla.org/developers/addon/api/key/>.
     2. Put them into `~/.config/ffvd/amo.env` and run `chmod 600` on it:
        ```
        AMO_JWT_ISSUER=user:12345:678
        AMO_JWT_SECRET=...
        ```
     3. Change `browser_specific_settings.gecko.id` in `extension/manifest.json` and
        `EXT_ID` in `install.sh` to your own ID (e.g. `ffvd@yourname`), because
        add-on IDs are unique on AMO. Then re-run `./install.sh`.
     4. Run `npm run sign`, then go to `about:addons` → ⚙ → *Install Add-on From File…*
        → `dist/*.xpi`.

   Bump `version` in `extension/manifest.json` before signing again, since AMO never
   signs the same version twice.

If a site stops working, update yt-dlp first (`sudo pacman -Syu yt-dlp`). Sites
change often, and yt-dlp keeps up.

## Configuration

| What | Where |
| --- | --- |
| Download folder, default quality, cookies | Popup → *Settings* (stored in the extension) |
| Custom yt-dlp command | `FFVD_YTDLP` env var or `~/.config/ffvd/config.json`: `{"ytdlp": "/path/to/yt-dlp"}` |
| Job state | `~/.local/state/ffvd/jobs/` |

By default, files go to your XDG *Downloads* folder.

## Development

```sh
npm test       # helper tests (against a fake yt-dlp, no network)
npm run lint   # web-ext lint
npm run run    # start a clean Firefox with the extension loaded
```

Layout:

```
extension/   WebExtension (Manifest V3): popup, context menu, background
  _locales/  UI translations (en, ru)
host/        native messaging helper + tests
install.sh   registers the helper for Firefox
sign.sh      signs the extension on AMO (unlisted)
```

## Translations

UI strings live in `extension/_locales/<lang>/messages.json`. To add a language, copy
`en/messages.json` to a new folder named with the
[locale code](https://developer.mozilla.org/docs/Mozilla/Add-ons/WebExtensions/Internationalization)
(e.g. `de`), translate the `message` values and open a pull request. Keep `$1`
placeholders as they are. Errors from the helper arrive as codes and are translated
via the `err_<code>` keys.

## Uninstall

```sh
./uninstall.sh   # removes the helper and job state; downloaded files are kept
```

Then remove the add-on in `about:addons`.

## Legal

ffvd is a front-end for yt-dlp. Only download content you have the right to download,
and respect the terms of service of the sites you use.

## License

[MIT](LICENSE)
