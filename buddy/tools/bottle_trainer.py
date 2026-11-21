"""Live bottle training window: see whether the medicine is recognised, and enrol it.

    python tools/bottle_trainer.py                    # Pi at 172.20.10.9
    python tools/bottle_trainer.py --pi 172.20.10.9

Shows the camera with the box the bottle has to be held in. The box turns green with the
medicine's name when the Pi recognises it; the panel lists every enrolled bottle's score
live (the Pi's own result, GET /bottles/last).

Keys (click the window first):
  1..9   pick what to enrol (the medications, then _other = "not a medicine")
  e      start / stop enrolling it: one photo every 0.6 s while on; turn the bottle slowly
  r      press twice: forget the picked one and start again
  q      quit
"""
import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from buddy.bottle_service import CENTER  # noqa: E402
from buddy.camera import Camera  # noqa: E402

GREEN, GREY, WHITE, AMBER, DIM = (80, 200, 80), (150, 150, 150), (255, 255, 255), (39, 159, 239), (110, 110, 110)


class Pi:
    def __init__(self, host):
        self.api = f"http://{host}:8081"
        self.last = {}
        self.counts = {}
        self.error = None
        threading.Thread(target=self._poll, daemon=True).start()

    def get(self, path):
        return json.loads(urllib.request.urlopen(self.api + path, timeout=5).read())

    def post(self, path):
        req = urllib.request.Request(self.api + path, data=b"", method="POST")
        try:
            return json.loads(urllib.request.urlopen(req, timeout=15).read())
        except urllib.error.HTTPError as e:
            return json.loads(e.read())

    def _poll(self):
        n = 0
        while True:
            try:
                self.last = self.get("/bottles/last")
                if n % 10 == 0:
                    self.counts = self.get("/bottles").get("bottles", {})
                self.error = None
            except Exception as e:
                self.error = str(e)
            n += 1
            time.sleep(0.15)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pi", default="172.20.10.9")
    a = ap.parse_args()
    pi = Pi(a.pi)
    for attempt in range(30):  # the laptop may still be rejoining the hotspot
        try:
            targets = [m["id"] for m in pi.get("/medications")] + ["_other"]
            break
        except Exception as e:
            print(f"cannot reach the Pi at {pi.api} ({e}); retrying...", flush=True)
            time.sleep(2)
    else:
        sys.exit(f"cannot reach the Pi at {pi.api}: is this laptop on the same Wi-Fi as the Pi?")
    cam = Camera(f"http://{a.pi}:8080/stream")
    sel, enrolling, last_shot, reset_armed = 0, False, 0.0, 0.0
    status = ""

    def shoot(name):
        nonlocal status
        r = pi.post(f"/bottles/enroll?name={name}")
        status = r.get("error") or f"{name}: {r.get('photos')} photos"

    while True:
        try:
            _, frame = cam.read()
        except TimeoutError:
            # stream dropped (Wi-Fi switch, Pi restart): keep the window open and retry
            status = "no camera frames: is the laptop on the hotspot? retrying..."
            if (cv2.waitKey(500) & 0xFF) == ord("q"):
                break
            continue
        h, w = frame.shape[:2]
        last = pi.last or {}
        name, score = last.get("name", "unknown"), last.get("score", 0.0)
        found = name not in ("unknown", None)
        x0, y0, x1, y1 = int(CENTER[0] * w), int(CENTER[1] * h), int(CENTER[2] * w), int(CENTER[3] * h)
        col = GREEN if found else GREY
        cv2.rectangle(frame, (x0, y0), (x1, y1), col, 4 if found else 2)
        label = f"{name.upper()}  {score:.2f}" if found else "no medicine"
        cv2.putText(frame, label, (x0 + 12, y0 + 44), cv2.FONT_HERSHEY_SIMPLEX, 1.3, col, 3)
        if found and last.get("shown") == name:
            cv2.putText(frame, "shown -> sent to Squint", (x0 + 12, y0 + 84), cv2.FONT_HERSHEY_SIMPLEX, 0.8, col, 2)

        # side panel: live scores and training controls
        panel = 340
        canvas = cv2.copyMakeBorder(frame, 0, 0, 0, panel, cv2.BORDER_CONSTANT, value=(20, 20, 20))
        px, y = w + 16, 36
        cv2.putText(canvas, "live scores", (px, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, DIM, 2)
        scores = last.get("scores", {})
        for k in targets:
            y += 34
            s = scores.get(k)
            bar = int(max(0.0, min(1.0, s or 0.0)) * 200)
            c = GREEN if k == name else (AMBER if k == "_other" else GREY)
            cv2.rectangle(canvas, (px, y - 18), (px + bar, y - 4), c, -1)
            cv2.putText(canvas, f"{k}  {'' if s is None else f'{s:.2f}'}  ({pi.counts.get(k, 0) // 6} ph)",
                        (px, y - 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, WHITE, 1)
            y += 8
        y += 30
        cv2.putText(canvas, "enrol (keys 1-%d):" % len(targets), (px, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, DIM, 2)
        for i, k in enumerate(targets):
            y += 28
            mark = ">" if i == sel else " "
            cv2.putText(canvas, f"{mark} {i + 1}  {k}", (px, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                        GREEN if i == sel else WHITE, 2 if i == sel else 1)
        y += 40
        cv2.putText(canvas, "ENROLLING  (e = stop)" if enrolling else "e = start enrolling", (px, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255) if enrolling else WHITE, 2)
        y += 28
        cv2.putText(canvas, "r r = reset   q = quit", (px, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, DIM, 1)
        y += 32
        cv2.putText(canvas, (pi.error or status)[:38], (px, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (0, 0, 255) if pi.error else WHITE, 1)
        cv2.imshow("squint bottle trainer", canvas)

        if enrolling and time.time() - last_shot > 0.6:
            last_shot = time.time()
            threading.Thread(target=shoot, args=(targets[sel],), daemon=True).start()

        k = cv2.waitKey(1) & 0xFF
        if k == ord("q"):
            break
        if ord("1") <= k <= ord("9") and k - ord("1") < len(targets):
            sel, enrolling = k - ord("1"), False
        elif k == ord("e"):
            enrolling = not enrolling
        elif k == ord("r"):
            if time.time() - reset_armed < 1.5:
                status = json.dumps(pi.post(f"/bottles/reset?name={targets[sel]}"))
                reset_armed = 0.0
            else:
                reset_armed, status = time.time(), f"press r again to forget {targets[sel]}"
    cam.close()


if __name__ == "__main__":
    main()
