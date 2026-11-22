"""Record full camera frames of one bottle (or of no bottle) for tools/train_label_classifier.py.

    python tools/capture_frames.py advil --tag kathy-window --seconds 40
    python tools/capture_frames.py _other --tag red-shirt              # hands, faces, clothes, cups...

Saves the Pi's whole 960x544 frame every 0.4 s to <out>/<name>/<date-time>_<tag>/, one folder per
recording session (the trainer holds out whole sessions). The window shows the colour patches the
Pi would find (loose ranges), so you can see the label is being picked up.

For a model that works anywhere, vary one thing per session: who holds it (Dinu, Kathy), where
(counter, window, kitchen, another room), light (lamp, daylight, dim), distance (close, arm's
length, across the counter), angle (tilted, turned, fingers over part of the label). Also record
_other sessions with red / blue / orange clothes, a red water bottle, empty hands, faces.
"""
import argparse
import os
import sys
import time

import cv2

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from buddy import colors  # noqa: E402
from buddy.camera import Camera  # noqa: E402

DRAW = {"advil": (255, 80, 0), "motrin": (0, 140, 255), "red": (0, 0, 255)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name", help="advil / motrin / tylenol / vitamind / _other")
    ap.add_argument("--tag", default="", help="what is different this time, e.g. kathy-dim-far")
    ap.add_argument("--seconds", type=float, default=40)
    ap.add_argument("--every", type=float, default=0.4)
    ap.add_argument("--pi", default="172.20.10.9")
    ap.add_argument("--out", default=os.path.join(HERE, "data", "frames"))
    a = ap.parse_args()
    session = time.strftime("%Y%m%d-%H%M%S") + (f"_{a.tag}" if a.tag else "")
    out = os.path.join(a.out, a.name, session)
    os.makedirs(out, exist_ok=True)
    cam = Camera(f"http://{a.pi}:8080/stream")
    start, last, n = time.time() + 6, 0.0, 0
    while time.time() < start + a.seconds:
        _, frame = cam.read()
        if frame is None:
            continue
        now = time.time()
        if now >= start and now - last >= a.every:
            cv2.imwrite(os.path.join(out, f"{int(now * 1000)}.jpg"), frame)
            last, n = now, n + 1
        view = frame.copy()
        for f in colors.find(frame, loose=True)[:3]:
            x0, y0, x1, y1 = f["box"]
            cv2.rectangle(view, (x0 - 4, y0 - 4), (x1 + 4, y1 + 4), DRAW[f["name"]], 2)
        rec = now >= start
        msg = (f"RECORDING {a.name} {a.tag}: {n} saved, {start + a.seconds - now:.0f} s left"
               if rec else f"{a.name}: get ready... {start - now:.0f}")
        cv2.putText(view, msg, (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (60, 60, 230) if rec else (255, 255, 255), 2)
        cv2.imshow("squint capture", view)
        if (cv2.waitKey(1) & 0xFF) == ord("q"):
            break
    cam.close()
    print(f"saved {n} frames to {out}")


if __name__ == "__main__":
    main()
