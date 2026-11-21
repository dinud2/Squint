"""C5: recorded clips -> pose sequences in the simulator's format (auto-labelled).

    python tools/extract_pose.py            # data/clips/*.mp4 -> data/clips_pose/*.npz

For intake clips, contact = first frame where the hand is within CONTACT_D of the
mouth; onset = last frame before that where the hand was still near its resting
distance. Check a few by eye with --show; fix any in the .json with
"t_on"/"t_contact" overrides and they win.
"""
import argparse
import glob
import json
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from squint_vision import intake as I  # noqa: E402
from squint_vision.pose import Pose  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", default=os.path.join(HERE, "data", "clips"))
    ap.add_argument("--out", default=os.path.join(HERE, "data", "clips_pose"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    pose = Pose()
    for path in sorted(glob.glob(os.path.join(a.clips, "*.mp4"))):
        meta = json.load(open(path[:-4] + ".json"))
        cap = cv2.VideoCapture(path)
        # the recorder stores the measured rate; mp4 containers can round it
        fps = float(meta.get("fps") or cap.get(cv2.CAP_PROP_FPS) or 15)
        T, K = [], []
        while True:
            ok, fr = cap.read()
            if not ok:
                break
            T.append(len(T) / fps); K.append(pose(fr))
        T, K = np.array(T, np.float32), np.array(K, np.float32)
        fs, D = I.FeatureStream(), []
        for t, k in zip(T, K):
            _, ff = fs.update(float(t), k)
            D.append(ff["d"] if ff else np.nan)
        D = np.array(D)
        t_on = t_contact = None
        if meta["label"]:
            hit = np.where(D < I.CONTACT_D)[0]
            if len(hit):
                c = hit[0]
                rest = np.nanmedian(D[:max(3, c // 3)])
                before = np.where(D[:c] > rest - 0.15)[0]
                t_on = float(T[before[-1]]) if len(before) else float(T[0])
                t_contact = float(T[c])
        meta = {"kind": meta["kind"], "label": int(meta["label"]),
                "t_on": float(meta.get("t_on", t_on if t_on is not None else 0.0)),
                "t_contact": meta.get("t_contact", t_contact), "fps": fps}
        if meta["label"] and meta["t_contact"] is None:
            print("  !! no contact found, skipping", path)
            continue
        armed = np.full(len(T), bool(json.load(open(path[:-4] + ".json")).get("armed", False)))
        out = os.path.join(a.out, os.path.basename(path)[:-4] + ".npz")
        np.savez(out, t=T, kps=K, armed=armed, meta=json.dumps(meta))
        print(f"{os.path.basename(path)}: {len(T)} frames  t_on={meta['t_on']}  t_contact={meta['t_contact']}")


if __name__ == "__main__":
    main()
