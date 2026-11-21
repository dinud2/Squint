"""C2: per-frame latency of each stage, with ONNX Runtime and OpenCV DNN.

    python tools/speed_test.py            # laptop
    SQUINT_BACKEND=cv2 python tools/speed_test.py
Run the same on the Pi (C3) to fill the latency table.
"""
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def bench(fn, n=100):
    for _ in range(5):
        fn()
    ts = []
    for _ in range(n):
        t = time.perf_counter(); fn(); ts.append((time.perf_counter() - t) * 1000)
    return np.median(ts), np.percentile(ts, 95)


def main():
    from squint_vision.bottles import BASE_MODEL, TRAINED_MODEL, Embedder
    from squint_vision.intake import IntakeDetector
    from squint_vision.pose import Pose
    from sim.pose_sim import simulate
    rng = np.random.default_rng(0)
    frame = rng.integers(0, 255, (480, 640, 3), np.uint8)
    crop = rng.integers(0, 255, (180, 180, 3), np.uint8)
    rows = []
    for backend in ("ort", "cv2"):
        os.environ["SQUINT_BACKEND"] = backend
        try:
            p = Pose(); rows.append((f"pose MoveNet ({backend})", *bench(lambda: p(frame))))
        except Exception as e:
            rows.append((f"pose MoveNet ({backend})", float("nan"), float("nan"))); print(" ", backend, "pose:", str(e)[:80])
        for name, path in (("bottle embed, trained", TRAINED_MODEL), ("bottle embed, base", BASE_MODEL)):
            if not os.path.exists(path):
                continue
            try:
                e = Embedder(path); rows.append((f"{name} ({backend})", *bench(lambda: e(crop))))
            except Exception as ex:
                rows.append((f"{name} ({backend})", float("nan"), float("nan"))); print(" ", backend, name, str(ex)[:80])
    seq = simulate("bottle_to_mouth", rng, fps=15)
    det = IntakeDetector()
    i = [0]

    def one():
        k = seq["kps"][i[0] % len(seq["kps"])]
        det.update(float(i[0]) / 15, k, True); i[0] += 1
    rows.append(("intake features + MLP", *bench(one, 500)))
    print(f"{'stage':38s} {'median ms':>10s} {'p95 ms':>8s}")
    for r in rows:
        print(f"{r[0]:38s} {r[1]:10.2f} {r[2]:8.2f}")


if __name__ == "__main__":
    main()
