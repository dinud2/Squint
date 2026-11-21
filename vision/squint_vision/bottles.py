"""C4: few-shot, open-set bottle recognition.

Enrolment stores ~15 L2-normalised MobileNetV3 embeddings per bottle.
Recognition scores each enrolled bottle by the mean of its top-3 cosine
similarities to the query (k-NN), then:

  * best is the special "_empty" class (empty hand / background)  -> "none"
  * best score < ACCEPT, or best - second-best < MARGIN            -> "unknown"
  * otherwise                                                      -> that bottle

Saying "unknown" instead of guessing is the safety property: D turns
"unknown" into amber, never green. Thresholds come from tools/sim_bottles.py.
"""
import json
import os

import cv2
import numpy as np

from .backend import OnnxModel

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_MODEL = os.path.join(HERE, "models", "mobilenetv3_small_embed.onnx")
TRAINED_MODEL = os.path.join(HERE, "models", "bottle_embed.onnx")   # tools/train_bottle_embed.py
MODEL = os.environ.get("SQUINT_EMBED") or (TRAINED_MODEL if os.path.exists(TRAINED_MODEL) else BASE_MODEL)
GALLERY_DIR = os.path.join(HERE, "data", "gallery")
THRESH_FILE = os.path.join(HERE, "models", "bottle_thresholds.json")
EMPTY = "_empty"
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)


class Embedder:
    def __init__(self, path=MODEL):
        self.model = OnnxModel(path)

    def __call__(self, crop_bgr):
        img = cv2.resize(crop_bgr, (224, 224))[:, :, ::-1].astype(np.float32) / 255.0
        x = ((img - MEAN) / STD).transpose(2, 0, 1)[None]
        v = self.model(np.ascontiguousarray(x))[0].astype(np.float32)
        return v / (np.linalg.norm(v) + 1e-8)


def load_thresholds():
    t = {"accept": 0.70, "margin": 0.03, "k": 3}
    if os.path.exists(THRESH_FILE):
        with open(THRESH_FILE) as f:
            t.update(json.load(f))
    return t


class Gallery:
    def __init__(self, directory=GALLERY_DIR, thresholds=None):
        self.dir = directory
        self.t = thresholds or load_thresholds()
        self.items = {}
        self.reload()

    def reload(self):
        self.items = {}
        if os.path.isdir(self.dir):
            for fn in os.listdir(self.dir):
                if fn.endswith(".npy"):
                    self.items[fn[:-4]] = np.load(os.path.join(self.dir, fn))

    def add(self, med, embeddings, save=True):
        self.items[med] = np.asarray(embeddings, np.float32)
        if save:
            os.makedirs(self.dir, exist_ok=True)
            np.save(os.path.join(self.dir, med + ".npy"), self.items[med])

    def scores(self, emb):
        k = self.t["k"]
        out = {}
        for med, g in self.items.items():
            s = np.sort(g @ emb)[::-1]
            out[med] = float(s[:k].mean())
        return out

    def candidates(self, scores, window=0.10):
        """Enrolled bottles that are plausible for this view (for the NFC cross-check)."""
        real = {m: s for m, s in scores.items() if m != EMPTY}
        if not real:
            return []
        best = max(real.values())
        floor = self.t["accept"] - window
        return sorted(m for m, s in real.items() if s >= floor and s >= best - window)

    def classify(self, emb):
        """-> (label, confidence, scores). label is a med id, 'unknown' or 'none'."""
        sc = self.scores(emb)
        if not sc:
            return "unknown", 0.0, sc
        ranked = sorted(sc.items(), key=lambda kv: -kv[1])
        best, bs = ranked[0]
        if best == EMPTY:
            return "none", bs, sc
        second = next((s for m, s in ranked[1:] if m != EMPTY), -1.0)
        if bs < self.t["accept"] or bs - second < self.t["margin"]:
            return "unknown", bs, sc
        return best, bs, sc


class BottleTracker:
    """Smooths per-frame labels; reports a change only when it is stable.

    A label must win `need` of the last `window` frames. 'unknown' needs
    the same agreement, so one blurry frame never flips the verdict.
    """

    def __init__(self, window=5, need=4):
        self.window, self.need = window, need
        self.hist = []
        self.current = "none"
        self.conf = 0.0

    def update(self, label, conf):
        self.hist = (self.hist + [(label, conf)])[-self.window:]
        labels = [l for l, _ in self.hist]
        for cand in set(labels):
            if labels.count(cand) >= self.need and cand != self.current:
                self.current = cand
                self.conf = float(np.mean([c for l, c in self.hist if l == cand]))
                return self.current, self.conf  # changed
        return None
