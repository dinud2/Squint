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
# 0.40 let a similar-looking visitor through as Dinu (2026-11-21). Measured live on the Pi: the
# visitor scored up to 0.50 against Dinu two frames in a row, 0.55 only in single frames; Dinu
# himself 0.70 median, Kathy 0.54 against her own photos. Unknown is the safe answer.
ACCEPT = float(os.environ.get("SQUINT_FACE_ACCEPT", "0.50"))   # best person must score at least this...
PERSON_ACCEPT = {"dinu": 0.55}   # stricter for someone a visitor resembles (SQUINT_FACE_ACCEPT_<ID> overrides)
MARGIN = 0.08           # ...and beat the other person by this much
TOP_K = 5               # score = mean of the 5 best matches against that person's photos


class FaceID:
    def __init__(self, gallery_dir=GALLERY_DIR, det_scale=1.0):
        """det_scale < 1 finds faces on a shrunken frame (0.5 -> ~4x less work on the Pi);
        boxes and landmarks are scaled back, so alignment still uses the full-res frame."""
        self.det_scale = det_scale
        self.last_raw = 0
        self.det = cv2.FaceDetectorYN.create(DET_MODEL, "", (320, 320), DET_SCORE, 0.3, 5000)
        self.rec = cv2.FaceRecognizerSF.create(REC_MODEL, "")
        self.gallery_dir = gallery_dir
        self.people = {}
        self.reload()

    # ------------------------------------------------------------ detection / embedding
    def _detect(self, frame):
        s = self.det_scale
        img = frame if s == 1.0 else cv2.resize(frame, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        h, w = img.shape[:2]
        self.det.setInputSize((w, h))
        _, faces = self.det.detect(img)
        self.last_raw = 0 if faces is None else len(faces)      # before the size filter (diagnostics)
        if faces is None:
            return []
        faces = faces.copy()
        faces[:, :14] /= s                               # boxes + landmarks back to full-res pixels
        return [f for f in faces if min(f[2], f[3]) >= MIN_FACE_PX]

    def main_face(self, frame):
        """-> the YuNet row (x, y, w, h, 5 landmarks, score) of the largest big-enough face, or None."""
        faces = self._detect(frame)
        return max(faces, key=lambda f: f[2] * f[3]) if faces else None

    def all_faces(self, frame, max_faces=4):
        """-> YuNet rows of every big-enough face, largest first (closest to the counter)."""
        return sorted(self._detect(frame), key=lambda f: -f[2] * f[3])[:max_faces]

    @staticmethod
    def accept(name):
        return float(os.environ.get(f"SQUINT_FACE_ACCEPT_{name.upper()}", PERSON_ACCEPT.get(name, ACCEPT)))

    def identify_all(self, frame):
        """Name every face at the counter. -> list of (face_row, name, score, scores), largest first.

        A person can only be in one place: names are handed out best match first, and a
        face whose best person is already taken gets its next acceptable person, or
        "unknown" (two faces both closest to Dinu -> the better one is Dinu)."""
        faces = self.all_faces(frame)
        cands = []
        for i, f in enumerate(faces):
            sc = self.scores(self.embed(self.align(frame, f)))
            for name, s in sc.items():
                others = [v for n, v in sc.items() if n != name]
                acc = self.accept(name)
                if s >= acc and s - (max(others) if others else -1.0) >= MARGIN:
                    cands.append((s, i, name))
                elif s >= acc and others and s >= max(others):
                    cands.append((s - 1.0, i, name))       # ambiguous: only if nothing better
            faces[i] = (f, sc)
        out = [[f, "unknown", max(sc.values()) if sc else 0.0, sc] for f, sc in faces]
        used_face, used_name = set(), set()
        for s, i, name in sorted(cands, reverse=True):
            if i in used_face or name in used_name or s < self.accept(name):
                continue
            out[i][1], out[i][2] = name, s
            used_face.add(i); used_name.add(name)
        return [tuple(o) for o in out]

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
        if bs < self.accept(best) or bs - second < MARGIN:
            return "unknown", bs, sc
        return best, bs, sc


def sharpness(img):
    """Variance of the Laplacian: low = blurry (motion or focus)."""
    return float(cv2.Laplacian(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
