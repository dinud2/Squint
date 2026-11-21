"""Bottle recognition for the bottle camera (the Brio on the Pi, or JPEGs POSTed by a client).

Two ways of using it (BottleService(mode=...)):

  "show" (default)  The person holds their bottle up to the camera ("show me your pill").
                    The middle of the frame is recognised directly, no object detector: a
                    general COCO detector often missed a pill bottle held in a hand, and every
                    miss looked like a new event. "_other" (empty view, hands, faces, cups...)
                    tells it when no medicine is being shown.
                    Event: bottle_shown {bottle, score}, once per showing (it can fire again for
                    the same bottle only after it has been out of view for CLEAR_S).
  "counter"         Bottles stand on the counter under the camera; NanoDet finds each one and
                    bottle_tracker.py reports which is lifted (bottle_picked / bottle_returned).

API (buddy/api.py):
    POST /tab5/frame                  body = JPEG -> {"bottles": [...], "events": [...], "ms": n}
    POST /bottles/enroll?name=tylenol body = JPEG, or empty = the newest camera frame
    POST /bottles/enroll?name=_other  "not a medicine" (empty view, hand, face, cup, water bottle)
    POST /bottles/reset?name=tylenol  forget a bottle
    GET  /bottles                     enrolled bottles and embedding counts
"""
import os
import threading
import time

import cv2
import numpy as np

from .bottle_tracker import BottleTracker
from .bottles import GALLERY_DIR, Embedder, Gallery, crop

OTHER = "_other"          # the "not a medicine" class: never reported as a bottle
CENTER = (0.18, 0.08, 0.82, 0.92)   # the part of the frame a held-up bottle fills (x0, y0, x1, y1)


def center_crop(img, box=CENTER):
    h, w = img.shape[:2]
    x0, y0, x1, y1 = box
    return img[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)], [int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)]


class ShowTracker:
    """bottle_shown once the same bottle is recognised in NEED frames in a row; the same bottle
    can only be shown again after it has been out of view for CLEAR_S."""
    NEED = 2
    CLEAR_S = 1.5

    def __init__(self):
        self.hist = []
        self.shown = None
        self.last_seen = {}

    def update(self, t, name, score):
        self.hist = (self.hist + [name])[-self.NEED:]
        if name != "unknown":
            self.last_seen[name] = t
        if self.shown and t - self.last_seen.get(self.shown, -1e9) > self.CLEAR_S:
            self.shown = None
        if name != "unknown" and name != self.shown and self.hist == [name] * self.NEED:
            self.shown = name
            return [{"type": "bottle_shown", "bottle": name, "score": round(score, 3)}]
        return []


def _area(b):
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def pick_enrol_box(boxes):
    """Counter mode: the enrolled bottle is the one shown up close, so ignore small boxes and,
    among the big ones, skip boxes that contain another big one (hand + bottle)."""
    top = max(_area(b) for b in boxes)
    big = [b for b in boxes if _area(b) >= 0.2 * top]

    def contains(o, i):
        ix = max(0, min(o[2], i[2]) - max(o[0], i[0])) * max(0, min(o[3], i[3]) - max(o[1], i[1]))
        return o is not i and ix >= 0.8 * _area(i)
    inner = [b for b in big if not any(contains(b, i) for i in big)] or big
    return max(inner, key=lambda b: b[4])


class BottleService:
    def __init__(self, hub=None, mode="show"):
        self.mode = mode
        self.emb, self.gallery = Embedder(), Gallery()
        self.det = None
        if mode == "counter":
            from .detector import NanoDet
            self.det = NanoDet()
        self.tracker = BottleTracker()
        self.show = ShowTracker()
        self.hub = hub
        self.lock = threading.Lock()          # cv2.dnn nets are not thread-safe
        self.last_img = None
        self.last = {"name": "unknown", "score": 0.0, "scores": {}, "t": 0.0, "shown": None}

    def frame(self, jpg):
        img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return {"error": "could not decode JPEG"}
        return self.frame_image(img)

    def frame_image(self, img):
        """One BGR frame from the bottle camera (or a JPEG a client posted)."""
        self.last_img = img
        t0 = time.time()
        with self.lock:
            if self.mode == "show":
                c, box = center_crop(img)
                name, score, sc = self.gallery.identify(self.emb(c))
                if name == OTHER:
                    name = "unknown"
                out = [{"name": name, "score": round(score, 3), "box": box}]
                events = self.show.update(time.time(), name, score)
                on_counter = []
                self.last = {"name": name, "score": round(score, 3), "t": time.time(), "shown": self.show.shown,
                             "scores": {k: round(v, 3) for k, v in sorted(sc.items(), key=lambda kv: -kv[1])}}
            else:
                out = []
                for b in self.det(img)[:6]:
                    name, score, _ = self.gallery.identify(self.emb(crop(img, b)))
                    if name == OTHER:
                        name = "unknown"
                    out.append({"name": name, "score": round(score, 3), "box": list(b[:4]), "det": round(b[4], 2)})
                seen = [(o["name"], o["score"], o["box"]) for o in out if o["name"] != "unknown"]
                events = self.tracker.update(time.time(), seen, img.shape[0])
                on_counter = self.tracker.on_counter()
        for ev in events:
            if self.hub is not None:
                self.hub.publish(ev)
        return {"bottles": out, "on_counter": on_counter, "events": events,
                "ms": round((time.time() - t0) * 1000)}

    def enroll(self, name, jpg, augment=6):
        """jpg = a photo, or empty: use the newest frame from the bottle camera."""
        if jpg:
            img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
        else:
            img = self.last_img
        if img is None:
            return {"error": "no photo: send a JPEG, or run the bottle camera loop"}
        box = None
        with self.lock:
            if self.mode == "show":
                c, box = center_crop(img)        # exactly what recognition looks at
                crops = [c]
            else:
                boxes = self.det(img)
                if name == OTHER:
                    crops = [crop(img, b) for b in boxes[:4]] + [img]
                else:
                    if not boxes:
                        return {"error": "no bottle found in this photo: hold it in view of the camera", "name": name}
                    big = pick_enrol_box(boxes)
                    box = list(big[:4])
                    crops = [crop(img, big)]
            rng = np.random.default_rng()
            embs = []
            for c in crops:
                embs.append(self.emb(c))
                for _ in range(augment - 1):            # small shifts / light changes, like live frames
                    h, w = c.shape[:2]
                    s = rng.uniform(0.85, 1.0)
                    dx, dy = rng.uniform(0, 1 - s, 2)
                    v = c[int(dy * h):int(dy * h + s * h), int(dx * w):int(dx * w + s * w)]
                    embs.append(self.emb(cv2.convertScaleAbs(v, alpha=rng.uniform(0.8, 1.2), beta=rng.uniform(-20, 20))))
            self.gallery.add(name, embs, append=True)
            d = os.path.join(GALLERY_DIR, name)
            os.makedirs(d, exist_ok=True)
            cv2.imwrite(os.path.join(d, f"{int(time.time() * 1000)}.jpg"), crops[0])
            n = len(self.gallery.items[name])
        return {"name": name, "photos": n // augment, "embeddings": n, "box": box}

    def reset(self, name):
        with self.lock:
            self.gallery.items.pop(name, None)
            p = os.path.join(GALLERY_DIR, name + ".npy")
            if os.path.exists(p):
                os.remove(p)
        return {"name": name, "removed": True}

    def live(self):
        """GET /bottles/last: what the bottle check saw in its newest frame."""
        return dict(self.last, age_s=round(time.time() - self.last["t"], 2) if self.last["t"] else None)

    def info(self):
        return {"mode": self.mode, "bottles": {n: len(g) for n, g in self.gallery.items.items()}}
