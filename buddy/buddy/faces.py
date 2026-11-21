"""Who is at the counter? Face detection (YuNet) + face embedding (SFace), both from the
OpenCV model zoo and run with cv2.dnn, so the same code works on a laptop and on QNX.

Enrolment stores the 128-d SFace embeddings of ~30-40 aligned face crops per person in
data/faces/<name>.npy. Recognition compares a face against every person and answers
with that person only if the match is clearly good enough, otherwise "unknown".

Only the main face counts: the largest face that is big enough. In a kitchen or a demo
hall, people walking past in the background must not be greeted.
"""
import os

import cv2
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DET_MODEL = os.path.join(HERE, "models", "face_detection_yunet_2023mar.onnx")
REC_MODEL = os.path.join(HERE, "models", "face_recognition_sface_2021dec.onnx")
GALLERY_DIR = os.path.join(HERE, "data", "faces")

MIN_FACE_PX = 60        # smaller faces are too far away (or background people)
DET_SCORE = 0.8
# SFace cosine similarity: the model authors' same-person threshold is 0.363.
ACCEPT = 0.40           # best person must score at least this...
MARGIN = 0.08           # ...and beat the other person by this much
TOP_K = 5               # score = mean of the 5 best matches against that person's photos


class FaceID:
    def __init__(self, gallery_dir=GALLERY_DIR):
        self.det = cv2.FaceDetectorYN.create(DET_MODEL, "", (320, 320), DET_SCORE, 0.3, 5000)
        self.rec = cv2.FaceRecognizerSF.create(REC_MODEL, "")
        self.gallery_dir = gallery_dir
        self.people = {}
        self.reload()

    # ------------------------------------------------------------ detection / embedding
    def main_face(self, frame):
        """-> the YuNet row (x, y, w, h, 5 landmarks, score) of the largest big-enough face, or None."""
        h, w = frame.shape[:2]
        self.det.setInputSize((w, h))
        _, faces = self.det.detect(frame)
        if faces is None:
            return None
        faces = [f for f in faces if min(f[2], f[3]) >= MIN_FACE_PX]
        return max(faces, key=lambda f: f[2] * f[3]) if faces else None

    def align(self, frame, face):
        return self.rec.alignCrop(frame, face)          # 112x112, eyes level

    def embed(self, aligned):
        v = self.rec.feature(aligned).reshape(-1).astype(np.float32)
        return v / (np.linalg.norm(v) + 1e-8)

    # ------------------------------------------------------------ gallery
    def reload(self):
        self.people = {}
        if os.path.isdir(self.gallery_dir):
            for fn in sorted(os.listdir(self.gallery_dir)):
                if fn.endswith(".npy"):
                    self.people[fn[:-4]] = np.load(os.path.join(self.gallery_dir, fn))

    def save_person(self, name, embeddings):
        os.makedirs(self.gallery_dir, exist_ok=True)
        self.people[name] = np.asarray(embeddings, np.float32)
        np.save(os.path.join(self.gallery_dir, name + ".npy"), self.people[name])

    def scores(self, emb):
        return {name: float(np.sort(g @ emb)[::-1][:TOP_K].mean()) for name, g in self.people.items()}

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


def sharpness(img):
    """Variance of the Laplacian: low = blurry (motion or focus)."""
    return float(cv2.Laplacian(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
