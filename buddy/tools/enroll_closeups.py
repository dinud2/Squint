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

import cv2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="medication id (GET /medications)")
    ap.add_argument("--pi", default="172.20.10.9")
    ap.add_argument("photos", nargs="+")
    a = ap.parse_args()
    for p in a.photos:
        img = cv2.imread(p)
        if img is None:
            print(f"  skip {p}: not an image")
            continue
        h, w = img.shape[:2]
        if max(h, w) > 1600:  # phone photos are huge; the Pi only needs ~ box size
            s = 1600 / max(h, w)
            img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
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
