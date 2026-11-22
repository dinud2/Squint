"""Tiny HTTP API for the speaker and the Tab5 (stdlib only, runs on QNX).

    GET /history?days=30   -> [{"date", "doses": [Dose]}]          (routine tracking)
    GET /insights?days=30  -> {"people": [PersonInsight]}           (docs/decline-tracking.md)
    GET /state    -> {"people": ["dinu", "kathy"], "unknown": 0, "since": t, "seq": n, "time": t}
                     Poll this (e.g. once a second from the ESP32).
    GET /events   -> Server-Sent Events: one `data: {json}` line per event, as it happens.
                     Starts with the current state so a client never misses who is there.
    GET /health   -> {"ok": true, "camera_age_s": ..., "warnings": [...], "faces": {...}, "bottles": {...},
                      "voice": {...}, "clients": [...]}   what each part last did (buddy/diag.py)

    POST /tab5/frame, /bottles/enroll?name=, /bottles/reset?name=, GET /bottles
                  -> bottle recognition for the Tab5 camera, see buddy/bottle_service.py

    iOS app (docs/api-contract.md): GET/POST /people, GET/POST /medications,
                  PUT/DELETE /medications/{id}, GET /today
    Tab5:         GET /tab5/commands?after=<seq>&wait=20 -> {"seq": n, "lines": [...]}
                  (Kathy's format; pass each line to handleCommand())
                  POST /doses/confirm {"med", "for", "taken": true|false}  ("Did you take it?")
    Testing:      POST /intake {"person", "confidence"}  (until hand-to-mouth is built)
                  POST /tab5/send {"line": "happy Well done!"}  (queue any face command)

Events (all have "type" and "time"):
    people_present   {"people": [...], "unknown": n, "seq": n}
    bottle_picked    {"bottle": "tylenol", "how": "lifted"|"gone"}
    bottle_returned  {"bottle": "tylenol"}
    say              {"text": ...}                       (also sent to the Nest)
    dose_taken       {"med", "for", "at", "how": "tab5"|"auto"}
"""
import json
import queue
import threading
import time
from urllib.parse import parse_qs, urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .diag import Diag
from .coordinator import AT_COUNTER_S
from .insights import insights


class Hub:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = {"type": "people_present", "people": [], "unknown": 0, "since": time.time(), "seq": 0,
                      "time": time.time()}
        self.subscribers = []
        self.listeners = []          # in-process callbacks (the coordinator)
        self.last_frame_t = 0.0
        self.diag = Diag()           # what each part last did (GET /health)
        self.preview, self.preview_t = None, 0.0   # small JPEG for the laptop view (GET /preview.mjpg)

    PREVIEW_W, PREVIEW_H, PREVIEW_Q, PREVIEW_FPS = 480, 272, 60, 10

    def set_preview(self, t, frame):
        """Keep a small, low-quality copy of a frame the loops already decoded: the laptop's
        debug view then costs the Pi ~2 ms 5x a second and ~50 KB/s of Wi-Fi, instead of the
        full 960x544 stream at 20 fps (~1 MB/s)."""
        if t - self.preview_t < 1.0 / self.PREVIEW_FPS:
            return
        import cv2
        ok, jpg = cv2.imencode(".jpg", cv2.resize(frame, (self.PREVIEW_W, self.PREVIEW_H), interpolation=cv2.INTER_AREA),
                               [cv2.IMWRITE_JPEG_QUALITY, self.PREVIEW_Q])
        if ok:
            self.preview, self.preview_t = jpg.tobytes(), t

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
        for fn in list(self.listeners):
            fn(event)

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


CAMS_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Squint cameras</title>
<style>
  body { margin: 0; background: #111; color: #eee; font: 15px system-ui, sans-serif; }
  .row { display: flex; gap: 12px; padding: 12px; flex-wrap: wrap; }
  figure { margin: 0 auto; flex: 0 1 960px; min-width: 0; }
  figcaption { padding: 6px 2px; color: #999; } figcaption b { color: #eee; }
  img { width: 100%; height: auto; display: block; background: #000; border-radius: 6px; }
  .wrap { position: relative; }
  .guide { position: absolute; left: 33%; top: 10%; width: 34%; height: 80%;
           border: 2px dashed rgba(255,255,255,.55); border-radius: 8px; pointer-events: none; }
  .guide span { position: absolute; top: 6px; left: 8px; font-size: 13px; color: rgba(255,255,255,.75); }
</style></head><body><div class="row">
  <figure><figcaption><b>Camera</b> &middot; C270 &middot; :8080 &middot; faces, and bottles held up in the box</figcaption>
    <div class="wrap"><img id="b" alt="camera"><div class="guide"><span>hold the bottle close: fill this box</span></div></div></figure>
</div><script>
  const h = location.hostname;
  document.getElementById("b").src = "http://" + h + ":8080/stream";
</script></body></html>"""


def make_handler(hub, bottles=None, coord=None):
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

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(n) if n else b""

        def _jbody(self):
            try:
                return json.loads(self._body() or b"{}")
            except ValueError:
                return None

        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if coord is not None and u.path in ("/history", "/insights"):
                days = max(1, min(int(q.get("days", 30)), 120))
                if u.path == "/history":
                    return self._json(coord.store.history(days))
                if coord.journal is None:
                    return self._json({"error": "routine tracking is off (no journal)"}, 503)
                return self._json(insights(coord.store, coord.journal, days))
            if coord is not None and u.path == "/doses/pending":   # what "Did you take it?" is about
                p = coord.pending
                here = coord.last_group if time.time() - coord.last_group_t < AT_COUNTER_S else []
                return self._json({"pending": None if not p else {"med": p["med"], "for": p["for"],
                                                                 "name": coord.store.med(p["med"])["name"]
                                                                 if coord.store.med(p["med"]) else p["med"]},
                                   "present": list(coord.present), "at_counter": list(coord.present) or list(here),
                                   "unknown": coord.unknown_here})
            if coord is not None and u.path in ("/people", "/medications", "/today", "/tab5/commands"):
                st = coord.store
                if u.path == "/people":
                    return self._json(st.people())
                if u.path == "/medications":
                    return self._json(st.medications())
                if u.path == "/today":
                    return self._json(st.today())
                hub.diag.polled(self.client_address[0], self.headers.get("User-Agent"))
                seq, lines = coord.tab5.after(int(q.get("after", 0)), float(q.get("wait", 0)))
                return self._json({"seq": seq, "lines": lines})
            if u.path == "/preview.jpg":            # the laptop view: small and cheap (see Hub.set_preview)
                if hub.preview is None:
                    return self._json({"error": "no frame yet"}, 503)
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(hub.preview)))
                self.end_headers()
                self.wfile.write(hub.preview)
                return
            if u.path == "/preview.mjpg":
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.end_headers()
                sent = 0.0
                try:
                    while True:
                        if hub.preview is not None and hub.preview_t != sent:
                            jpg, sent = hub.preview, hub.preview_t
                            self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                             + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
                            self.wfile.flush()
                        time.sleep(0.05)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    return
            if u.path == "/cams":                   # both camera streams side by side
                body = CAMS_PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path.startswith("/state"):
                with hub.lock:
                    s = dict(hub.state)
                s["time"] = time.time()
                self._json(s)
            elif u.path == "/bottles/last" and bottles is not None:
                self._json(bottles.live())
            elif self.path.startswith("/bottles") and bottles is not None:
                self._json(bottles.info())
            elif self.path.startswith("/health"):
                age = time.time() - hub.last_frame_t if hub.last_frame_t else None
                self._json({"ok": age is not None and age < 5, "camera_age_s": age, **hub.diag.report()})
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
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if coord is not None and u.path == "/doses/reset":     # demo: today starts over
                n = coord.store.reset_day()
                with coord.lock:
                    coord.pending = None
                coord.last_greet.clear()                    # greet the next arrival straight away
                coord.took_this_visit.clear()
                print(f"[reset] today's dose log cleared ({n} entries)", flush=True)
                return self._json({"ok": True, "cleared": n})
            if coord is not None and u.path in ("/people", "/medications", "/doses/confirm", "/intake", "/tab5/send"):
                b = self._jbody()
                if b is None:
                    return self._json({"error": "body must be JSON"}, 400)
                if u.path == "/people":
                    return self._json(coord.store.add_person(b), 201)
                if u.path == "/medications":
                    return self._json(coord.store.add_med(b), 201)
                if u.path == "/tab5/send":
                    if not b.get("line"):
                        return self._json({"error": "need {\"line\": \"...\"}"}, 400)
                    coord.show(str(b["line"]))
                    return self._json({"ok": True, "seq": coord.tab5.seq})
                if u.path == "/intake":
                    hub.publish({"type": "intake", "person": b.get("person"), "confidence": float(b.get("confidence", 0))})
                    return self._json({"ok": True})
                r = coord.confirm(b.get("med"), b.get("for"), bool(b.get("taken", True)))
                print(f"[confirm] from {self.client_address[0]} {b} -> {r.get('error') or r.get('status')}", flush=True)
                return self._json(r, 400 if "error" in r else 200)
            if bottles is None:
                return self._json({"error": "bottle recognition is not running"}, 503)
            body = self._body()
            try:
                if u.path == "/tab5/frame":
                    self._json(bottles.frame(body))
                elif u.path == "/bottles/enroll" and q.get("name"):
                    r = bottles.enroll(q["name"], body, full=q.get("crop") == "full")
                    self._json(r, 400 if "error" in r else 200)
                elif u.path == "/bottles/reset" and q.get("name"):
                    self._json(bottles.reset(q["name"]))
                else:
                    self._json({"error": "not found",
                                "endpoints": ["/tab5/frame", "/bottles/enroll?name=", "/bottles/reset?name="]}, 404)
            except Exception as e:          # never take the server down on one bad request
                self._json({"error": repr(e)}, 500)
        def do_PUT(self):
            u = urlparse(self.path)
            if coord is not None and u.path.startswith("/medications/"):
                b = self._jbody()
                if b is None:
                    return self._json({"error": "body must be JSON"}, 400)
                m = coord.store.put_med(u.path.split("/")[2], b)
                return self._json(m) if m else self._json({"error": "no such medication"}, 404)
            self._json({"error": "not found"}, 404)

        def do_DELETE(self):
            u = urlparse(self.path)
            if coord is not None and u.path.startswith("/medications/"):
                if coord.store.delete_med(u.path.split("/")[2]):
                    self.send_response(204)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    return
                return self._json({"error": "no such medication"}, 404)
            self._json({"error": "not found"}, 404)

        def do_OPTIONS(self):                      # CORS preflight (web tools)
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
    return Handler


def serve(hub, port=8081, bottles=None, coord=None):
    srv = ThreadingHTTPServer(("0.0.0.0", port), make_handler(hub, bottles, coord))
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
