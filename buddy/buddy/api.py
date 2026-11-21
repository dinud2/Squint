"""Tiny HTTP API for the speaker and the Tab5 (stdlib only, runs on QNX).

    GET /state    -> {"people": ["dinu", "kathy"], "unknown": 0, "since": t, "seq": n, "time": t}
                     Poll this (e.g. once a second from the ESP32).
    GET /events   -> Server-Sent Events: one `data: {json}` line per event, as it happens.
                     Starts with the current state so a client never misses who is there.
    GET /health   -> {"ok": true, "camera_age_s": ...}

    POST /tab5/frame, /bottles/enroll?name=, /bottles/reset?name=, GET /bottles
                  -> bottle recognition for the Tab5 camera, see buddy/bottle_service.py

Events (all have "type" and "time"):
    people_present   {"people": [...], "unknown": n, "seq": n}
    bottle_picked    {"bottle": "tylenol", "how": "lifted"|"gone"}
    bottle_returned  {"bottle": "tylenol"}
"""
import json
import queue
import threading
import time
from urllib.parse import parse_qs, urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Hub:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = {"type": "people_present", "people": [], "unknown": 0, "since": time.time(), "seq": 0,
                      "time": time.time()}
        self.subscribers = []
        self.last_frame_t = 0.0

    def publish(self, event):
        event = {**event, "time": time.time()}
        with self.lock:
            if event["type"] == "people_present":
                event["seq"] = self.state["seq"] + 1
                event["since"] = event["time"]
                self.state = event
            subs = list(self.subscribers)
        for q in subs:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass
        print("[event]", json.dumps(event), flush=True)

    def subscribe(self):
        q = queue.Queue(maxsize=100)
        with self.lock:
            self.subscribers.append(q)
            first = dict(self.state)
        q.put(first)
        return q

    def unsubscribe(self, q):
        with self.lock:
            if q in self.subscribers:
                self.subscribers.remove(q)


def make_handler(hub, bottles=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/state"):
                with hub.lock:
                    s = dict(hub.state)
                s["time"] = time.time()
                self._json(s)
            elif self.path.startswith("/bottles") and bottles is not None:
                self._json(bottles.info())
            elif self.path.startswith("/health"):
                age = time.time() - hub.last_frame_t if hub.last_frame_t else None
                self._json({"ok": age is not None and age < 5, "camera_age_s": age})
            elif self.path.startswith("/events"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                q = hub.subscribe()
                try:
                    while True:
                        try:
                            ev = q.get(timeout=15)
                            self.wfile.write(f"data: {json.dumps(ev)}\n\n".encode())
                        except queue.Empty:
                            self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    hub.unsubscribe(q)
            else:
                self._json({"error": "not found", "endpoints": ["/state", "/events", "/health", "/bottles"]}, 404)

        def do_POST(self):
            if bottles is None:
                return self._json({"error": "bottle recognition is not running"}, 503)
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n) if n else b""
            try:
                if u.path == "/tab5/frame":
                    self._json(bottles.frame(body))
                elif u.path == "/bottles/enroll" and q.get("name"):
                    r = bottles.enroll(q["name"], body)
                    self._json(r, 400 if "error" in r else 200)
                elif u.path == "/bottles/reset" and q.get("name"):
                    self._json(bottles.reset(q["name"]))
                else:
                    self._json({"error": "not found",
                                "endpoints": ["/tab5/frame", "/bottles/enroll?name=", "/bottles/reset?name="]}, 404)
            except Exception as e:          # never take the server down on one bad request
                self._json({"error": repr(e)}, 500)
    return Handler


def serve(hub, port=8081, bottles=None):
    srv = ThreadingHTTPServer(("0.0.0.0", port), make_handler(hub, bottles))
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
