#!/usr/bin/env python3
"""ffvd native messaging host: bridges the Firefox extension and yt-dlp.

Modes:
  ffvd_host.py <manifest> <ext-id>   native messaging (started by Firefox)
  ffvd_host.py --worker <job-id>     detached download worker (started by us)

Only the Python standard library is used.
"""
import glob
import json
import os
import re
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import time
import uuid
from pathlib import Path

VERSION = "1.1.0"

# yt-dlp format arguments per preset. "-S res:N" prefers the best quality up to N.
_VIDEO = ["-f", "bv*+ba/b", "--merge-output-format", "mp4"]
PRESETS = {
    "best": _VIDEO + ["-S", "res,ext:mp4:m4a"],
    "2160": _VIDEO + ["-S", "res:2160,ext:mp4:m4a"],
    "1440": _VIDEO + ["-S", "res:1440,ext:mp4:m4a"],
    "1080": _VIDEO + ["-S", "res:1080,ext:mp4:m4a"],
    "720": _VIDEO + ["-S", "res:720,ext:mp4:m4a"],
    "480": _VIDEO + ["-S", "res:480,ext:mp4:m4a"],
    "360": _VIDEO + ["-S", "res:360,ext:mp4:m4a"],
    "mp3": ["-f", "ba/b", "-x", "--audio-format", "mp3", "--audio-quality", "0"],
    "m4a": ["-f", "ba[ext=m4a]/ba/b", "-x", "--audio-format", "m4a"],
}

PROGRESS_TEMPLATE = (
    "download:FFVDP %(progress.downloaded_bytes)s %(progress.total_bytes)s "
    "%(progress.total_bytes_estimate)s %(progress.speed)s %(progress.eta)s"
)
POSTPROCESS_TEMPLATE = "postprocess:FFVDPP %(progress.postprocessor)s"

ACTIVE = ("queued", "running")
MAX_JOBS_LISTED = 30


# ---------------------------------------------------------------- paths/config

def state_dir():
    base = os.environ.get("FFVD_STATE_DIR")
    if not base:
        xdg = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
        base = os.path.join(xdg, "ffvd")
    path = Path(base, "jobs")
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_config():
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    try:
        with open(os.path.join(xdg, "ffvd", "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


# Firefox may start us with a minimal PATH, so look in the usual places too.
EXTRA_PATH = [os.path.expanduser("~/.local/bin"), os.path.expanduser("~/.deno/bin"), "/usr/local/bin", "/usr/bin", "/bin"]


def which(name):
    path = os.pathsep.join([os.environ.get("PATH", "")] + EXTRA_PATH)
    return shutil.which(name, path=path)


def ytdlp_cmd():
    """Command (argv prefix) that runs yt-dlp, or None if it is not installed."""
    custom = os.environ.get("FFVD_YTDLP") or load_config().get("ytdlp")
    if custom:
        return shlex.split(custom)
    found = which("yt-dlp")
    return [found] if found else None


def js_runtime_args():
    """YouTube needs a JS runtime; yt-dlp enables only deno by default."""
    if which("deno"):
        return []
    node = which("node")
    if not node:
        candidates = sorted(glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/node")))
        node = candidates[-1] if candidates else None
    return ["--js-runtimes", f"node:{node}"] if node else []


def default_outdir():
    try:
        out = subprocess.run(["xdg-user-dir", "DOWNLOAD"], capture_output=True,
                             text=True, timeout=5).stdout.strip()
        if out and out != os.path.expanduser("~"):
            return out
    except (OSError, subprocess.SubprocessError):
        pass
    return os.path.expanduser("~/Downloads")


# ---------------------------------------------------------------- validation

class HostError(Exception):
    """An error the extension can translate: `code` maps to an err_<code> UI message."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def check_url(url):
    if not isinstance(url, str) or not re.match(r"^https?://\S+$", url, re.I):
        raise HostError("bad_url", "An http(s):// URL is required")
    return url


def resolve_outdir(value):
    path = os.path.expanduser(value.strip()) if isinstance(value, str) and value.strip() else default_outdir()
    if not os.path.isabs(path):
        raise HostError("bad_outdir", "The download folder must be an absolute path")
    os.makedirs(path, exist_ok=True)
    return path


def check_job_id(job_id):
    if not isinstance(job_id, str) or not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise HostError("bad_job_id", "Invalid job id")
    return job_id


def common_args(cookies):
    args = ["--color", "never", "--no-warnings"] + js_runtime_args()
    if cookies:
        args += ["--cookies-from-browser", "firefox"]
    return args


def build_download_args(job):
    preset = job["preset"]
    if preset not in PRESETS:
        raise HostError("unknown_preset", f"Unknown preset: {preset}")
    if job.get("playlist"):
        template = "%(playlist_title|playlist)s/%(playlist_index|0)03d - %(title).150B [%(id)s].%(ext)s"
        playlist = ["--yes-playlist"]
    else:
        template = "%(title).150B [%(id)s].%(ext)s"
        playlist = ["--no-playlist"]
    return (common_args(job.get("cookies")) + PRESETS[preset] + playlist + [
        "-P", job["outdir"], "-o", template,
        "--newline", "--progress",
        "--progress-template", PROGRESS_TEMPLATE,
        "--progress-template", POSTPROCESS_TEMPLATE,
        "--print", "before_dl:FFVDT %(title)s",
        "--print", "after_move:FFVDF %(filepath)s",
    ])


def last_error(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    errors = [l for l in lines if l.startswith("ERROR:")]
    msg = (errors or lines or ["yt-dlp failed"])[-1]
    return msg[len("ERROR:"):].strip() if msg.startswith("ERROR:") else msg


# ---------------------------------------------------------------- jobs

def job_path(job_id):
    return state_dir() / f"{job_id}.json"


def save_job(job):
    path = job_path(job["id"])
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def load_job(job_id):
    try:
        return json.loads(job_path(job_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def is_stale(job):
    if job["status"] not in ACTIVE:
        return False
    if job.get("pid"):
        return not pid_alive(job["pid"])
    return time.time() - job.get("created", 0) > 30


def list_jobs():
    jobs = []
    for path in state_dir().glob("*.json"):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if is_stale(job):
            job.update(status="error", error="Download interrupted", errorCode="interrupted")
            save_job(job)
        jobs.append(job)
    jobs.sort(key=lambda j: j.get("created", 0), reverse=True)
    return jobs[:MAX_JOBS_LISTED]


def parse_number(token):
    try:
        return float(token)
    except ValueError:
        return None


def apply_line(job, line):
    """Update job from one line of yt-dlp output. Returns True if it changed."""
    if line.startswith("FFVDP "):
        done, total, estimate, speed, eta = (parse_number(t) for t in (line.split() + ["NA"] * 6)[1:6])
        total = total or estimate
        job.update(stage="download", downloaded=done, total=total, speed=speed, eta=eta,
                   percent=round(done * 100 / total, 1) if done is not None and total else None)
    elif line.startswith("FFVDPP "):
        job.update(stage="postprocess", postprocessor=line[7:].strip(), speed=None, eta=None)
    elif line.startswith("FFVDT "):
        job["title"] = line[6:].strip() or job.get("title")
    elif line.startswith("FFVDF "):
        job.setdefault("files", []).append(line[6:].strip())
        job["filepath"] = line[6:].strip()
    else:
        job.setdefault("log", []).append(line)
        job["log"] = job["log"][-20:]
        return False
    return True


# Desktop notifications come from the helper, so they follow the system locale.
NOTIFY_TEXT = {
    "en": {"done": "Video downloaded", "error": "Download failed"},
    "ru": {"done": "Видео скачано", "error": "Ошибка загрузки"},
}


def text(key):
    lang = (os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or "")[:2]
    return NOTIFY_TEXT.get(lang, NOTIFY_TEXT["en"])[key]


def notify(summary, body):
    if os.environ.get("FFVD_NO_NOTIFY"):
        return
    exe = which("notify-send")
    if exe:
        subprocess.run([exe, "-a", "ffvd", "-i", "folder-download", summary, body],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=10, check=False)


def run_worker(job_id):
    # Cancel kills our whole process group; survive it to record the outcome.
    signal.signal(signal.SIGTERM, lambda *_: None)
    job = load_job(check_job_id(job_id))
    job.update(status="running", pid=os.getpid(), started=time.time())
    save_job(job)

    cmd = ytdlp_cmd()
    try:
        if not cmd:
            raise HostError("no_ytdlp", "yt-dlp not found")
        argv = cmd + build_download_args(job) + ["--", job["url"]]
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, errors="replace", bufsize=1)
    except HostError as e:
        job.update(status="error", error=str(e), errorCode=e.code, finished=time.time())
        save_job(job)
        return 1
    except OSError as e:
        job.update(status="error", error=str(e), finished=time.time())
        save_job(job)
        return 1

    last_save = 0.0
    for raw in proc.stdout:
        if apply_line(job, raw.rstrip("\n")) and time.time() - last_save > 0.5:
            save_job(job)
            last_save = time.time()
    rc = proc.wait()

    cancel_marker = job_path(job_id).with_suffix(".cancel")
    if cancel_marker.exists():
        cancel_marker.unlink()
        job["status"] = "cancelled"
    elif rc == 0:
        job.update(status="done", percent=100.0)
    else:
        job.update(status="error", error=last_error("\n".join(job.get("log", []))))
    job.update(finished=time.time(), speed=None, eta=None)
    save_job(job)

    title = job.get("title") or job["url"]
    if job["status"] == "done":
        notify(text("done"), title)
    elif job["status"] == "error":
        notify(text("error"), f"{title}\n{job['error']}")
    return 0


# ---------------------------------------------------------------- commands

def cmd_ping(_msg):
    cmd = ytdlp_cmd()
    version = None
    if cmd:
        try:
            version = subprocess.run(cmd + ["--version"], capture_output=True, text=True,
                                     timeout=60).stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            version = None
    return {"version": VERSION, "ytdlp": version, "ffmpeg": bool(which("ffmpeg")),
            "jsRuntime": bool(which("deno") or js_runtime_args()), "outdir": default_outdir()}


def cmd_info(msg):
    url = check_url(msg.get("url"))
    cmd = ytdlp_cmd()
    if not cmd:
        raise HostError("no_ytdlp", "yt-dlp not found")
    argv = cmd + common_args(msg.get("cookies")) + ["-J", "--flat-playlist", "--no-playlist", "--", url]
    try:
        res = subprocess.run(argv, capture_output=True, text=True, errors="replace", timeout=120)
    except subprocess.TimeoutExpired:
        raise HostError("info_timeout", "yt-dlp did not answer within 2 minutes")
    if res.returncode != 0:
        raise HostError(None, last_error(res.stderr))
    data = json.loads(res.stdout)
    heights = sorted({f["height"] for f in data.get("formats") or []
                      if f.get("height") and f.get("vcodec") != "none"}, reverse=True)
    if not heights and data.get("height"):
        heights = [data["height"]]
    is_playlist = data.get("_type") == "playlist"
    return {
        "title": data.get("title"),
        "uploader": data.get("uploader") or data.get("channel"),
        "duration": data.get("duration"),
        "thumbnail": data.get("thumbnail"),
        "site": data.get("extractor_key") or data.get("extractor"),
        "heights": heights,
        "isPlaylist": is_playlist,
        "count": len(data.get("entries") or []) if is_playlist else None,
    }


def cmd_download(msg):
    job = {
        "id": uuid.uuid4().hex,
        "url": check_url(msg.get("url")),
        "preset": msg.get("preset") or "best",
        "playlist": bool(msg.get("playlist")),
        "cookies": bool(msg.get("cookies")),
        "outdir": resolve_outdir(msg.get("outdir")),
        "title": msg.get("title") if isinstance(msg.get("title"), str) else None,
        "status": "queued",
        "created": time.time(),
    }
    build_download_args(job)  # validates preset before spawning
    save_job(job)
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "--worker", job["id"]],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)
    return {"id": job["id"]}


def cmd_jobs(_msg):
    return {"jobs": [{k: v for k, v in j.items() if k != "log"} for j in list_jobs()]}


def cmd_cancel(msg):
    job_id = check_job_id(msg.get("id"))
    job = load_job(job_id)
    if not job or job["status"] not in ACTIVE:
        return {}
    job_path(job_id).with_suffix(".cancel").touch()
    if job.get("pid"):
        try:
            os.killpg(job["pid"], signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    return {}


def cmd_clear(_msg):
    for job in list_jobs():
        if job["status"] not in ACTIVE:
            job_path(job["id"]).unlink(missing_ok=True)
    return {}


def cmd_open(msg):
    job = load_job(check_job_id(msg.get("id")))
    if not job:
        raise HostError("job_not_found", "Job not found")
    target = job.get("filepath") if msg.get("what") == "file" else None
    if not target:
        target = os.path.dirname(job["filepath"]) if job.get("filepath") else job["outdir"]
    if not os.path.exists(target):
        raise HostError("file_not_found", "File not found")
    exe = which("xdg-open")
    if not exe:
        raise HostError("no_xdg_open", "xdg-open not found")
    subprocess.Popen([exe, target], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    return {}


COMMANDS = {"ping": cmd_ping, "info": cmd_info, "download": cmd_download, "jobs": cmd_jobs,
            "cancel": cmd_cancel, "clear": cmd_clear, "open": cmd_open}


def handle(msg):
    try:
        if not isinstance(msg, dict) or msg.get("cmd") not in COMMANDS:
            raise HostError("unknown_command", "Unknown command")
        return {"ok": True, **COMMANDS[msg["cmd"]](msg)}
    except HostError as e:
        return {"ok": False, "error": str(e), "code": e.code}
    except Exception as e:  # never leave the extension without an answer
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


# ---------------------------------------------------------------- protocol

def read_message(stream):
    header = stream.read(4)
    if len(header) < 4:
        return None
    (length,) = struct.unpack("=I", header)
    return json.loads(stream.read(length).decode("utf-8"))


def write_message(stream, obj):
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    stream.write(struct.pack("=I", len(data)) + data)
    stream.flush()


def main(argv):
    if len(argv) == 3 and argv[1] == "--worker":
        return run_worker(argv[2])
    while True:
        msg = read_message(sys.stdin.buffer)
        if msg is None:
            return 0
        write_message(sys.stdout.buffer, handle(msg))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
