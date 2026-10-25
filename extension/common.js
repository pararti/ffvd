"use strict";

const HOST = "ffvd";

const PRESETS = [
  { id: "best", msg: "presetBest", height: Infinity },
  { id: "2160", label: "4K (2160p)", height: 2160 },
  { id: "1440", label: "1440p", height: 1440 },
  { id: "1080", label: "1080p", height: 1080 },
  { id: "720", label: "720p", height: 720 },
  { id: "480", label: "480p", height: 480 },
  { id: "360", label: "360p", height: 360 },
  { id: "mp3", msg: "presetMp3", audio: true },
  { id: "m4a", msg: "presetM4a", audio: true },
];

const DEFAULT_SETTINGS = { preset: "best", cookies: false, outdir: "" };

/** Localized string from _locales; `subs` fill $1, $2, … */
function t(key, ...subs) {
  return browser.i18n.getMessage(key, subs.map(String)) || key;
}

function presetLabel(preset) {
  return preset.msg ? t(preset.msg) : preset.label;
}

/** Translate a helper error code, falling back to the helper's (English) text. */
function errorText(code, fallback) {
  return (code && browser.i18n.getMessage("err_" + code)) || fallback || t("errUnknown");
}

/** Fill elements marked with data-i18n, data-i18n-placeholder and data-i18n-title. */
function localizePage() {
  document.documentElement.lang = browser.i18n.getUILanguage();
  for (const el of document.querySelectorAll("[data-i18n]")) el.textContent = t(el.dataset.i18n);
  for (const el of document.querySelectorAll("[data-i18n-placeholder]")) el.placeholder = t(el.dataset.i18nPlaceholder);
  for (const el of document.querySelectorAll("[data-i18n-title]")) el.title = t(el.dataset.i18nTitle);
}

async function getSettings() {
  return { ...DEFAULT_SETTINGS, ...(await browser.storage.local.get(DEFAULT_SETTINGS)) };
}

/** Send one command to the native host; throws Error with a readable message. */
async function host(cmd, params = {}) {
  let res;
  try {
    res = await browser.runtime.sendNativeMessage(HOST, { cmd, ...params });
  } catch (e) {
    throw new Error(t("errNoHost", e.message));
  }
  if (!res || !res.ok) throw new Error(res ? errorText(res.code, res.error) : t("errUnknown"));
  return res;
}

function isHttpUrl(url) {
  return typeof url === "string" && /^https?:\/\//i.test(url);
}
