"""Squint home server: anything on the network can make the house speak.

    .venv/bin/python server.py                 # announce on the Google Nest
    .venv/bin/python server.py --local         # no Nest? play on the laptop speakers instead

    POST /announce   {"text": "...", "speaker": "Bathroom speaker", "voice": "en_US-hfc_female-medium"}
                     speaker and voice are optional. Replies {"ok": true, "speaker": ..., "seconds": ...}
    GET  /speakers   Google speakers found on the Wi-Fi
    GET  /voices     voices installed in voices/
    GET  /audio/<f>  the audio files themselves (this is what the Nest downloads)

The iOS app, the reminder scheduler and the agent all just POST to /announce.
"""
import argparse
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import voice
from nest import Nests, my_ip

PORT = 8765
TYPES = {".m4a": "audio/mp4", ".wav": "audio/wav"}


class State:
    local = False
    nests = Nests()
    lock = threading.Lock()      # one announcement at a time, so they don't talk over each other


def announce(text, speaker=None, voice_name=None):
    path = voice.synth(text, voice_name or voice.DEFAULT_VOICE)
    seconds = round(voice.duration(path), 1)
    with State.lock:
        if State.local:
            subprocess.run(["afplay", path])
            return {"ok": True, "speaker": "laptop", "seconds": seconds}
        url = f"http://{my_ip()}:{PORT}/audio/{os.path.basename(path)}"
        name = State.nests.play(url, TYPES[os.path.splitext(path)[1]], speaker)
        return {"ok": True, "speaker": name, "seconds": seconds, "url": url}


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/speakers":
            return self._json(200, {"speakers": [] if State.local else State.nests.discover()})
        if self.path == "/voices":
            return self._json(200, {"voices": voice.available(), "default": voice.DEFAULT_VOICE})
        if self.path.startswith("/audio/"):
            name = os.path.basename(self.path.split("?")[0])          # basename: no ../ tricks
            path = os.path.join(voice.CACHE, name)
            if not os.path.isfile(path):
                return self._json(404, {"error": "no such audio"})
            data = open(path, "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", TYPES.get(os.path.splitext(name)[1], "application/octet-stream"))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self._json(404, {"error": "try POST /announce"})

    def do_POST(self):
        if self.path != "/announce":
            return self._json(404, {"error": "try POST /announce"})
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            text = str(req.get("text", "")).strip()
            if not text:
                return self._json(400, {"error": "text is required"})
            self._json(200, announce(text, req.get("speaker"), req.get("voice")))
        except (LookupError, FileNotFoundError) as e:
            self._json(503, {"ok": False, "error": str(e)})

    def log_message(self, fmt, *args):
        print("[home]", self.address_string(), fmt % args)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true", help="play on this laptop instead of a Nest")
    args = ap.parse_args()
    State.local = args.local
    if not args.local:
        found = State.nests.discover()
        print("[home] speakers:", found or "none yet (same Wi-Fi as the Nest?)")
    print(f"[home] voice: {voice.DEFAULT_VOICE}")
    print(f"[home] listening on http://{my_ip()}:{PORT}  (POST /announce)")
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
