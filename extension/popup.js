"use strict";

const $ = (id) => document.getElementById(id);
let settings;
let infoSeq = 0;

const STATUS_TEXT = {
  queued: "в очереди",
  running: "скачивается",
  done: "готово",
  error: "ошибка",
  cancelled: "отменено",
};

function show(el, text) {
  el.textContent = text || "";
  el.hidden = !text;
}

function fmtBytes(n) {
  if (!n) return "";
  const units = ["Б", "КБ", "МБ", "ГБ"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return n.toFixed(i ? 1 : 0) + " " + units[i];
}

function fmtTime(sec) {
  if (sec == null || !isFinite(sec)) return "";
  sec = Math.round(sec);
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  const mm = String(m).padStart(h ? 2 : 1, "0"), ss = String(s).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

function el(tag, props = {}, ...children) {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children.filter((c) => c != null));
  return node;
}

function fillPresets(maxHeight) {
  const select = $("preset");
  const current = select.value || settings.preset;
  select.replaceChildren();
  for (const p of PRESETS) {
    if (maxHeight && p.height && p.height !== Infinity && p.height > maxHeight) continue;
    select.append(el("option", { value: p.id, textContent: p.label }));
  }
  select.value = [...select.options].some((o) => o.value === current) ? current : "best";
}

async function checkHost() {
  try {
    const res = await host("ping");
    if (!res.ytdlp) {
      show($("hostError"), "yt-dlp не установлен.\nУстановите: sudo pacman -S yt-dlp deno");
      return false;
    }
    $("hostStatus").textContent = "yt-dlp " + res.ytdlp + (res.ffmpeg ? "" : " · нет ffmpeg!");
    $("outdir").placeholder = res.outdir;
    return true;
  } catch (e) {
    show($("hostError"), e.message);
    return false;
  }
}

async function loadInfo() {
  const url = $("url").value.trim();
  const seq = ++infoSeq;
  $("info").hidden = true;
  $("playlistRow").hidden = !/[?&]list=/.test(url);
  if (!isHttpUrl(url)) {
    $("infoState").textContent = "";
    fillPresets();
    return;
  }
  $("infoState").textContent = "Получаю информацию о видео…";
  try {
    const info = await host("info", { url, cookies: $("cookies").checked });
    if (seq !== infoSeq) return;
    $("infoState").textContent = "";
    $("title").textContent = info.title || url;
    const meta = [info.site, info.uploader, fmtTime(info.duration),
      info.heights.length ? info.heights[0] + "p" : null];
    $("meta").textContent = meta.filter(Boolean).join(" · ");
    $("thumb").hidden = !info.thumbnail;
    if (info.thumbnail) $("thumb").src = info.thumbnail;
    $("info").hidden = false;
    if (info.isPlaylist) {
      $("playlistRow").hidden = false;
      $("playlist").checked = true;
      $("playlistCount").textContent = info.count ? `(${info.count})` : "";
    }
    fillPresets(info.heights[0]);
  } catch (e) {
    if (seq !== infoSeq) return;
    $("infoState").replaceChildren("Не удалось распознать: " + e.message);
    if (needsLogin(e.message) && !$("cookies").checked) {
      $("infoState").append(el("br"), el("button", {
        className: "small",
        textContent: "Повторить со входом из Firefox",
        onclick: () => { $("cookies").checked = true; $("cookies").onchange(); loadInfo(); },
      }));
    }
    fillPresets();
  }
}

function needsLogin(message) {
  return /log(ged)?[ -]?in|sign in|not a bot|cookies|authenticat|private|age/i.test(message);
}

async function download() {
  show($("dlError"));
  const url = $("url").value.trim();
  if (!isHttpUrl(url)) return show($("dlError"), "Нужна ссылка http(s)://");
  $("download").disabled = true;
  try {
    await host("download", {
      url,
      preset: $("preset").value,
      playlist: !$("playlistRow").hidden && $("playlist").checked,
      cookies: $("cookies").checked,
      outdir: $("outdir").value.trim(),
      title: $("info").hidden ? null : $("title").textContent,
    });
    await refreshJobs();
  } catch (e) {
    show($("dlError"), e.message);
  } finally {
    $("download").disabled = false;
  }
}

function jobItem(job) {
  const active = job.status === "queued" || job.status === "running";
  const pct = job.status === "done" ? 100 : job.percent || 0;
  const details = [STATUS_TEXT[job.status] || job.status];
  if (job.status === "running") {
    if (job.stage === "postprocess") details.push("обработка (" + (job.postprocessor || "ffmpeg") + ")");
    else {
      if (job.percent != null) details.push(job.percent.toFixed(1) + "%");
      if (job.total) details.push(fmtBytes(job.total));
      if (job.speed) details.push(fmtBytes(job.speed) + "/с");
      if (job.eta) details.push("осталось " + fmtTime(job.eta));
    }
  }

  const actions = el("span", { className: "actions" });
  const button = (text, title, fn) =>
    el("button", { className: "small", textContent: text, title, onclick: () => fn().catch((e) => alertJob(e)) });
  if (active) actions.append(button("✕", "Отменить", () => host("cancel", { id: job.id }).then(refreshJobs)));
  if (job.status === "done") {
    actions.append(button("▶", "Открыть файл", () => host("open", { id: job.id, what: "file" })));
    actions.append(button("📂", "Открыть папку", () => host("open", { id: job.id, what: "dir" })));
  }
  if (job.status === "error" && !job.cookies && needsLogin(job.error || "")) {
    actions.append(button("↻ со входом", "Повторить, используя вход из Firefox (куки)", () =>
      host("download", { ...pick(job, "url", "preset", "playlist", "outdir", "title"), cookies: true })
        .then(refreshJobs)));
  }

  return el("li", { className: job.status },
    el("div", { className: "name", textContent: job.title || job.url, title: job.url }),
    active || job.status === "done" ? el("div", { className: "bar" }, el("div", { style: `width:${pct}%` })) : null,
    el("div", { className: "line" }, el("span", { textContent: details.join(" · ") }), actions),
    job.error ? el("div", { className: "err", textContent: job.error }) : null,
  );
}

function pick(obj, ...keys) {
  return Object.fromEntries(keys.map((k) => [k, obj[k]]));
}

function alertJob(e) {
  show($("dlError"), e.message);
}

async function refreshJobs() {
  try {
    const { jobs } = await host("jobs");
    $("jobs").replaceChildren(...jobs.map(jobItem));
    $("noJobs").hidden = jobs.length > 0;
  } catch {
    // host errors are already shown by checkHost()
  }
}

async function init() {
  settings = await getSettings();
  fillPresets();
  $("cookies").checked = settings.cookies;
  $("outdir").value = settings.outdir;

  $("preset").onchange = () => browser.storage.local.set({ preset: $("preset").value });
  $("cookies").onchange = () => browser.storage.local.set({ cookies: $("cookies").checked });
  $("outdir").onchange = () => browser.storage.local.set({ outdir: $("outdir").value.trim() });
  $("refresh").onclick = loadInfo;
  $("url").onchange = loadInfo;
  $("url").onkeydown = (e) => { if (e.key === "Enter") loadInfo(); };
  $("download").onclick = download;
  $("clear").onclick = () => host("clear").then(refreshJobs).catch(alertJob);

  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  if (tab && isHttpUrl(tab.url)) $("url").value = tab.url;

  if (await checkHost()) {
    refreshJobs();
    setInterval(refreshJobs, 1000);
    loadInfo();
  }
}

init();
