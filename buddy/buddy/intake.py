"""Hand to mouth: after a bottle is shown, did that person bring a hand to their mouth?

Runs on the same camera frames as face recognition, but only while a dose is waiting for
"Did you take it?" (coordinator.pending), so it costs nothing the rest of the time.

  mouth  : the middle of the two mouth corners from YuNet (the face detector), scaled by the
           face width. A hand over the mouth often hides the face, so the last mouth position
           is kept for MOUTH_KEEP_S.
  hand   : MediaPipe palm detector (OpenCV model zoo, cv2.dnn; ~200 ms per frame on the Pi), run
           on a crop around the mouth so the hand is big enough for its 192 px input.
  at mouth: a palm box within NEAR face widths of the mouth point (0 if the box covers it).

Result, once per waiting dose (event "intake" -> coordinator.on_intake):
  2+ "at mouth" frames, at least one confident palm (>= PALM_SURE),
  or 3+ "at mouth" frames, or one very confident palm (>= PALM_CERTAIN) -> 0.95: auto-confirm
  1 frame, or only unsure palms                                    -> 0.75: Tab5 asks
"""
import os
import time

import numpy as np

from .palmdet import MPPalmDet

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.path.join(HERE, "models", "palm_detection_mediapipe_2023feb.onnx")

NEAR = 0.45          # face widths between the palm box and the mouth point (0.25 missed hands held below the chin)
PALM_SURE = 0.70
PALM_CERTAIN = 0.85  # one at-mouth frame with a palm this confident is enough on its own
SURE_FRAMES = 2      # at-mouth frames -> 0.95 (auto-confirm), if at least one palm is >= PALM_SURE
MANY_FRAMES = 3      # ...or this many at-mouth frames, whatever the palm scores: a hand bringing a pill
                     # up shows its side / back, and live it gave 3 frames all under 0.70 (2026-11-21)
CROP_FW = 4.0        # the palm detector looks at a square this many face widths wide around the
                     # mouth: on the whole 960x544 frame (shrunk to 192 px) a hand was ~15 px
FOLLOW_FW = 1.5      # an unnamed face this close to the last mouth position is the same person
# (the Pi checks ~2 frames/s while a dose waits, so a ~1 s hand-to-mouth gives about 2 frames;
#  the first live test gave 2 frames / 1 confident palm and was held at 0.75 by a 3-frame rule)
MOUTH_KEEP_S = 2.5   # the hand hides the face: keep the last mouth position this long
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
            certain = max(self.hits) >= PALM_CERTAIN
            conf = 0.95 if (len(self.hits) >= SURE_FRAMES and sure >= 1) or certain or len(self.hits) >= MANY_FRAMES else 0.75
            self.reported = True
            return {"type": "intake", "person": pending["for"], "confidence": conf,
                    "frames": len(self.hits), "sure_frames": sure, "palms": [round(x, 2) for x in self.hits]}
        # The person the dose is for. A hand near the face often makes it "unknown" for a few
        # frames, so once found, follow whichever face is where they were.
        face = next((f for f, name, _, _ in seen if name == pending["for"]), None)
        if face is None and seen:
            if self.mouth is not None:
                m0, fw0, _ = self.mouth
                near = [f for f, _, _, _ in seen if np.hypot(*(mouth_of(f)[0] - m0)) <= FOLLOW_FW * fw0]
                face = near[0] if near else None
            elif len(seen) == 1:                  # the only face at the counter
                face = seen[0][0]
        if face is not None:
            m, fw = mouth_of(face)
            self.mouth = (m, fw, t)
        if self.mouth is None or t - self.mouth[2] > MOUTH_KEEP_S:
            return None
        m, fw, _ = self.mouth
        h, w = frame.shape[:2]                   # crop around the mouth, a little below (hands come up)
        half = CROP_FW * fw / 2
        x0, y0 = int(max(0, m[0] - half)), int(max(0, m[1] + 0.3 * fw - half))
        x1, y1 = int(min(w, m[0] + half)), int(min(h, m[1] + 0.3 * fw + half))
        if x1 - x0 < 32 or y1 - y0 < 32:
            return None
        palms = self.det.infer(frame[y0:y1, x0:x1])
        best = None
        for p in palms:
            box = [p[0] + x0, p[1] + y0, p[2] + x0, p[3] + y0]
            if box_distance(box, m) <= NEAR * fw:
                best = max(best or 0.0, float(p[-1]))
        if best is not None:
            self.hits.append(best)
            self.last_hit_t = t
        return None
