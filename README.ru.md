# ffvd — загрузчик видео для Firefox

[English](README.md) · **Русский**

Видео, клипы, рилсы и шортсы с YouTube, X/Twitter, Instagram, TikTok, VK, Reddit,
Twitch, Vimeo и [1800+ других сайтов](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md).

Устройство: расширение (`extension/`) ничего не качает само. Через
[native messaging](https://developer.mozilla.org/docs/Mozilla/Add-ons/WebExtensions/Native_messaging)
оно передаёт ссылку локальному помощнику (`host/ffvd_host.py`), а тот запускает
`yt-dlp`. Никаких сторонних серверов и телеметрии нет. Загрузки идут в фоне и
продолжаются, даже если закрыть попап или Firefox.

## Установка через ИИ-агента

Вставьте в Claude Code, Codex, Cursor, Gemini CLI или другого агента:

```text
Install the ffvd Firefox video downloader on this machine by following
https://github.com/pararti/ffvd/blob/main/docs/agent-install.md
Ask me before any sudo command.
```

Агент сам поставит зависимости и помощник, скачает подписанное расширение и проверит
контрольную сумму. От вас нужно только подтвердить установку в Firefox. В конце агент
запускает `python3 doctor.py`, которая проверяет всю установку.

## Установка

```sh
sudo pacman -S yt-dlp deno ffmpeg   # deno нужен yt-dlp для YouTube
./install.sh                        # помощник + манифест в ~/.mozilla, без sudo
```

Расширение в обычном Firefox нужно либо подписать, либо загрузить временно:

- **Временно (для проверки):** `about:debugging#/runtime/this-firefox` →
  «Загрузить временное дополнение» → `extension/manifest.json`. Пропадёт после
  перезапуска Firefox.
- **Постоянно:** подписать бесплатно через AMO как *unlisted* (в каталоге не
  публикуется, проверяется автоматически):
  1. Получить ключи: <https://addons.mozilla.org/developers/addon/api/key/>
  2. `AMO_JWT_ISSUER=... AMO_JWT_SECRET=... npm run sign`
  3. `about:addons` → ⚙ → «Установить дополнение из файла» → `dist/*.xpi`

## Использование

- **Кнопка на панели:** подставляет ссылку открытой вкладки, показывает название и
  доступное качество. Выберите качество (до 4K, mp3/m4a) и нажмите «Скачать».
- **Правый клик** по ссылке, видео или странице → «Скачать видео (ffvd)». На X
  удобнее всего кликнуть по времени публикации твита: это ссылка на пост.
- **«Использовать вход из Firefox»:** yt-dlp берёт ваши куки Firefox
  (`--cookies-from-browser firefox`). Без этого YouTube часто отвечает «Sign in to
  confirm you're not a bot», а X, Instagram и Vimeo не отдают часть видео. Куки
  остаются на компьютере. При ошибке входа в попапе появляется кнопка повтора.
- Файлы сохраняются в «Загрузки» (меняется в настройках попапа).
- Интерфейс на русском или английском — по языку Firefox.

Если сайт перестал работать, обычно помогает обновить yt-dlp: `sudo pacman -Syu yt-dlp`.

## Разработка

```sh
npm test     # тесты помощника (с поддельным yt-dlp)
npm run lint # web-ext lint
```

Настройки помощника: `FFVD_YTDLP` или `~/.config/ffvd/config.json`
(`{"ytdlp": "/путь/к/yt-dlp"}`). Состояние задач лежит в `~/.local/state/ffvd/jobs/`.
Удаление: `./uninstall.sh`.
