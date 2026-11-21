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
        return v / (np.linalg.norm(v) + 1e-8)


def crop(frame, box, pad=0.10):
    """Detector box -> crop with a little context (the label edges matter)."""
    x1, y1, x2, y2 = box[:4]
    h, w = frame.shape[:2]
    px, py = (x2 - x1) * pad, (y2 - y1) * pad
    x1, y1 = int(max(0, x1 - px)), int(max(0, y1 - py))
    x2, y2 = int(min(w, x2 + px)), int(min(h, y2 + py))
    return frame[y1:y2, x1:x2]


class Gallery:
    def __init__(self, directory=GALLERY_DIR):
        self.dir = directory
        self.items = {}
        self.reload()

    def reload(self):
        self.items = {}
        if os.path.isdir(self.dir):
            for fn in sorted(os.listdir(self.dir)):
                if fn.endswith(".npy"):
                    self.items[fn[:-4]] = np.load(os.path.join(self.dir, fn))

    def add(self, name, embeddings, save=True, append=False):
        e = np.asarray(embeddings, np.float32)
        if append and name in self.items:
            e = np.concatenate([self.items[name], e])
        self.items[name] = e
        if save:
            os.makedirs(self.dir, exist_ok=True)
            np.save(os.path.join(self.dir, name + ".npy"), e)

    def scores(self, emb):
        return {n: float(np.sort(g @ emb)[::-1][:TOP_K].mean()) for n, g in self.items.items()}

    def identify(self, emb):
        """-> (name or "unknown", best score, all scores)."""
        sc = self.scores(emb)
        if not sc:
            return "unknown", 0.0, sc
        ranked = sorted(sc.items(), key=lambda kv: -kv[1])
        best, bs = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else -1.0
        if bs < ACCEPT or bs - second < MARGIN:
            return "unknown", bs, sc
        return best, bs, sc
