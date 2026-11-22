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
from . import colors
from .bottles import GALLERY_DIR, Classifier, Embedder, Gallery, crop

# Every frame a bottle is named in ("bottle_shown"), so a misread can be looked at later.
SHOWN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "shown")
SHOWN_KEEP = 120   # photo + clean copy (raw/) each


def save_shown(img, box, ev, scores):
    try:
        os.makedirs(SHOWN_DIR, exist_ok=True)
        top = " ".join(f"{k} {v:.2f}" for k, v in sorted(scores.items(), key=lambda kv: -kv[1])[:3])
        view = img.copy()
        cv2.rectangle(view, (box[0], box[1]), (box[2], box[3]), (0, 200, 0), 2)
        cv2.putText(view, top, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        name = time.strftime("%H%M%S") + f"_{ev['bottle']}_{ev['score']:.2f}.jpg"
        cv2.imwrite(os.path.join(SHOWN_DIR, name), view)
        os.makedirs(os.path.join(SHOWN_DIR, "raw"), exist_ok=True)      # unmarked, for testing
        cv2.imwrite(os.path.join(SHOWN_DIR, "raw", name), img)
        for f in sorted(os.listdir(os.path.join(SHOWN_DIR, "raw")))[:-SHOWN_KEEP // 2]:
            os.remove(os.path.join(SHOWN_DIR, "raw", f))
        old = sorted(f for f in os.listdir(SHOWN_DIR) if f.endswith(".jpg"))[:-SHOWN_KEEP // 2]
        for f in old:
            os.remove(os.path.join(SHOWN_DIR, f))
    except Exception as e:                      # never let a debug photo stop recognition
        print("[bottles] could not save shown frame:", e, flush=True)

OTHER = "_other"          # the "not a medicine" class: never reported as a bottle
CLASSIFIER_MIN = 0.65     # trained classifier: held-out photos at 0.6-0.9 -> 0 wrong bottles, 0 no-medicine named
# The box the bottle is held in, close to the camera (~20-30 cm) so it FILLS the box. The first
# version used a big box (64% x 84%) with the bottle held small inside it: the photos were mostly
# the person and the room, and every empty view looked like the bottles with the least label.
CENTER = (0.33, 0.10, 0.67, 0.90)   # (x0, y0, x1, y1) as fractions of the frame


def center_crop(img, box=CENTER):
    h, w = img.shape[:2]
    x0, y0, x1, y1 = box
    return img[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)], [int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)]


class ShowTracker:
    """bottle_shown once the same bottle is recognised in NEED (3) of the last WINDOW (4) checks, with
    no other bottle among them; the same bottle can only be shown again after it has been out of
    view for CLEAR_S."""
    NEED = 3      # ~0.75 s at 4 checks/s; stray one-frame guesses (e.g. "motrin" on an empty view) never get through
    WINDOW = 4    # ...out of the last 4 checks: one missed frame (a hand over the label) no longer
                  # restarts the count. Any OTHER bottle in the window blocks it.
    CLEAR_S = 1.5

    def __init__(self):
        self.hist = []
        self.shown = None
        self.last_seen = {}

    def update(self, t, name, score):
        self.hist = (self.hist + [name])[-self.WINDOW:]
        if name != "unknown":
            self.last_seen[name] = t
        if self.shown and t - self.last_seen.get(self.shown, -1e9) > self.CLEAR_S:
            self.shown = None
        others = {h for h in self.hist if h not in ("unknown", name)}
        if name != "unknown" and name != self.shown and self.hist.count(name) >= self.NEED and not others:
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
        self.emb, self.gallery = Embedder(), Gallery(center=(mode == "show"))
        # A classifier trained on the laptop replaces gallery matching in show mode when present.
        self.clf = Classifier() if (mode in ("show", "color") and Classifier.available()) else None
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
            if self.mode == "color":
                # Anywhere in the picture, by label colour (colors.py): blue = Advil, orange =
                # Motrin, red = Tylenol or Vitamin D; the classifier checks a tight crop around
                # the patch (veto "not a bottle", red: which one, "not sure" if it disagrees).
                name, info = colors.identify(img, self.clf)
                box = info.get("box") or [0, 0, 0, 0]
                score = float(info.get("p", {}).get(name, 0.9)) if name else 0.0
                sc = {name: score} if name else {("not sure" if info.get("unsure") else "nothing"): 1.0}
                name = name or "unknown"
                out = [{"name": name, "score": round(score, 3), "box": box}]
                events = self.show.update(time.time(), name, score)
                for ev in events:
                    save_shown(img, box, ev, sc)
                on_counter = []
                self.last = {"name": name, "score": round(score, 3), "t": time.time(), "shown": self.show.shown,
                             "scores": {k: round(v, 3) for k, v in sc.items()}, "box": box,
                             "candidates": info.get("candidates"), "red": info.get("red"),
                             "unsure": info.get("unsure"), "unsure_box": info.get("unsure_box"),
                             "checks": info.get("checks")}
            elif self.mode == "show":
                c, box = center_crop(img)
                if self.clf is not None:
                    sc = self.clf(c)
                    name, score = max(sc.items(), key=lambda kv: kv[1]) if sc else ("unknown", 0.0)
                    if score < CLASSIFIER_MIN:
                        name = "unknown"
                else:
                    name, score, sc = self.gallery.identify(self.emb(c))
                if name == OTHER:
                    name = "unknown"
                out = [{"name": name, "score": round(score, 3), "box": box}]
                events = self.show.update(time.time(), name, score)
                for ev in events:
                    save_shown(img, box, ev, sc)
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

    def enroll(self, name, jpg, augment=6, full=False):
        """jpg = a photo, or empty: use the newest frame from the bottle camera.
        full=True: jpg is a close-up (e.g. a phone photo with the bottle filling it): use the whole
        picture, and make 12 webcam-like versions of it (smaller, blurred, compressed, other light)."""
        if full:
            img = cv2.imdecode(np.frombuffer(jpg or b"", np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                return {"error": "crop=full needs a JPEG body"}
            return self._enroll_closeup(name, img)
        if jpg:
            img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
        else:
            img = self.last_img
        if img is None:
            return {"error": "no photo: send a JPEG, or run the bottle camera loop"}
        box = None
        with self.lock:
            if self.mode in ("show", "color"):
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

    def _enroll_closeup(self, name, img, n=12):
        """A sharp close-up -> n versions that look like the C270's box: about the box's size,
        a little off-centre / rotated, blurred, darker or brighter, JPEG-compressed."""
        rng = np.random.default_rng()
        h, w = img.shape[:2]
        bw, bh = int((CENTER[2] - CENTER[0]) * 960), int((CENTER[3] - CENTER[1]) * 544)  # the box in a C270 frame
        embs = []
        for i in range(n):
            s = 1.0 if i == 0 else rng.uniform(0.8, 1.0)
            cw, ch = int(w * s), int(h * s)
            x0 = int(rng.uniform(0, w - cw)) if i else (w - cw) // 2
            y0 = int(rng.uniform(0, h - ch)) if i else (h - ch) // 2
            v = img[y0:y0 + ch, x0:x0 + cw]
            if i:
                M = cv2.getRotationMatrix2D((cw / 2, ch / 2), rng.uniform(-12, 12), 1.0)
                v = cv2.warpAffine(v, M, (cw, ch), borderMode=cv2.BORDER_REFLECT)
            # down to the box's pixel size (keeping the aspect of the box), like the webcam sees it
            v = cv2.resize(v, (bw, bh), interpolation=cv2.INTER_AREA)
            if i:
                k = int(rng.choice([1, 3, 3, 5]))
                if k > 1:
                    v = cv2.GaussianBlur(v, (k, k), 0)
                v = cv2.convertScaleAbs(v, alpha=rng.uniform(0.7, 1.2), beta=rng.uniform(-30, 25))
                q = int(rng.uniform(35, 80))
                v = cv2.imdecode(cv2.imencode(".jpg", v, [cv2.IMWRITE_JPEG_QUALITY, q])[1], cv2.IMREAD_COLOR)
            embs.append(self.emb(v))
        with self.lock:
            self.gallery.add(name, embs, append=True)
            d = os.path.join(GALLERY_DIR, name)
            os.makedirs(d, exist_ok=True)
            cv2.imwrite(os.path.join(d, f"closeup_{int(time.time() * 1000)}.jpg"),
                        cv2.resize(img, (bw, bh), interpolation=cv2.INTER_AREA))
            total = len(self.gallery.items[name])
        return {"name": name, "closeup_versions": n, "embeddings": total}

    def reset(self, name):
        with self.lock:
            self.gallery.items.pop(name, None)
            self.gallery._recenter()
            p = os.path.join(GALLERY_DIR, name + ".npy")
            if os.path.exists(p):
                os.remove(p)
        return {"name": name, "removed": True}

    def live(self):
        """GET /bottles/last: what the bottle check saw in its newest frame."""
        return dict(self.last, age_s=round(time.time() - self.last["t"], 2) if self.last["t"] else None)

    def info(self):
        return {"mode": self.mode, "classifier": self.clf.classes if self.clf else None,
                "bottles": {n: len(g) for n, g in self.gallery.items.items()}}
