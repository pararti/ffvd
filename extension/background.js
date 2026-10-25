"use strict";

const MENU_PRESETS = ["best", "1080", "720", "mp3"];

browser.runtime.onInstalled.addListener(() => {
  browser.contextMenus.removeAll();
  browser.contextMenus.create({
    id: "ffvd",
    title: t("menuDownload"),
    contexts: ["link", "video", "audio", "page"],
  });
  for (const id of MENU_PRESETS) {
    browser.contextMenus.create({
      id: "ffvd:" + id,
      parentId: "ffvd",
      title: presetLabel(PRESETS.find((p) => p.id === id)),
      contexts: ["link", "video", "audio", "page"],
    });
  }
});

/** Pick what yt-dlp should get: a link, a direct media file, or the page itself. */
function targetUrl(info) {
  if (isHttpUrl(info.linkUrl)) return info.linkUrl;
  if ((info.mediaType === "video" || info.mediaType === "audio") && isHttpUrl(info.srcUrl)) {
    return info.srcUrl;
  }
  return info.pageUrl;
}

browser.contextMenus.onClicked.addListener(async (info) => {
  if (!String(info.menuItemId).startsWith("ffvd:")) return;
  const preset = String(info.menuItemId).slice(5);
  const url = targetUrl(info);
  const settings = await getSettings();
  try {
    if (!isHttpUrl(url)) throw new Error(t("errNoLinkHere"));
    await host("download", { url, preset, cookies: settings.cookies, outdir: settings.outdir });
    notify(t("downloadStarted"), url);
  } catch (e) {
    notify(t("errorTitle"), e.message);
  }
});

function notify(title, message) {
  browser.notifications.create({
    type: "basic",
    iconUrl: browser.runtime.getURL("icons/icon.svg"),
    title,
    message,
  });
}
