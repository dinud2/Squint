"""Clean the bottle training photos before training (laptop).

    python tools/clean_bottle_data.py                       # data/train_raw -> data/train_clean (+ report)

The trainer recorded a photo every 0.6 s while 'e' was on, so some photos labelled as a bottle
show no bottle at all (it had left the box) but a face: those taught the old matcher that
"Dinu's face = Motrin". A photo of a bottle class is dropped when the bottle detector finds
no bottle-like object AND a face fills a good part of the picture. _other photos are kept.
Writes data/train_clean/<class>/*.jpg and data/train_clean/dropped/<class>/*.jpg (to check).
"""
import argparse
import os
import shutil
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from buddy.detector import NanoDet  # noqa: E402
from buddy.faces import FaceID  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(HERE, "data", "train_raw"))
    ap.add_argument("--dst", default=os.path.join(HERE, "data", "train_clean"))
    ap.add_argument("--face-frac", type=float, default=0.18, help="face width / photo width that counts as 'a face'")
    a = ap.parse_args()
    det, fid = NanoDet(score=0.12), FaceID()
    shutil.rmtree(a.dst, ignore_errors=True)
    for cls in sorted(os.listdir(a.src)):
        sd = os.path.join(a.src, cls)
        if not os.path.isdir(sd):
            continue
        kept = dropped = 0
        for fn in sorted(os.listdir(sd)):
            if not fn.endswith(".jpg"):
                continue
            img = cv2.imread(os.path.join(sd, fn))
            if img is None:
                continue
            drop = False
            if cls != "_other" and not fn.startswith("closeup"):
                h, w = img.shape[:2]
                bottles = [b for b in det(img) if (b[2] - b[0]) * (b[3] - b[1]) >= 0.03 * w * h]
                face = fid.main_face(img) if min(h, w) >= 60 else None
                drop = not bottles and face is not None and face[2] >= a.face_frac * w
            out = os.path.join(a.dst, "dropped", cls) if drop else os.path.join(a.dst, cls)
            os.makedirs(out, exist_ok=True)
            shutil.copy(os.path.join(sd, fn), os.path.join(out, fn))
            dropped += drop
            kept += not drop
        print(f"{cls:9s} kept {kept:4d}  dropped {dropped:3d} (face, no bottle)", flush=True)


if __name__ == "__main__":
    main()
