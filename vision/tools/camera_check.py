"""Is this camera good enough for Squint? Run it before anything else.

    python tools/camera_check.py --source 0                               # laptop webcam
    python tools/camera_check.py --source http://<pi-ip>:8080/stream      # Dinu's QNX camstream
    python tools/camera_check.py --source http://localhost:8080/stream    # on the Pi itself
    add --show for a live window, --seconds N to run longer

Reports: real fps and frame gaps, decode + pose time, and FRAMING: how often the
nose, both shoulders and both wrists are visible. Squint needs the face AND the
hands in view (stand where Margaret stands, raise a hand to your mouth).
Saves data/camera_check.jpg with the skeleton drawn on it.
"""
import argparse
import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from squint_vision import pose as P  # noqa: E402
from squint_vision.camera import Camera  # noqa: E402

EDGES = [(5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (0, 1), (0, 2), (1, 3), (2, 4)]


def overlay(frame, kps):
    for a, b in EDGES:
        if kps[a, 2] > 0.2 and kps[b, 2] > 0.2:
            cv2.line(frame, tuple(map(int, kps[a, :2])), tuple(map(int, kps[b, :2])), (255, 160, 0), 2)
    for i in range(11):
        if kps[i, 2] > 0.2:
            cv2.circle(frame, tuple(map(int, kps[i, :2])), 4, (0, 255, 0), -1)
    if kps[0, 2] > 0.2:
        m = P.mouth(kps)
        cv2.circle(frame, (int(m[0]), int(m[1])), 7, (0, 0, 255), 2)
    return frame


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="0")
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--no-pose", action="store_true", help="only measure the stream")
    a = ap.parse_args()
    cam = Camera(a.source)
    pose = None if a.no_pose else P.Pose()
    ts, pose_ms, vis, shape = [], [], [], None
    best = None
    t_end = time.time() + a.seconds
    while time.time() < t_end:
        t, frame = cam.read()
        if frame is None:
            break
        ts.append(time.time())
        shape = frame.shape
        if pose:
            t0 = time.perf_counter()
            k = pose(frame)
            pose_ms.append((time.perf_counter() - t0) * 1000)
            v = k[:, 2] > 0.3
            vis.append([v[P.NOSE], v[P.LSHO] and v[P.RSHO], v[P.LWRI], v[P.RWRI]])
            if best is None or v[:11].sum() >= best[0]:
                best = (v[:11].sum(), overlay(frame.copy(), k))
            if a.show:
                cv2.imshow("camera check", overlay(frame, k))
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    if len(ts) < 2:
        print("NO FRAMES. Check the URL / that camstream is running / same network.")
        return 1
    gaps = np.diff(ts) * 1000
    print(f"source      {a.source}")
    print(f"frame size  {shape[1]}x{shape[0]}")
    print(f"fps         {len(ts) / (ts[-1] - ts[0]):.1f}   (Squint wants >= 12)")
    print(f"frame gap   median {np.median(gaps):.0f} ms, worst {gaps.max():.0f} ms")
    if pose_ms:
        print(f"pose        median {np.median(pose_ms):.1f} ms per frame")
        v = np.array(vis).mean(0) * 100
        print(f"visible     nose {v[0]:.0f}%  shoulders {v[1]:.0f}%  left wrist {v[2]:.0f}%  right wrist {v[3]:.0f}%")
        if v[0] < 80:
            print("  !! face often out of view: lower/tilt the camera, or stand further back (wide lens helps)")
        if max(v[2], v[3]) < 30:
            print("  !! wrists rarely visible: raise a hand to your mouth during the check; if still low, move the camera back")
        os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
        out = os.path.join(HERE, "data", "camera_check.jpg")
        cv2.imwrite(out, best[1])
        print(f"saved       {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
