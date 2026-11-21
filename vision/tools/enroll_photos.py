"""Enrol a bottle from phone photos (adds to any live enrolment already saved).

    python tools/enroll_photos.py --med tylenol photo1.jpg photo2.jpg ...
    python tools/enroll_photos.py --med omega369 --append more1.jpg more2.jpg
    python tools/send.py meds_changed        # a running vision_main reloads the gallery

Phone photos are sharp, high-res and centred on the bottle; live crops from the
Pi are ~150 px boxes around the wrist, often blurry, with the bottle partly cut
off. So each photo is turned into several views that look more like live crops:
random crops at different zooms and offsets, shrunk to live resolution, slight
blur, brightness/contrast changes and small rotations.

Live enrolment (tools/send.py enroll_start med=...) is still the better source;
use photos to add angles the live enrolment missed, or to bootstrap a bottle.
"""
import argparse
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from squint_vision.bottles import Embedder, Gallery  # noqa: E402

LIVE_PX = 150   # typical hand-crop size on the 640x480 stream


def views(img, n, rng):
    h, w = img.shape[:2]
    out = []
    for i in range(n):
        if i == 0:
            frac, cx, cy = 0.85, 0.5, 0.5                  # one plain, centred view
        else:
            frac = rng.uniform(0.55, 1.0)                  # zoom: part of the bottle .. whole photo
            cx, cy = rng.uniform(0.35, 0.65), rng.uniform(0.35, 0.7)
        s = int(frac * min(h, w))
        x0 = int(np.clip(cx * w - s / 2, 0, w - s))
        y0 = int(np.clip(cy * h - s / 2, 0, h - s))
        v = img[y0:y0 + s, x0:x0 + s]
        if i:
            ang = rng.uniform(-15, 15)
            M = cv2.getRotationMatrix2D((s / 2, s / 2), ang, 1.0)
            v = cv2.warpAffine(v, M, (s, s), borderMode=cv2.BORDER_REFLECT)
        px = int(rng.uniform(0.7, 1.3) * LIVE_PX) if i else LIVE_PX
        v = cv2.resize(v, (px, px), interpolation=cv2.INTER_AREA)
        if i:
            k = int(rng.choice([1, 3, 5]))
            if k > 1:
                v = cv2.GaussianBlur(v, (k, k), 0)
            v = cv2.convertScaleAbs(v, alpha=rng.uniform(0.75, 1.25), beta=rng.uniform(-25, 25))
        out.append(v)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--med", required=True)
    ap.add_argument("--append", action="store_true", help="keep this bottle's existing embeddings")
    ap.add_argument("--per-photo", type=int, default=12)
    ap.add_argument("--save-views", action="store_true", help="write the views to data/enroll/<med>/photos/")
    ap.add_argument("photos", nargs="+")
    a = ap.parse_args()

    rng = np.random.default_rng(0)
    emb, gal = Embedder(), Gallery()
    new, all_views = [], []
    for p in a.photos:
        img = cv2.imread(p)
        if img is None:
            sys.exit(f"cannot read {p}")
        vs = views(img, a.per_photo, rng)
        all_views += vs
        new += [emb(v) for v in vs]
    old = gal.items.get(a.med)
    if a.append and old is not None:
        embs = np.concatenate([old, np.asarray(new, np.float32)])
    else:
        embs = np.asarray(new, np.float32)
    gal.add(a.med, embs)
    if a.save_views:
        d = os.path.join(os.path.dirname(gal.dir), "enroll", a.med, "photos")
        os.makedirs(d, exist_ok=True)
        for i, v in enumerate(all_views):
            cv2.imwrite(os.path.join(d, f"{i:03d}.jpg"), v)
    kept = 0 if old is None or not a.append else len(old)
    print(f"{a.med}: {len(new)} photo views + {kept} existing = {len(embs)} embeddings")


if __name__ == "__main__":
    main()
