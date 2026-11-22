"""Which pill bottle is this? Few-shot, open-set recognition of detector crops.

Embedder: MobileNetV3 bottle embedder trained for the earlier project (old-idea branch,
vision/tools/train_bottle_embed.py), run with cv2.dnn so it works on QNX. Each enrolled
bottle keeps the L2-normalised embeddings of its photos in data/bottles/<name>.npy.

A crop is named only if its best bottle scores >= ACCEPT and beats the runner-up by
MARGIN; anything else (a cup, a water bottle, a hand, a new bottle) is "unknown".
Saying "unknown" instead of guessing is the safety property: the screen must never
show a green check for the wrong medicine.
"""
import os

import cv2
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.path.join(HERE, "models", "bottle_embed.onnx")
GALLERY_DIR = os.path.join(HERE, "data", "bottles")
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)
ACCEPT = 0.60
MARGIN = 0.07
TOP_K = 3


class Embedder:
    def __init__(self, model=MODEL):
        self.net = cv2.dnn.readNet(model)

    def __call__(self, crop_bgr):
        img = cv2.resize(crop_bgr, (224, 224))[:, :, ::-1].astype(np.float32) / 255.0
        x = ((img - MEAN) / STD).transpose(2, 0, 1)[None]
        self.net.setInput(np.ascontiguousarray(x))
        v = np.asarray(self.net.forward()).reshape(-1).astype(np.float32)
        if not np.all(np.isfinite(v)):        # e.g. a bad / black frame while the camera starts
            return np.zeros_like(v)
        return v / (np.linalg.norm(v) + 1e-8)


class Classifier:
    """The bottle classifier trained on the laptop (tools/train_bottle_classifier.py), run with
    cv2.dnn. Same preprocessing as training: the box crop resized to 224x224, RGB, ImageNet
    normalisation. -> {class: probability}."""
    MODEL = os.path.join(HERE, "models", "bottle_classifier.onnx")
    META = os.path.join(HERE, "models", "bottle_classes.json")

    @classmethod
    def available(cls):
        return os.path.exists(cls.MODEL) and os.path.exists(cls.META)

    def __init__(self, model=None, meta=None):
        import json
        with open(meta or self.META) as f:
            meta = json.load(f)
        self.classes = meta["classes"]
        self.size = int(meta.get("size", 224))
        self.mean = np.array(meta.get("mean", MEAN), np.float32)
        self.std = np.array(meta.get("std", STD), np.float32)
        self.net = cv2.dnn.readNet(model or self.MODEL)

    def __call__(self, crop_bgr):
        img = cv2.resize(crop_bgr, (self.size, self.size), interpolation=cv2.INTER_AREA)[:, :, ::-1]
        x = ((img.astype(np.float32) / 255.0 - self.mean) / self.std).transpose(2, 0, 1)[None]
        self.net.setInput(np.ascontiguousarray(x))
        z = np.asarray(self.net.forward()).reshape(-1).astype(np.float64)
        if not np.all(np.isfinite(z)):
            return {}
        p = np.exp(z - z.max())
        p /= p.sum()
        return {c: float(v) for c, v in zip(self.classes, p)}


def crop(frame, box, pad=0.10):
    """Detector box -> crop with a little context (the label edges matter)."""
    x1, y1, x2, y2 = box[:4]
    h, w = frame.shape[:2]
    px, py = (x2 - x1) * pad, (y2 - y1) * pad
    x1, y1 = int(max(0, x1 - px)), int(max(0, y1 - py))
    x2, y2 = int(min(w, x2 + px)), int(min(h, y2 + py))
    return frame[y1:y2, x1:x2]


class Gallery:
    """center=True ("show" mode): compare what is left after removing the scene every photo
    shares. A bottle held up fills only part of the crop; the rest (the person, the lanyard,
    the ceiling) is the same in every photo, so raw embeddings were ~0.85 alike for every
    bottle and the right one led by only 0.02-0.05. Subtracting the mean embedding of all
    enrolled photos (incl. _other) and renormalising left the bottle: leads of +0.28..+0.51
    on the enrolment photos (leave-one-out, 100% top-1). The scores change scale, hence the
    separate thresholds."""
    CENTER_ACCEPT = 0.50
    CENTER_MARGIN = 0.08   # tuned on ~950 enrolled photos: 79% named, 0 wrong, 0 no-medicine named (0.15: 48%)

    def __init__(self, directory=GALLERY_DIR, center=False):
        self.dir = directory
        self.center = center
        self.items = {}
        self.mu = None
        self.cen = {}
        self.accept = self.CENTER_ACCEPT if center else ACCEPT
        self.margin = self.CENTER_MARGIN if center else MARGIN
        self.reload()

    def _recenter(self):
        if not self.center or not self.items:
            self.mu, self.cen = None, {}
            return
        self.mu = np.concatenate(list(self.items.values())).mean(0)
        self.cen = {n: self._c(g) for n, g in self.items.items()}

    def _c(self, v):
        v = np.atleast_2d(v) - self.mu
        return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-8)

    def reload(self):
        self.items = {}
        if os.path.isdir(self.dir):
            for fn in sorted(os.listdir(self.dir)):
                if fn.endswith(".npy"):
                    g = self._valid(np.load(os.path.join(self.dir, fn)))
                    if len(g):
                        self.items[fn[:-4]] = g
        self._recenter()

    @staticmethod
    def _valid(e):
        """Drop NaN / zero rows: one NaN row made the shared mean NaN and every score NaN
        (some augmented close-ups produced NaN embeddings on the Pi)."""
        e = np.asarray(e, np.float32).reshape(-1, np.asarray(e).shape[-1])
        return e[np.all(np.isfinite(e), axis=1) & np.any(e != 0, axis=1)]

    def add(self, name, embeddings, save=True, append=False):
        e = self._valid(embeddings)
        if append and name in self.items:
            e = np.concatenate([self.items[name], e])
        if not len(e):
            return
        self.items[name] = e
        self._recenter()
        if save:
            os.makedirs(self.dir, exist_ok=True)
            np.save(os.path.join(self.dir, name + ".npy"), e)

    def scores(self, emb):
        if self.center and self.mu is not None:
            q = self._c(emb)[0]
            return {n: float(np.sort(g @ q)[::-1][:TOP_K].mean()) for n, g in self.cen.items()}
        return {n: float(np.sort(g @ emb)[::-1][:TOP_K].mean()) for n, g in self.items.items()}

    def identify(self, emb):
        """-> (name or "unknown", best score, all scores)."""
        if not np.any(emb) or not np.all(np.isfinite(emb)):
            return "unknown", 0.0, {}
        sc = {n: v for n, v in self.scores(emb).items() if np.isfinite(v)}
        if not sc:
            return "unknown", 0.0, sc
        ranked = sorted(sc.items(), key=lambda kv: -kv[1])
        best, bs = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else -1.0
        if bs < self.accept or bs - second < self.margin:
            return "unknown", bs, sc
        return best, bs, sc
