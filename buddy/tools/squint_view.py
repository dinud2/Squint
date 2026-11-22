"""Live view of the Pi's camera with what Squint currently thinks, for aiming the camera and the demo.

    python tools/squint_view.py                 # Pi at 172.20.10.9;  f = fullscreen, q = quit

Nothing is computed on the laptop: the picture is the Pi's stream and every label is the Pi's own
result (GET /health, /bottles/last, /doses/pending, /events).
  - face box (the first face the Pi sees) with the name
  - the bottle box: grey while empty, green with the medicine's name when the Pi names it
  - top bar: who is at the counter, and the dose waiting for "Did you take it?"
  - bottom: the last few things Squint said / did
  - x-ray panel (on by default, x toggles it): the numbers behind each decision, for the live demo:
      who is here   SFace score per person against the accept line and the 0.08 lead
      which bottle  every colour patch, the classifier's probabilities, and its verdict (and why)
      took it?      the palm scores at the mouth and the confidence they add up to
      Tab5          the last line the Pi sent to the face
"""
import argparse
import json
import os
import sys
import threading
import time
import urllib.request

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from buddy.bottle_service import CENTER  # noqa: E402
from buddy.camera import Camera  # noqa: E402
from buddy.faces import ACCEPT, MARGIN, PERSON_ACCEPT  # noqa: E402
from buddy.coordinator import AUTO_CONFIRM  # noqa: E402

GREEN, AMBER, RED, WHITE, GREY = (90, 200, 90), (39, 170, 245), (70, 70, 230), (245, 245, 245), (170, 170, 170)
NAMES = {"motrin": "Motrin", "tylenol": "Tylenol", "advil": "Advil", "vitamind": "Vitamin D", "omega369": "Omega 3-6-9 (not in the app)"}
WIN = "Squint camera"


def get(url, timeout=2):
    return json.loads(urllib.request.urlopen(url, timeout=timeout).read())


class Pi:
    """Polls the Pi's state in the background so the video never waits on HTTP."""

    def __init__(self, host):
        self.api = f"http://{host}:8081"
        self.health, self.bottle, self.doses, self.ok = {}, {}, {}, False
        self.feed = []
        self.intake, self.intake_t = None, 0.0     # last hand-to-mouth result
        self.tab5, self.tab5_seq = "", 0          # last line sent to the Tab5
        for fn in (self._poll, self._events, self._tab5):
            threading.Thread(target=fn, daemon=True).start()

    def _poll(self):
        while True:
            try:
                self.bottle = get(self.api + "/bottles/last")
                self.doses = get(self.api + "/doses/pending")
                self.health = get(self.api + "/health")
                self.ok = True
            except Exception:
                self.ok = False
            time.sleep(0.25)

    def _events(self):
        while True:
            try:
                with urllib.request.urlopen(self.api + "/events", timeout=60) as r:
                    for raw in r:
                        line = raw.decode("utf-8", "ignore").strip()
                        if not line.startswith("data:"):
                            continue
                        ev = json.loads(line[5:])
                        t = ev.get("type")
                        if t == "say":
                            txt, col = f'"{ev["text"]}"', WHITE
                        elif t == "dose_taken":
                            txt, col = f"Taken: {NAMES.get(ev['med'], ev['med'])} ({ev['for']}, {ev['at']})", GREEN
                        elif t == "intake":
                            self.intake, self.intake_t = ev, time.time()
                            txt, col = f"Hand to mouth ({ev.get('confidence')})", AMBER
                        else:
                            continue
                        self.feed = (self.feed + [(time.strftime("%H:%M"), txt, col)])[-4:]
            except Exception:
                time.sleep(2)


    def _tab5(self):
        """Follow the Tab5's own command stream (long-poll), like the app's live mirror."""
        while True:
            try:
                r = get(f"{self.api}/tab5/commands?after={self.tab5_seq}&wait=20", timeout=25)
                if self.tab5_seq and r.get("lines"):
                    self.tab5 = r["lines"][-1]
                self.tab5_seq = r.get("seq", self.tab5_seq)
            except Exception:
                time.sleep(2)


def label(img, text, org, col, scale=0.7, thick=2):
    (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
    x, y = org
    cv2.rectangle(img, (x - 4, y - h - 8), (x + w + 4, y + 6), (25, 25, 25), -1)
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, col, thick, cv2.LINE_AA)


def draw(frame, pi):
    h, w = frame.shape[:2]
    f = pi.health.get("faces", {}) if pi.ok else {}
    # face: the Pi's newest face box (only if it is fresh)
    box, names = f.get("last_box"), f.get("last_names") or []
    if box and time.time() - f.get("last_face_t", 0) < 1.0:
        x, y, bw, bh = int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)
        named = time.time() - f.get("last_named_t", 0) < 1.0 and names
        col = GREEN if named else GREY
        cv2.rectangle(frame, (x, y), (x + bw, y + bh), col, 2)
        label(frame, names[0].title() if named else "?", (x, max(24, y - 8)), col)
    # bottle box
    b = pi.bottle if pi.ok else {}
    named = b.get("name") not in (None, "unknown") and b.get("age_s", 9) < 2
    if pi.xray and b.get("age_s", 9) < 2:  # every colour patch the classifier judged this frame
        sx, sy = w / 960, h / 544
        for c in b.get("checks") or []:
            if c["verdict"] == "_other":
                x0, y0, x1, y1 = c["box"]
                cv2.rectangle(frame, (int(x0 * sx), int(y0 * sy)), (int(x1 * sx), int(y1 * sy)), GREY, 1)
                label(frame, f"{c['colour']}: not a bottle", (int(x0 * sx), max(56, int(y0 * sy) - 4)), GREY, 0.45, 1)
    if "box" in b:                       # colour mode: the bottle can be anywhere (box in 960x544 px)
        if named and any(b["box"]):
            sx, sy = w / 960, h / 544
            x0, y0, x1, y1 = b["box"]
            x0, y0, x1, y1 = int(x0 * sx) - 12, int(y0 * sy) - 12, int(x1 * sx) + 12, int(y1 * sy) + 12
            cv2.rectangle(frame, (x0, y0), (x1, y1), GREEN, 3)
            label(frame, NAMES.get(b["name"], b["name"]), (x0, max(60, y0 - 8)), GREEN, 0.8)
        elif b.get("unsure") and b.get("unsure_box") and b.get("age_s", 9) < 2:   # colour vs classifier disagree
            sx, sy = w / 960, h / 544
            x0, y0, x1, y1 = b["unsure_box"]
            x0, y0, x1, y1 = int(x0 * sx) - 12, int(y0 * sy) - 12, int(x1 * sx) + 12, int(y1 * sy) + 12
            cv2.rectangle(frame, (x0, y0), (x1, y1), AMBER, 2)
            label(frame, "not sure", (x0, max(60, y0 - 8)), AMBER, 0.7)
    else:                                # show mode: the fixed box in the middle
        x0, y0, x1, y1 = int(CENTER[0] * w), int(CENTER[1] * h), int(CENTER[2] * w), int(CENTER[3] * h)
        cv2.rectangle(frame, (x0, y0), (x1, y1), GREEN if named else GREY, 3 if named else 1)
        if named:
            label(frame, f"{NAMES.get(b['name'], b['name'])}  {b['score']:.0%}", (x0 + 6, y1 - 12), GREEN, 0.8)
        else:
            label(frame, "hold the bottle here", (x0 + 6, y1 - 12), GREY, 0.55, 1)
    # top bar: who is here, what is being asked
    d = pi.doses if pi.ok else {}
    here = [n.title() for n in d.get("at_counter", [])]
    if not pi.ok:
        top, col = "Can't reach the Pi", RED
    elif d.get("pending"):
        top, col = f"{d['pending']['for'].title()}: did you take your {d['pending']['name']}?", AMBER
    else:
        if d.get("unknown") and not d.get("present"):
            here = ["someone I don't know"]
        top, col = ("At the counter: " + ", ".join(here)) if here else "Nobody at the counter", WHITE
    cv2.rectangle(frame, (0, 0), (w, 40), (25, 25, 25), -1)
    cv2.putText(frame, top, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.75, col, 2, cv2.LINE_AA)
    # bottom: recent things said / done
    for i, (ts, txt, c) in enumerate(reversed(pi.feed)):
        label(frame, f"{ts}  {txt}"[:90], (12, h - 14 - 30 * i), c, 0.55, 1)
    return frame


PANEL_W = 440
COLS = {"white": WHITE, "amber": AMBER, "red": RED, "blue": (214, 155, 126)}
MOOD = {"stop": "red", "wrong": "amber", "concerned": "amber", "sleep": "blue", "away": "blue"}


def bar(img, x, y, w, v, col, mark=None):
    cv2.rectangle(img, (x, y), (x + w, y + 10), (55, 55, 55), -1)
    cv2.rectangle(img, (x, y), (x + int(w * max(0.0, min(1.0, v))), y + 10), col, -1)
    if mark is not None:
        mx = x + int(w * mark)
        cv2.line(img, (mx, y - 4), (mx, y + 14), WHITE, 1)


def text(img, s, x, y, col=WHITE, scale=0.5, thick=1):
    cv2.putText(img, s, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, col, thick, cv2.LINE_AA)


def panel(pi, h):
    """The numbers behind what Squint just decided, read from the Pi (nothing computed here)."""
    img = np.full((h, PANEL_W, 3), 22, np.uint8)
    x, y = 16, 30
    def head(s, sub):
        nonlocal y
        text(img, s, x, y, WHITE, 0.6, 2)
        text(img, sub, x + 8 + cv2.getTextSize(s, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0][0], y, GREY, 0.42)
        y += 24
    if not pi.ok:
        text(img, "Can't reach the Pi", x, y, RED, 0.6, 2)
        return img
    # 1. faces
    f = pi.health.get("faces", {})
    head("WHO IS HERE", "YuNet -> SFace")
    fresh = time.time() - f.get("last_face_t", 0) < 1.5
    sc = (f.get("last_scores") or [{}])[0] if fresh else {}
    if not sc:
        text(img, "no face in view" if not fresh else "face too small / far", x, y, GREY); y += 24
    else:
        ranked = sorted(sc.items(), key=lambda kv: -kv[1])
        for name, v in ranked[:3]:
            acc = PERSON_ACCEPT.get(name, ACCEPT)
            text(img, f"{name:<8}{v:.2f}", x, y + 9, WHITE if name == ranked[0][0] else GREY)
            bar(img, x + 130, y, 270, v, GREEN if name == ranked[0][0] else GREY, acc)
            y += 22
        best, v = ranked[0]
        lead = v - (ranked[1][1] if len(ranked) > 1 else 0.0)
        acc = PERSON_ACCEPT.get(best, ACCEPT)
        if v >= acc and lead >= MARGIN:
            text(img, f"-> {best.title()}: over {acc:.2f}, ahead by {lead:.2f}", x, y + 6, GREEN)
        else:
            why = f"under {acc:.2f}" if v < acc else f"lead {lead:.2f} < {MARGIN}"
            text(img, f"-> unknown ({why}): never a guess", x, y + 6, AMBER)
        y += 30
    # 2. bottles
    b = pi.bottle
    y += 8
    head("WHICH BOTTLE", "colour -> MobileNetV3")
    checks = (b.get("checks") or []) if b.get("age_s", 9) < 2 else []
    if not checks:
        text(img, "no label colour in view", x, y, GREY); y += 24
    for c in checks[:3]:
        p = c.get("p", {})
        top = sorted(((k, v) for k, v in p.items()), key=lambda kv: -kv[1])[:2]
        verdict = c["verdict"]
        col = GREEN if verdict not in ("_other", "unsure") else (AMBER if verdict == "unsure" else GREY)
        text(img, f"{c['colour']} patch", x, y + 9, col)
        for i, (k, v) in enumerate(top):
            text(img, f"{k} {v:.2f}", x + 130 + 140 * i, y + 9, WHITE if i == 0 else GREY, 0.45)
        y += 20
        res = {"_other": "not a bottle", "unsure": "NOT SURE"}.get(verdict, verdict.upper())
        text(img, f"   -> {res}  ({c.get('why', '')})"[:58], x, y + 6, col, 0.42)
        y += 24
    # 3. hand to mouth
    y += 8
    head("DID THEY TAKE IT", "palm detector at the mouth")
    d = pi.doses
    if d.get("pending"):
        text(img, f"watching {d['pending']['for'].title()}'s mouth...", x, y, AMBER); y += 22
    ev = pi.intake if time.time() - pi.intake_t < 30 else None
    if ev:
        palms = ", ".join(f"{v:.2f}" for v in ev.get("palms", []))
        text(img, f"palms at mouth: {palms}", x, y, WHITE); y += 22
        conf = ev.get("confidence", 0)
        text(img, f"-> {conf:.2f}: " + ("auto-confirm in 2 s" if conf >= AUTO_CONFIRM else "ask on the Tab5"),
             x, y, GREEN if conf >= AUTO_CONFIRM else AMBER); y += 24
    elif not d.get("pending"):
        text(img, "runs only while a dose waits", x, y, GREY); y += 24
    # 4. tab5
    y += 8
    head("TAB5", "what the face shows")
    if pi.tab5:
        mood, _, rest = pi.tab5.partition(" ")
        col = COLS[MOOD.get(mood, "white")]
        cv2.circle(img, (x + 8, y - 4), 7, col, -1)
        text(img, f"{mood}  {rest.replace('|', ' / ')}"[:46], x + 24, y, col)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pi", default="172.20.10.9")
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--stream", help="default: the Pi's camera stream (http://<pi>:8080/stream, ~15 fps, "
                    "served by camstream, so it never stalls while the Pi is busy recognising). "
                    "http://<pi>:8081/preview.mjpg: small and light, but only as fast as the face loop")
    ap.add_argument("--no-xray", action="store_true", help="hide the numbers panel (x toggles it)")
    a = ap.parse_args()
    pi = Pi(a.pi)
    pi.xray = not a.no_xray
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, 960 + (PANEL_W if pi.xray else 0), 544)
    full = a.fullscreen
    if full:
        cv2.setWindowProperty(WIN, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cam = None
    while True:
        try:
            if cam is None:
                cam = Camera(a.stream or f"http://{a.pi}:8080/stream")
            _, frame = cam.read()
            if frame.shape[1] < 960:             # the small preview: enlarge so the labels stay sharp
                frame = cv2.resize(frame, (960, 544), interpolation=cv2.INTER_LINEAR)
            frame = draw(frame.copy(), pi)
        except Exception as e:           # Pi rebooting / hotspot drop: keep the window, retry
            frame = np.zeros((544, 960, 3), np.uint8)
            label(frame, f"Waiting for the Pi's camera... ({type(e).__name__})", (20, 280), RED)
            if cam is not None:
                try:
                    cam.close()
                except Exception:
                    pass
                cam = None
            time.sleep(1)
        if pi.xray:
            frame = np.hstack([frame, panel(pi, frame.shape[0])])
        cv2.imshow(WIN, frame)
        k = cv2.waitKey(1) & 0xFF
        if k == ord("q"):
            break
        if k == ord("x"):
            pi.xray = not pi.xray
        if k == ord("f"):
            full = not full
            cv2.setWindowProperty(WIN, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN if full else cv2.WINDOW_NORMAL)


if __name__ == "__main__":
    main()
