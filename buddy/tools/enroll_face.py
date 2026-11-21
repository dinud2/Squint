"""Enrol one person's face from the counter camera.

    python tools/enroll_face.py --name dinu  --source http://172.20.10.9:8080/stream
    python tools/enroll_face.py --name kathy --source http://172.20.10.9:8080/stream

Stand where you normally would at the counter. The window counts down, then walks you
through a few poses (look at the device, turn a little left/right, chin up/down, step
closer/back) while it collects ~40 face photos. A photo is only kept when there is one
big, sharp face and it isn't a near-copy of one already taken, so the set is varied.

Saves data/faces/<name>/NNN.jpg (aligned 112x112 crops), data/faces/<name>/full/NNN.jpg
(the camera frames), and data/faces/<name>.npy (embeddings used for recognition).
--append adds to an existing enrolment instead of replacing it.
"""
import argparse
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from buddy.camera import Camera  # noqa: E402
from buddy.faces import GALLERY_DIR, FaceID, sharpness  # noqa: E402

POSES = [("Look at the device", 7), ("Turn your head a little LEFT", 6), ("Turn your head a little RIGHT", 6),
         ("Chin a little UP", 5), ("Chin a little DOWN", 5), ("Step a little CLOSER", 6),
         ("Step BACK (arm's length +)", 7), ("Look at the device, relax", 6)]
GAP_S = 0.3              # at most ~3 photos per second
DUP_COS = 0.96           # skip a photo this similar to one already kept
MIN_SHARP = 25.0
SAME_PERSON = 0.30       # after SEED photos, a face must match their average this well
SEED = 5                 # (first enrolment of Dinu caught Kathy walking into view: 7 of 40)


def banner(img, lines, color):
    out = img.copy()
    cv2.rectangle(out, (0, 0), (out.shape[1], 30 + 55 * len(lines)), (0, 0, 0), -1)
    for i, (txt, scale) in enumerate(lines):
        cv2.putText(out, txt, (15, 50 + 55 * i), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 3)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--source", default="http://172.20.10.9:8080/stream")
    ap.add_argument("--shots", type=int, default=40)
    ap.add_argument("--lead", type=float, default=8.0, help="countdown to get into place")
    ap.add_argument("--append", action="store_true")
    a = ap.parse_args()

    fid, cam = FaceID(), Camera(a.source)
    d = os.path.join(GALLERY_DIR, a.name)
    if not a.append and os.path.isdir(d):            # fresh enrolment: drop the old photos
        import shutil
        shutil.rmtree(d)
    os.makedirs(os.path.join(d, "full"), exist_ok=True)
    old = list(fid.people.get(a.name, [])) if a.append else []
    ref = np.mean(old, 0) if len(old) >= SEED else None   # who we're enrolling
    start_i = len(old)

    end = time.time() + a.lead
    while time.time() < end:
        _, fr = cam.read()
        cv2.imshow("enrol", banner(fr, [(f"Enrolling {a.name}", 1.2), (f"get in place... {int(end - time.time()) + 1}", 1.4)],
                                   (0, 255, 255)))
        if (cv2.waitKey(1) & 0xFF) == ord("q"):
            return

    embs, last_t = [], 0.0
    for prompt, secs in POSES:
        end = time.time() + secs
        while time.time() < end and len(embs) < a.shots:
            t, fr = cam.read()
            face = fid.main_face(fr)
            show = fr.copy()
            status = "no face (move closer / into view)"
            if face is not None:
                x, y, w, h = face[:4].astype(int)
                cv2.rectangle(show, (x, y), (x + w, y + h), (0, 255, 0), 2)
                status = f"face {w}x{h}"
                if t - last_t >= GAP_S:
                    al = fid.align(fr, face)
                    sh = sharpness(al)
                    if sh < MIN_SHARP:
                        status += "  (blurry, hold still)"
                    else:
                        e = fid.embed(al)
                        if ref is None and len(embs) >= SEED:
                            ref = np.mean(embs, 0)
                        if ref is not None and float(e @ ref) / (np.linalg.norm(ref) + 1e-8) < SAME_PERSON:
                            status += "  (different person? only the enrollee in view)"
                        elif embs and max(float(e @ k) for k in embs) > DUP_COS:
                            status += "  (same as before, keep moving)"
                        else:
                            i = start_i + len(embs)
                            cv2.imwrite(os.path.join(d, f"{i:03d}.jpg"), al)
                            cv2.imwrite(os.path.join(d, "full", f"{i:03d}.jpg"), fr)
                            embs.append(e)
                            last_t = t
            bar = int(show.shape[1] * len(embs) / a.shots)
            cv2.rectangle(show, (0, show.shape[0] - 18), (bar, show.shape[0]), (0, 200, 0), -1)
            cv2.imshow("enrol", banner(show, [(prompt, 1.2), (f"{len(embs)}/{a.shots}  {status}", 0.8)],
                                       (255, 255, 255)))
            if (cv2.waitKey(1) & 0xFF) == ord("q"):
                break
        if len(embs) >= a.shots:
            break
    cam.close()
    cv2.destroyAllWindows()
    if len(embs) < 10:
        print(f"only {len(embs)} usable photos: nothing saved to the gallery. Check lighting/framing and retry.")
        return 1
    fid.save_person(a.name, old + embs)
    print(f"{a.name}: {len(embs)} new photos ({len(old) + len(embs)} total) -> {GALLERY_DIR}/{a.name}.npy")
    if len(fid.people) > 1:
        sims = {o: float(np.mean(np.asarray(embs) @ fid.people[o].T)) for o in fid.people if o != a.name}
        print("mean similarity to other people (lower is better):", {k: round(v, 3) for k, v in sims.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
