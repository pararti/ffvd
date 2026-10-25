"""Tests for ffvd_host.py. Run: python3 -m unittest discover -s host"""
import io
import json
import os
import stat
import struct
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import ffvd_host as host  # noqa: E402

HOST = os.path.join(os.path.dirname(__file__), "ffvd_host.py")

# Fake yt-dlp: behaviour is picked by the URL path.
FAKE_YTDLP = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json, sys, time
    args = sys.argv[1:]
    url = args[-1]
    if "--version" in args:
        print("2099.01.01"); sys.exit(0)
    if "-J" in args:
        if "fail" in url:
            print("ERROR: [generic] Unsupported URL: " + url, file=sys.stderr); sys.exit(1)
        print(json.dumps({"title": "Clip", "uploader": "Me", "duration": 12, "extractor_key": "Fake",
                          "formats": [{"height": 720, "vcodec": "avc1"}, {"height": 1080, "vcodec": "vp9"},
                                      {"height": None, "vcodec": "none"}]}))
        sys.exit(0)
    outdir = args[args.index("-P") + 1]
    if "fail" in url:
        print("ERROR: [fake] Video unavailable"); sys.exit(1)
    print("FFVDT Clip title", flush=True)
    steps = 200 if "slow" in url else 3
    for i in range(1, steps + 1):
        print(f"FFVDP {i * 100} 300 NA 1000.0 {steps - i}", flush=True)
        time.sleep(0.05)
    print("FFVDPP Merger", flush=True)
    path = outdir + "/Clip title [x].mp4"
    open(path, "w").close()
    print("FFVDF " + path, flush=True)
""")


def encode(obj):
    data = json.dumps(obj).encode()
    return struct.pack("=I", len(data)) + data


def decode_all(raw):
    out = []
    while raw:
        (n,) = struct.unpack("=I", raw[:4])
        out.append(json.loads(raw[4:4 + n]))
        raw = raw[4 + n:]
    return out


class HostTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        fake = root / "yt-dlp"
        fake.write_text(FAKE_YTDLP)
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self.outdir = root / "out"
        self.env_backup = dict(os.environ)
        os.environ.update(FFVD_YTDLP=str(fake), FFVD_STATE_DIR=str(root / "state"),
                          FFVD_NO_NOTIFY="1", XDG_CONFIG_HOME=str(root / "config"))

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.env_backup)
        self.tmp.cleanup()

    def call(self, *messages):
        """Run the host as Firefox does: framed JSON on stdin/stdout."""
        res = subprocess.run([sys.executable, HOST, "manifest.json", "ffvd@test"],
                             input=b"".join(encode(m) for m in messages),
                             capture_output=True, timeout=30)
        self.assertEqual(res.returncode, 0, res.stderr)
        return decode_all(res.stdout)

    def wait_job(self, job_id, statuses=("done", "error", "cancelled"), timeout=15):
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = host.load_job(job_id)
            if job and job["status"] in statuses:
                return job
            time.sleep(0.1)
        self.fail(f"job {job_id} stuck: {host.load_job(job_id)}")


class ProtocolTest(HostTestCase):
    def test_roundtrip_framing(self):
        buf = io.BytesIO()
        host.write_message(buf, {"a": "привет"})
        buf.seek(0)
        self.assertEqual(host.read_message(buf), {"a": "привет"})
        self.assertIsNone(host.read_message(buf))

    def test_ping_reports_versions(self):
        [res] = self.call({"cmd": "ping"})
        self.assertTrue(res["ok"])
        self.assertEqual(res["ytdlp"], "2099.01.01")

    def test_several_messages_in_one_session(self):
        res = self.call({"cmd": "jobs"}, {"cmd": "nope"})
        self.assertEqual(res[0], {"ok": True, "jobs": []})
        self.assertFalse(res[1]["ok"])


class ValidationTest(HostTestCase):
    def test_rejects_non_http_urls(self):
        for url in ["file:///etc/passwd", "--exec=rm", "javascript:1", "", None]:
            [res] = self.call({"cmd": "download", "url": url, "outdir": str(self.outdir)})
            self.assertFalse(res["ok"], url)

    def test_rejects_unknown_preset(self):
        [res] = self.call({"cmd": "download", "url": "https://x.com/a", "preset": "--exec",
                           "outdir": str(self.outdir)})
        self.assertFalse(res["ok"])
        self.assertEqual(list(Path(os.environ["FFVD_STATE_DIR"], "jobs").glob("*.json")), [])

    def test_rejects_relative_outdir_and_bad_job_id(self):
        [res] = self.call({"cmd": "download", "url": "https://x.com/a", "outdir": "rel/dir"})
        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], "bad_outdir")
        [res] = self.call({"cmd": "open", "id": "../../etc"})
        self.assertEqual(res["code"], "bad_job_id")

    def test_url_goes_after_double_dash(self):
        job = {"preset": "720", "outdir": "/o", "url": "https://a"}
        args = host.build_download_args(job)
        self.assertNotIn("https://a", args)
        self.assertIn("res:720,ext:mp4:m4a", args)
        self.assertIn("--no-playlist", args)
        self.assertIn("--yes-playlist", host.build_download_args({**job, "playlist": True}))
        self.assertIn("--cookies-from-browser", host.build_download_args({**job, "cookies": True}))


class InfoTest(HostTestCase):
    def test_info_summarises_formats(self):
        [res] = self.call({"cmd": "info", "url": "https://example.com/v"})
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["title"], "Clip")
        self.assertEqual(res["heights"], [1080, 720])
        self.assertFalse(res["isPlaylist"])

    def test_info_error_is_readable(self):
        [res] = self.call({"cmd": "info", "url": "https://example.com/fail"})
        self.assertFalse(res["ok"])
        self.assertIsNone(res["code"])
        self.assertTrue(res["error"].startswith("[generic] Unsupported URL"))


class DownloadTest(HostTestCase):
    def start(self, url):
        [res] = self.call({"cmd": "download", "url": url, "preset": "best", "outdir": str(self.outdir)})
        self.assertTrue(res["ok"], res)
        return res["id"]

    def test_download_completes_with_file(self):
        job = self.wait_job(self.start("https://example.com/v"))
        self.assertEqual(job["status"], "done", job)
        self.assertEqual(job["title"], "Clip title")
        self.assertTrue(os.path.exists(job["filepath"]))
        [listed] = self.call({"cmd": "jobs"})[0]["jobs"]
        self.assertNotIn("log", listed)

    def test_download_error(self):
        job = self.wait_job(self.start("https://example.com/fail"))
        self.assertEqual(job["status"], "error")
        self.assertEqual(job["error"], "[fake] Video unavailable")

    def test_progress_then_cancel(self):
        job_id = self.start("https://example.com/slow")
        job = self.wait_job(job_id, statuses=("running",))
        deadline = time.time() + 10
        while host.load_job(job_id).get("percent") is None and time.time() < deadline:
            time.sleep(0.1)
        self.assertGreater(host.load_job(job_id)["percent"], 0)
        self.assertTrue(self.call({"cmd": "cancel", "id": job_id})[0]["ok"])
        job = self.wait_job(job_id)
        self.assertEqual(job["status"], "cancelled")

    def test_clear_removes_finished_only(self):
        self.wait_job(self.start("https://example.com/v"))
        self.call({"cmd": "clear"})
        self.assertEqual(self.call({"cmd": "jobs"})[0]["jobs"], [])

    def test_stale_running_job_marked_interrupted(self):
        host.save_job({"id": "a" * 32, "url": "https://a", "status": "running",
                       "pid": 2 ** 22 + 1, "created": time.time()})
        [job] = self.call({"cmd": "jobs"})[0]["jobs"]
        self.assertEqual(job["status"], "error")
        self.assertEqual(job["errorCode"], "interrupted")

    def test_missing_ytdlp_reported_with_code(self):
        os.environ["FFVD_YTDLP"] = ""
        os.environ["PATH"] = "/nonexistent"
        extra, host.EXTRA_PATH = host.EXTRA_PATH, []
        try:
            res = host.handle({"cmd": "info", "url": "https://example.com/v"})
        finally:
            host.EXTRA_PATH = extra
        self.assertEqual(res["code"], "no_ytdlp")


class NotifyTextTest(unittest.TestCase):
    def test_follows_locale_with_english_fallback(self):
        env = dict(os.environ)
        try:
            os.environ.pop("LC_ALL", None); os.environ.pop("LC_MESSAGES", None)
            os.environ["LANG"] = "ru_RU.UTF-8"
            self.assertEqual(host.text("done"), "Видео скачано")
            os.environ["LANG"] = "de_DE.UTF-8"
            self.assertEqual(host.text("done"), "Video downloaded")
        finally:
            os.environ.clear(); os.environ.update(env)


class ParseTest(unittest.TestCase):
    def test_progress_line(self):
        job = {}
        host.apply_line(job, "FFVDP 50 NA 200 10.5 3")
        self.assertEqual(job["percent"], 25.0)
        self.assertEqual(job["speed"], 10.5)
        host.apply_line(job, "FFVDP 50 NA NA NA NA")
        self.assertIsNone(job["percent"])

    def test_error_extraction(self):
        self.assertEqual(host.last_error("foo\nERROR: bad thing\nbar"), "bad thing")
        self.assertEqual(host.last_error("only text"), "only text")


if __name__ == "__main__":
    unittest.main()
