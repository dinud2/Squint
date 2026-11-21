"""Which medicine am I holding? Live recognition from the laptop webcam.

    python tools/webcam_meds.py                 # first run builds the gallery from the enrol photos
    python tools/webcam_meds.py --rebuild       # rebuild it (e.g. after adding enrol photos)
    python tools/webcam_meds.py --cam 1

Same recogniser as the Pi ("show" mode, buddy/bottles.py): hold the bottle up inside the box,
close enough to fill it. The gallery starts from vision/data/enroll/<name>/ (omega369 incl. its
phone photos, tylenol, and _empty -> _other = "not a medicine") and is kept in
data/bottles_webcam/, separate from the Pi's gallery.

Every time a medicine is recognised steadily (3 checks in a row) it is logged to
data/med_sightings.jsonl and listed in the panel as "seen today".

Keys (click the window first):
  0      toggle enrolling _other from this webcam (empty view, your face, hands, a cup...).
         Do this once without any medicine: this laptop's room isn't in the enrol photos.
  1..9   toggle enrolling the Nth medicine from this webcam (one photo every 0.5 s; turn it slowly)
  q      quit
"""
import argparse
import datetime
import glob
import json
import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from buddy.bottle_service import CENTER, OTHER, ShowTracker, center_crop  # noqa: E402
from buddy.bottles import Embedder, Gallery  # noqa: E402

ENROLL = os.path.join(os.path.dirname(HERE), "vision", "data", "enroll")
GALLERY = os.path.join(HERE, "data", "bottles_webcam")
LOG = os.path.join(HERE, "data", "med_sightings.jsonl")
ALIASES = {"_empty": OTHER}
GREEN, WHITE, GREY, AMBER, RED = (80, 200, 80), (255, 255, 255), (150, 150, 150), (39, 159, 239), (60, 60, 220)


def augment(img, rng, n):
    """img + n-1 webcam-like versions: a little cropped / rotated, other light, blur, JPEG."""
    out = [img]
    h, w = img.shape[:2]
    for _ in range(n - 1):
        s = rng.uniform(0.82, 1.0)
        cw, ch = int(w * s), int(h * s)
        x0, y0 = int(rng.uniform(0, w - cw + 1)), int(rng.uniform(0, h - ch + 1))
        v = img[y0:y0 + ch, x0:x0 + cw]
        M = cv2.getRotationMatrix2D((cw / 2, ch / 2), rng.uniform(-10, 10), 1.0)
        v = cv2.warpAffine(v, M, (cw, ch), borderMode=cv2.BORDER_REFLECT)
        v = cv2.convertScaleAbs(v, alpha=rng.uniform(0.75, 1.2), beta=rng.uniform(-25, 25))
        if rng.random() < 0.5:
            v = cv2.GaussianBlur(v, (3, 3), 0)
        v = cv2.imdecode(cv2.imencode(".jpg", v, [cv2.IMWRITE_JPEG_QUALITY, int(rng.uniform(40, 85))])[1],
                         cv2.IMREAD_COLOR)
        out.append(v)
    return out


def build_gallery(emb, n_aug=4):
    rng = np.random.default_rng(0)
    gal = Gallery(GALLERY, center=True)
    for d in sorted(os.listdir(ENROLL)):
        files = sorted(glob.glob(os.path.join(ENROLL, d, "*.jpg")) + glob.glob(os.path.join(ENROLL, d, "*", "*.jpg")))
        name = ALIASES.get(d, d)
        embs = [emb(v) for f in files if (img := cv2.imread(f)) is not None for v in augment(img, rng, n_aug)]
        if embs:
            gal.add(name, np.array(embs))       # replaces the old file
            print(f"  {name}: {len(files)} photos -> {len(embs)} embeddings")
    return gal


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cam", default="0", help="webcam index or stream URL")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--fps", type=float, default=6, help="recognitions per second")
    a = ap.parse_args()

    emb = Embedder()
    if a.rebuild or not glob.glob(os.path.join(GALLERY, "*.npy")):
        print(f"building gallery from {ENROLL}")
        gal = build_gallery(emb)
    else:
        gal = Gallery(GALLERY, center=True)
    meds = sorted(n for n in gal.items if n != OTHER)
    print("medicines:", ", ".join(meds))

    cap = cv2.VideoCapture(int(a.cam) if a.cam.isdigit() else a.cam)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)
    if not cap.isOpened():
        sys.exit(f"cannot open camera {a.cam}")

    show, seen = ShowTracker(), {}
    today = datetime.date.today().isoformat()
    if os.path.exists(LOG):
        for line in open(LOG):
            r = json.loads(line)
            if r["time"].startswith(today):
                seen[r["bottle"]] = r["time"][11:16]
    enrolling, last_enrol, last_rec = None, 0.0, 0.0
    name, score, scores = "unknown", 0.0, {}
    cv2.namedWindow("meds", cv2.WINDOW_NORMAL)
    while True:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.05)
            continue
        frame = cv2.flip(frame, 1)                # mirror, so moving the bottle feels natural
        t = time.time()
        crop, box = center_crop(frame)

        if enrolling and t - last_enrol >= 0.5:
            gal.add(enrolling, [emb(crop)], append=True)
            meds = sorted(n for n in gal.items if n != OTHER)
            last_enrol = t
        if t - last_rec >= 1.0 / a.fps:
            last_rec = t
            name, score, scores = gal.identify(emb(crop))
            if name == OTHER:
                name = "unknown"
            for ev in show.update(t, name, score):
                now = datetime.datetime.now().isoformat(timespec="seconds")
                seen[ev["bottle"]] = now[11:16]
                with open(LOG, "a") as f:
                    f.write(json.dumps({"time": now, "bottle": ev["bottle"], "score": ev["score"]}) + "\n")
                print(f"{now}  {ev['bottle']}  ({ev['score']:.2f})", flush=True)

        # --- draw
        known = name != "unknown"
        col = AMBER if enrolling else GREEN if known else GREY
        cv2.rectangle(frame, tuple(box[:2]), tuple(box[2:]), col, 3)
        label = f"enrolling {enrolling} ({len(gal.items.get(enrolling, []))})" if enrolling else \
            f"{name}  {score:.2f}" if known else "hold a bottle in the box"
        cv2.putText(frame, label, (box[0], box[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, col, 2)
        y = 30
        for n, s in sorted(scores.items(), key=lambda kv: -kv[1]):
            cv2.putText(frame, f"{n:10s} {s:+.2f}", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        GREEN if n == name else WHITE, 1)
            y += 24
        y += 10
        cv2.putText(frame, "seen today:", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, WHITE, 1)
        for n in meds:
            y += 24
            cv2.putText(frame, f"  {n:10s} {seen.get(n, '-')}", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        GREEN if n in seen else GREY, 1)
        keys = "  ".join(f"{i + 1}={n}" for i, n in enumerate(meds))
        cv2.putText(frame, f"enrol: 0=_other  {keys}   q=quit", (10, frame.shape[0] - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, WHITE, 1)
        cv2.imshow("meds", frame)

        k = cv2.waitKey(1) & 0xFF
        if k == ord("q"):
            break
        if ord("0") <= k <= ord("9"):
            i = k - ord("0")
            target = OTHER if i == 0 else meds[i - 1] if i <= len(meds) else None
            enrolling = None if enrolling == target else target
            print("enrolling:", enrolling or "off", flush=True)
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
