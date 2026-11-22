"""Live view of the Pi's camera with what Squint currently thinks, for aiming the camera and the demo.

    python tools/squint_view.py                 # Pi at 172.20.10.9;  f = fullscreen, q = quit

Nothing is computed on the laptop: the picture is the Pi's stream and every label is the Pi's own
result (GET /health, /bottles/last, /doses/pending, /events).
  - face box (the first face the Pi sees) with the name
  - the bottle box: grey while empty, green with the medicine's name when the Pi names it
  - top bar: who is at the counter, and the dose waiting for "Did you take it?"
  - bottom: the last few things Squint said / did
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

GREEN, AMBER, RED, WHITE, GREY = (90, 200, 90), (39, 170, 245), (70, 70, 230), (245, 245, 245), (170, 170, 170)
NAMES = {"motrin": "Motrin", "tylenol": "Tylenol", "advil": "Advil", "vitamind": "Vitamin D"}
WIN = "Squint camera"


def get(url, timeout=2):
    return json.loads(urllib.request.urlopen(url, timeout=timeout).read())


class Pi:
    """Polls the Pi's state in the background so the video never waits on HTTP."""

    def __init__(self, host):
        self.api = f"http://{host}:8081"
        self.health, self.bottle, self.doses, self.ok = {}, {}, {}, False
        self.feed = []
        for fn in (self._poll, self._events):
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
                            txt, col = f"Hand to mouth ({ev.get('confidence')})", AMBER
                        else:
                            continue
                        self.feed = (self.feed + [(time.strftime("%H:%M"), txt, col)])[-4:]
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
        top, col = ("At the counter: " + ", ".join(here)) if here else "Nobody at the counter", WHITE
    cv2.rectangle(frame, (0, 0), (w, 40), (25, 25, 25), -1)
    cv2.putText(frame, top, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.75, col, 2, cv2.LINE_AA)
    # bottom: recent things said / done
    for i, (ts, txt, c) in enumerate(reversed(pi.feed)):
        label(frame, f"{ts}  {txt}"[:90], (12, h - 14 - 30 * i), c, 0.55, 1)
    return frame


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pi", default="172.20.10.9")
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--stream", help="default: the Pi's small preview (480x272, 5 fps). "
                    "http://<pi>:8080/stream for the full camera (heavier on the Pi and Wi-Fi)")
    a = ap.parse_args()
    pi = Pi(a.pi)
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, 960, 544)
    full = a.fullscreen
    if full:
        cv2.setWindowProperty(WIN, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cam = None
    while True:
        try:
            if cam is None:
                cam = Camera(a.stream or f"http://{a.pi}:8081/preview.mjpg")
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
        cv2.imshow(WIN, frame)
        k = cv2.waitKey(1) & 0xFF
        if k == ord("q"):
            break
        if k == ord("f"):
            full = not full
            cv2.setWindowProperty(WIN, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN if full else cv2.WINDOW_NORMAL)


if __name__ == "__main__":
    main()
