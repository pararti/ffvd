#!/usr/bin/env python3
"""Check that ffvd is fully installed: dependencies, native helper, Firefox add-on.

  python3 doctor.py          human-readable report
  python3 doctor.py --json   machine-readable report (for scripts and AI agents)

Exit code: 0 if nothing failed (warnings allowed), 1 otherwise.
"""
import glob
import json
import os
import platform
import shutil
import struct
import subprocess
import sys

DEFAULT_EXT_ID = "ffvd@apararti.local"
MANIFEST_PATH = os.path.expanduser("~/.mozilla/native-messaging-hosts/ffvd.json")
EXTRA_PATH = [os.path.expanduser("~/.local/bin"), os.path.expanduser("~/.deno/bin"), "/usr/local/bin", "/usr/bin", "/bin"]


def which(name):
    return shutil.which(name, path=os.pathsep.join([os.environ.get("PATH", "")] + EXTRA_PATH))


def repo_manifest():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extension", "manifest.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def ext_id():
    try:
        return repo_manifest()["browser_specific_settings"]["gecko"]["id"]
    except KeyError:
        return DEFAULT_EXT_ID


def version_tuple(version):
    return tuple(int(p) for p in str(version).split(".") if p.isdigit())


def run(argv, timeout=60):
    try:
        res = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return res.stdout.strip() if res.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def check_os():
    if platform.system() == "Linux":
        return "ok", "Linux", None
    return "fail", platform.system(), "ffvd currently supports Linux only"


def check_firefox():
    exe = which("firefox")
    if run(["flatpak", "info", "org.mozilla.firefox"], timeout=10) is not None and not exe:
        return "fail", "Flatpak Firefox", "Flatpak Firefox cannot start native helpers; use the distro or Mozilla build"
    if not exe:
        return "fail", "not found", "Install Firefox from your distro or mozilla.org"
    real = os.path.realpath(exe)
    version = run([exe, "--version"], timeout=20) or "unknown version"
    if real.startswith("/snap/") or "snap" in real.split(os.sep):
        return "warn", f"{version} (Snap)", "Snap Firefox needs xdg-desktop-portal for native messaging"
    return "ok", version, None


def check_ytdlp():
    exe = which("yt-dlp")
    if not exe:
        return "fail", "not found", "Install yt-dlp (see docs/agent-install.md, step 3)"
    return "ok", f"{run([exe, '--version']) or '?'} ({exe})", None


def check_ffmpeg():
    exe = which("ffmpeg")
    return ("ok", exe, None) if exe else ("fail", "not found", "Install ffmpeg (needed to merge video and audio)")


def check_js_runtime():
    if which("deno"):
        return "ok", f"deno ({which('deno')})", None
    node = which("node") or (sorted(glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/node"))) or [None])[-1]
    if node:
        return "ok", f"node ({node})", None
    return "warn", "none", "Install deno (or node): yt-dlp needs a JS runtime for YouTube"


def read_manifest():
    try:
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def check_native_manifest():
    data = read_manifest()
    if data is None:
        return "fail", "missing", "Run ./install.sh"
    if ext_id() not in data.get("allowed_extensions", []):
        return "fail", MANIFEST_PATH, f"allowed_extensions does not include {ext_id()}; re-run ./install.sh"
    if not os.access(data.get("path", ""), os.X_OK):
        return "fail", data.get("path"), "Helper file missing or not executable; re-run ./install.sh"
    return "ok", MANIFEST_PATH, None


def check_helper():
    data = read_manifest()
    if data is None:
        return "fail", "not installed", "Run ./install.sh"
    msg = json.dumps({"cmd": "ping"}).encode()
    try:
        res = subprocess.run([data["path"], MANIFEST_PATH, ext_id()], input=struct.pack("=I", len(msg)) + msg,
                             capture_output=True, timeout=90)
        reply = json.loads(res.stdout[4:])
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as e:
        return "fail", f"does not answer ({e})", "Re-run ./install.sh; check that python3 is installed"
    if not reply.get("ok"):
        return "fail", reply.get("error", "error"), None
    if not reply.get("ytdlp"):
        return "fail", "answers, but cannot run yt-dlp", "Install yt-dlp"
    detail = f"v{reply['version']}, downloads to {reply['outdir']}"
    latest = repo_manifest().get("version")
    if latest and version_tuple(reply["version"]) < version_tuple(latest):
        return "warn", detail, f"Helper is older than this checkout ({latest}); re-run ./install.sh"
    return "ok", detail, None


def check_addon():
    wanted = ext_id()
    found = []
    for path in glob.glob(os.path.expanduser("~/.mozilla/firefox/*/extensions.json")):
        try:
            with open(path, encoding="utf-8") as f:
                addons = json.load(f).get("addons", [])
        except (OSError, ValueError):
            continue
        for addon in addons:
            if addon.get("id") == wanted:
                found.append((os.path.basename(os.path.dirname(path)), addon))
    if not found:
        return "fail", "not installed", "Install ffvd.xpi in Firefox (docs/agent-install.md, step 6)"
    active = [(profile, a) for profile, a in found if a.get("active")]
    if not active:
        return "fail", "installed but disabled", "Enable ffvd in about:addons"
    temporary = all(a.get("location") == "app-temporary" for _, a in active)
    details = ", ".join(f"{a.get('version')} in profile {p}" for p, a in active)
    if temporary:
        return "warn", details + " (temporary)", "Temporary add-ons vanish on restart; install the signed .xpi"
    latest = repo_manifest().get("version")
    if latest and all(version_tuple(a.get("version")) < version_tuple(latest) for _, a in active):
        return "warn", details, f"Update available: install ffvd.xpi {latest} (docs/agent-install.md, step 6)"
    return "ok", details, None


CHECKS = [
    ("os", "Operating system", check_os),
    ("firefox", "Firefox", check_firefox),
    ("yt-dlp", "yt-dlp", check_ytdlp),
    ("ffmpeg", "ffmpeg", check_ffmpeg),
    ("js-runtime", "JS runtime for YouTube", check_js_runtime),
    ("native-manifest", "Native messaging manifest", check_native_manifest),
    ("helper", "ffvd helper", check_helper),
    ("addon", "Firefox add-on", check_addon),
]


def main():
    results = []
    for key, title, fn in CHECKS:
        status, detail, hint = fn()
        results.append({"check": key, "title": title, "status": status, "detail": detail, "hint": hint})
    ok = all(r["status"] != "fail" for r in results)

    if "--json" in sys.argv:
        print(json.dumps({"ok": ok, "checks": results}, indent=2, ensure_ascii=False))
    else:
        for r in results:
            print(f"[{r['status']:>4}] {r['title']}: {r['detail']}")
            if r["hint"] and r["status"] != "ok":
                print(f"       -> {r['hint']}")
        print("\nffvd is ready." if ok else "\nffvd is not fully installed yet.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
