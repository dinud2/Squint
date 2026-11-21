"""Enrol bottles from close-up photos (e.g. taken with a phone, the bottle filling the picture).

    python tools/enroll_closeups.py --name tylenol photos/tylenol/*.jpg
    python tools/enroll_closeups.py --name motrin IMG_1234.jpg IMG_1235.jpg

Take 4-8 photos per bottle: front label, both sides, slightly tilted, in your hand, in normal
room light. Each photo is sent to the Pi, which makes 12 webcam-like versions of it (smaller,
blurred, compressed, darker / brighter) so it matches what the C270 sees in its box.
Then add live webcam photos with tools/bottle_trainer.py (same box), and _other there.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request

import os

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="medication id (GET /medications)")
    ap.add_argument("--pi", default="172.20.10.9")
    ap.add_argument("--no-crop", action="store_true", help="send the whole photo (default: crop to the bottle)")
    ap.add_argument("--save-crops", help="also write the crops to this folder, to check them")
    ap.add_argument("photos", nargs="+")
    a = ap.parse_args()
    det = None
    if not a.no_crop:
        from buddy.detector import NanoDet
        det = NanoDet(score=0.15)
    for p in a.photos:
        img = cv2.imread(p)
        if img is None:
            print(f"  skip {p}: not an image")
            continue
        h, w = img.shape[:2]
        if max(h, w) > 1600:  # phone photos are huge; the Pi only needs ~ box size
            s = 1600 / max(h, w)
            img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        if det is not None:
            # Phone photos show a lot of counter around the bottle: keep just the bottle (biggest
            # bottle-like box, a little padding) so the close-up is mostly label, like the box view.
            boxes = det(img)
            if boxes:
                x1, y1, x2, y2 = max(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))[:4]
                px, py = int(0.08 * (x2 - x1)), int(0.05 * (y2 - y1))
                img = img[max(0, y1 - py):min(h, y2 + py), max(0, x1 - px):min(w, x2 + px)]
            else:
                print(f"  {p}: no bottle found, sending the whole photo")
        if a.save_crops:
            os.makedirs(a.save_crops, exist_ok=True)
            cv2.imwrite(os.path.join(a.save_crops, f"{a.name}_{os.path.basename(p)}"), img)
        jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()
        req = urllib.request.Request(f"http://{a.pi}:8081/bottles/enroll?name={a.name}&crop=full", data=jpg,
                                     headers={"Content-Type": "image/jpeg"})
        try:
            r = json.loads(urllib.request.urlopen(req, timeout=60).read())
        except urllib.error.HTTPError as e:
            r = json.loads(e.read())
        print(f"  {p}: {r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
