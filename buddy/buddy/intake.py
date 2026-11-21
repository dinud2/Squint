"""Hand to mouth: after a bottle is shown, did that person bring a hand to their mouth?

Runs on the same camera frames as face recognition, but only while a dose is waiting for
"Did you take it?" (coordinator.pending), so it costs nothing the rest of the time.

  mouth  : the middle of the two mouth corners from YuNet (the face detector), scaled by the
           face width. A hand over the mouth often hides the face, so the last mouth position
           is kept for MOUTH_KEEP_S.
  hand   : MediaPipe palm detector (OpenCV model zoo, cv2.dnn; ~200 ms per frame on the Pi).
  at mouth: a palm box within NEAR face widths of the mouth point (0 if the box covers it).

Result, once per waiting dose (event "intake" -> coordinator.on_intake):
  2+ "at mouth" frames, at least one confident palm (>= PALM_SURE) -> 0.95: auto-confirm
  1 frame, or only unsure palms                                    -> 0.75: Tab5 asks
"""
import os
import time

import numpy as np

from .palmdet import MPPalmDet

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.path.join(HERE, "models", "palm_detection_mediapipe_2023feb.onnx")

NEAR = 0.25          # face widths between the palm box and the mouth point
PALM_SURE = 0.70
SURE_FRAMES = 2      # at-mouth frames -> 0.95 (auto-confirm), if at least one palm is >= PALM_SURE
# (the Pi checks ~2 frames/s while a dose waits, so a ~1 s hand-to-mouth gives about 2 frames;
#  the first live test gave 2 frames / 1 confident palm and was held at 0.75 by a 3-frame rule)
MOUTH_KEEP_S = 1.2   # the hand hides the face: keep the last mouth position this long
SETTLE_S = 1.2       # report this long after the last 'at mouth' frame (the hand may stay there)


def mouth_of(face):
    """YuNet row: x, y, w, h, then 5 landmarks (r-eye, l-eye, nose, r-mouth, l-mouth), score."""
    m = (np.array(face[10:12]) + np.array(face[12:14])) / 2
    return m, float(face[2])


def box_distance(box, p):
    """Distance from point p to the box (0 inside)."""
    x1, y1, x2, y2 = box
    dx = max(x1 - p[0], 0.0, p[0] - x2)
    dy = max(y1 - p[1], 0.0, p[1] - y2)
    return float(np.hypot(dx, dy))


class HandToMouth:
    def __init__(self, model=MODEL):
        self.det = MPPalmDet(model, scoreThreshold=0.5)
        self.reset(None)

    def reset(self, key):
        self.key = key              # which waiting dose this is about (med, person)
        self.hits = []              # palm scores of 'at mouth' frames
        self.last_hit_t = None
        self.mouth = None           # (point, face_width, t)
        self.reported = False

    def update(self, t, frame, seen, pending):
        """seen: identify_all() rows (face, name, score, scores). pending: coordinator.pending.
        -> {"type": "intake", "person", "confidence", ...} once, or None."""
        if not pending:
            if self.key is not None:
                self.reset(None)
            return None
        key = (pending["med"], pending["for"], pending.get("t"))
        if key != self.key:
            self.reset(key)
        if self.reported:
            return None
        # Report first: the hand may still hide the face (mouth position too old) by then.
        if self.hits and t - self.last_hit_t >= SETTLE_S:
            sure = sum(s >= PALM_SURE for s in self.hits)
            conf = 0.95 if len(self.hits) >= SURE_FRAMES and sure >= 1 else 0.75
            self.reported = True
            return {"type": "intake", "person": pending["for"], "confidence": conf,
                    "frames": len(self.hits), "sure_frames": sure}
        for face, name, _, _ in seen:            # the person the dose is for
            if name == pending["for"]:
                m, fw = mouth_of(face)
                self.mouth = (m, fw, t)
        if self.mouth is None or t - self.mouth[2] > MOUTH_KEEP_S:
            return None
        m, fw, _ = self.mouth
        palms = self.det.infer(frame)
        best = None
        for p in palms:
            if box_distance(p[0:4], m) <= NEAR * fw:
                best = max(best or 0.0, float(p[-1]))
        if best is not None:
            self.hits.append(best)
            self.last_hit_t = t
        return None
