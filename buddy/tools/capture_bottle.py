"""Record more classifier training pictures of one bottle, from the Pi's camera.

    python tools/capture_bottle.py motrin --seconds 40      # -> data/train_raw/motrin/*.jpg

A window shows the camera and the box; after an 8 s countdown it saves the box (the same crop
the Pi classifies) every 0.4 s. Hold the bottle in the box and turn it slowly, nearer and
further. Then: tools/clean_bottle_data.py, tools/train_bottle_classifier.py. q stops early.
"""
import argparse
import os
import sys
import time

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from buddy.bottle_service import CENTER, center_crop  # noqa: E402
from buddy.camera import Camera  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--seconds", type=float, default=40)
    ap.add_argument("--every", type=float, default=0.4)
    ap.add_argument("--pi", default="172.20.10.9")
    ap.add_argument("--out", default=os.path.join(HERE, "data", "train_raw"))
    a = ap.parse_args()
    out = os.path.join(a.out, a.name)
    os.makedirs(out, exist_ok=True)
    cam = Camera(f"http://{a.pi}:8080/stream")
    start, last, n = time.time() + 8, 0.0, 0
    while time.time() < start + a.seconds:
        _, frame = cam.read()
        now = time.time()
        h, w = frame.shape[:2]
        x0, y0, x1, y1 = int(CENTER[0] * w), int(CENTER[1] * h), int(CENTER[2] * w), int(CENTER[3] * h)
        if now >= start and now - last >= a.every:
            cv2.imwrite(os.path.join(out, f"{int(now * 1000)}.jpg"), center_crop(frame)[0])
            last, n = now, n + 1
        view = frame.copy()
        rec = now >= start
        cv2.rectangle(view, (x0, y0), (x1, y1), (60, 60, 230) if rec else (200, 200, 200), 3)
        msg = (f"RECORDING {a.name}: {n} saved, {start + a.seconds - now:.0f} s left - turn it slowly"
               if rec else f"{a.name}: hold it in the box... {start - now:.0f}")
        cv2.putText(view, msg, (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.imshow("squint capture", view)
        if (cv2.waitKey(1) & 0xFF) == ord("q"):
            break
    cam.close()
    print(f"saved {n} pictures of {a.name} to {out}")


if __name__ == "__main__":
    main()
