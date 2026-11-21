"""Tiny HTTP API for the speaker and the Tab5 (stdlib only, runs on QNX).

    GET /state    -> {"people": ["dinu", "kathy"], "unknown": 0, "since": t, "seq": n, "time": t}
                     Poll this (e.g. once a second from the ESP32).
    GET /events   -> Server-Sent Events: one `data: {json}` line per event, as it happens.
                     Starts with the current state so a client never misses who is there.
    GET /health   -> {"ok": true, "camera_age_s": ...}

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


class Hub:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = {"type": "people_present", "people": [], "unknown": 0, "since": time.time(), "seq": 0,
                      "time": time.time()}
        self.subscribers = []
        self.listeners = []          # in-process callbacks (the coordinator)
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
  figure { margin: 0; flex: 1 1 420px; min-width: 0; }
  figcaption { padding: 6px 2px; color: #999; } figcaption b { color: #eee; }
  img { width: 100%; height: auto; display: block; background: #000; border-radius: 6px; }
  .wrap { position: relative; }
  .guide { position: absolute; left: 18%; top: 8%; width: 64%; height: 84%;
           border: 2px dashed rgba(255,255,255,.55); border-radius: 8px; pointer-events: none; }
  .guide span { position: absolute; top: 6px; left: 8px; font-size: 13px; color: rgba(255,255,255,.75); }
</style></head><body><div class="row">
  <figure><figcaption><b>Bottles</b> &middot; Brio 101 &middot; :8080</figcaption>
    <div class="wrap"><img id="b" alt="bottle camera"><div class="guide"><span>hold the bottle here</span></div></div></figure>
  <figure><figcaption><b>Faces</b> &middot; C270 &middot; :8082</figcaption><img id="f" alt="face camera"></figure>
</div><script>
  const h = location.hostname;
  document.getElementById("b").src = "http://" + h + ":8080/stream";
  document.getElementById("f").src = "http://" + h + ":8082/stream";
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
            if coord is not None and u.path in ("/people", "/medications", "/today", "/tab5/commands"):
                st = coord.store
                if u.path == "/people":
                    return self._json(st.people())
                if u.path == "/medications":
                    return self._json(st.medications())
                if u.path == "/today":
                    return self._json(st.today())
                seq, lines = coord.tab5.after(int(q.get("after", 0)), float(q.get("wait", 0)))
                return self._json({"seq": seq, "lines": lines})
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
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
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
                return self._json(r, 400 if "error" in r else 200)
            if bottles is None:
                return self._json({"error": "bottle recognition is not running"}, 503)
            body = self._body()
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
