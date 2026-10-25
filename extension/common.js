"use strict";

const HOST = "ffvd";

const PRESETS = [
  { id: "best", label: "Лучшее качество", height: Infinity },
  { id: "2160", label: "4K (2160p)", height: 2160 },
  { id: "1440", label: "1440p", height: 1440 },
  { id: "1080", label: "1080p", height: 1080 },
  { id: "720", label: "720p", height: 720 },
  { id: "480", label: "480p", height: 480 },
  { id: "360", label: "360p", height: 360 },
  { id: "mp3", label: "Только аудио (mp3)", audio: true },
  { id: "m4a", label: "Только аудио (m4a)", audio: true },
];

const DEFAULT_SETTINGS = { preset: "best", cookies: false, outdir: "" };

async function getSettings() {
  return { ...DEFAULT_SETTINGS, ...(await browser.storage.local.get(DEFAULT_SETTINGS)) };
}

/** Send one command to the native host; throws Error with a readable message. */
async function host(cmd, params = {}) {
  let res;
  try {
    res = await browser.runtime.sendNativeMessage(HOST, { cmd, ...params });
  } catch (e) {
    throw new Error("Нет связи с локальным помощником ffvd. Запустите install.sh. (" + e.message + ")");
  }
  if (!res || !res.ok) throw new Error((res && res.error) || "Неизвестная ошибка");
  return res;
}

function isHttpUrl(url) {
  return typeof url === "string" && /^https?:\/\//i.test(url);
}
