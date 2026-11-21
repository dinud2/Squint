"""Bottle recognition for frames sent by the Tab5 camera (or any camera, for testing).

Used by the API:
    POST /tab5/frame                  body = JPEG
        -> {"bottles": [{"name", "score", "box"}], "on_counter": [...], "events": [...], "ms": n}
    POST /bottles/enroll?name=tylenol body = JPEG with that bottle in view (send ~10-20)
    POST /bottles/enroll?name=_other  cups, water bottles, hands, empty counter: teaches
                                      "not a medicine" so those come out as unknown
    POST /bottles/reset?name=tylenol  forget a bottle
    GET  /bottles                     enrolled bottles and photo counts
"""
import os
import threading
import time

import cv2
import numpy as np

from .bottle_tracker import BottleTracker
from .bottles import GALLERY_DIR, Embedder, Gallery, crop
from .detector import NanoDet

OTHER = "_other"          # the "not a medicine" class: never reported as a bottle


def _area(b):
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def pick_enrol_box(boxes):
    """The bottle being enrolled is the one shown up close, so: ignore small boxes (a water
    bottle in the background was once the most confident detection), and among the big
    ones skip boxes that contain another big one (hand + bottle around the bottle itself)."""
    top = max(_area(b) for b in boxes)
    big = [b for b in boxes if _area(b) >= 0.2 * top]

    def contains(o, i):
        ix = max(0, min(o[2], i[2]) - max(o[0], i[0])) * max(0, min(o[3], i[3]) - max(o[1], i[1]))
        return o is not i and ix >= 0.8 * _area(i)
    inner = [b for b in big if not any(contains(b, i) for i in big)] or big
    return max(inner, key=lambda b: b[4])


class BottleService:
    def __init__(self, hub=None):
        self.det, self.emb, self.gallery = NanoDet(), Embedder(), Gallery()
        self.tracker = BottleTracker()
        self.hub = hub
        self.lock = threading.Lock()          # cv2.dnn nets are not thread-safe
        self.last_img = None

    def frame(self, jpg):
        img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return {"error": "could not decode JPEG"}
        return self.frame_image(img)

    def frame_image(self, img):
        """One BGR frame (from the counter camera, or a JPEG the Tab5 posted)."""
        self.last_img = img
        t0 = time.time()
        with self.lock:
            boxes = self.det(img)
            out = []
            for b in boxes[:6]:
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
        """jpg = a photo with the bottle in it, or empty: use the latest counter-camera frame."""
        if jpg:
            img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
        else:
            img = self.last_img
        if img is None:
            return {"error": "no photo: send a JPEG, or run the bottle camera loop"}
        with self.lock:
            boxes = self.det(img)
            if name == OTHER:
                # everything detected, plus the whole frame: what the counter looks like without medicine
                crops = [crop(img, b) for b in boxes[:4]] + [img]
            else:
                if not boxes:
                    return {"error": "no bottle found in this photo: hold it in view of the camera", "name": name}
                big = pick_enrol_box(boxes)
                boxes = [big] + [b for b in boxes if b is not big]
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
        return {"name": name, "photos": n // augment, "embeddings": n,
                "box": list(boxes[0][:4]) if boxes else None}

    def reset(self, name):
        with self.lock:
            self.gallery.items.pop(name, None)
            p = os.path.join(GALLERY_DIR, name + ".npy")
            if os.path.exists(p):
                os.remove(p)
        return {"name": name, "removed": True}

    def info(self):
        return {"bottles": {n: len(g) for n, g in self.gallery.items.items()}}
