"""Live check of face recognition: who does the counter camera think it sees?

    python tools/face_live.py --source http://172.20.10.9:8080/stream          # window
    python tools/face_live.py --source http://172.20.10.9:8080/stream --no-show  # print only (Pi)
"""
import argparse
import os
import sys
import time

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from buddy.camera import Camera  # noqa: E402
from buddy.faces import FaceID  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="http://172.20.10.9:8080/stream")
    ap.add_argument("--no-show", action="store_true")
    a = ap.parse_args()
    fid, cam = FaceID(), Camera(a.source)
    print("enrolled:", sorted(fid.people))
    last = None
    colors = [(0, 200, 0), (255, 160, 0), (200, 0, 200), (0, 200, 200)]
    while True:
        t, fr = cam.read()
        t0 = time.time()
        seen = fid.identify_all(fr)
        ms = (time.time() - t0) * 1000
        summary = tuple(sorted(n for _, n, _, _ in seen)) or ("nobody",)
        if summary != last:
            parts = [f"{n} {s:.2f}" for _, n, s, _ in seen] or ["nobody"]
            print(f"{time.strftime('%H:%M:%S')} {' | '.join(parts)}   {ms:.0f} ms")
            last = summary
        if not a.no_show:
            for k, (face, name, score, sc) in enumerate(seen):
                x, y, w, h = face[:4].astype(int)
                col = colors[k % len(colors)] if name != "unknown" else (0, 165, 255)
                cv2.rectangle(fr, (x, y), (x + w, y + h), col, 2)
                cv2.putText(fr, f"{name} {score:.2f}", (x, max(25, y - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, col, 2)
            cv2.putText(fr, f"{len(seen)} face(s)  {ms:.0f} ms", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.imshow("faces", fr)
            if (cv2.waitKey(1) & 0xFF) == ord("q"):
                break


if __name__ == "__main__":
    main()
