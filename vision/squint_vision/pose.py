"""MoveNet Lightning pose + the body geometry Part C needs (mouth, hand crop)."""
import os

import cv2
import numpy as np

from .backend import OnnxModel

# COCO-17 keypoint order used by MoveNet
NOSE, LEYE, REYE, LEAR, REAR, LSHO, RSHO, LELB, RELB, LWRI, RWRI = range(11)
MODEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "movenet_lightning.onnx")


class Pose:
    """frame (BGR, HxWx3) -> keypoints (17,3) as (x_px, y_px, score)."""

    def __init__(self, path=MODEL):
        self.model = OnnxModel(path)

    def __call__(self, frame):
        h, w = frame.shape[:2]
        s = max(h, w)
        pad = np.zeros((s, s, 3), np.uint8)
        pad[:h, :w] = frame
        img = cv2.resize(pad, (192, 192))[:, :, ::-1]  # BGR->RGB
        out = self.model(img[None].astype(np.int32))[0, 0]  # (17,3) y,x,score in [0,1]
        kps = np.empty((17, 3), np.float32)
        kps[:, 0] = out[:, 1] * s
        kps[:, 1] = out[:, 0] * s
        kps[:, 2] = out[:, 2]
        return kps


def mouth(kps):
    """Estimate the mouth: below the nose by ~0.9x the eyes-to-nose offset."""
    eyes = (kps[LEYE, :2] + kps[REYE, :2]) / 2
    return kps[NOSE, :2] + 0.9 * (kps[NOSE, :2] - eyes)


def shoulder_width(kps):
    return max(float(np.linalg.norm(kps[LSHO, :2] - kps[RSHO, :2])), 1.0)


def hand_point(kps, side):
    """MoveNet gives the wrist; the hand (and what it holds) sits a bit past it."""
    e, w = (LELB, LWRI) if side == "l" else (RELB, RWRI)
    return kps[w, :2] + 0.3 * (kps[w, :2] - kps[e, :2])


def hand_crop_box(kps, side, frame_shape, scale=1.3):
    """Square box around the hand, sized by forearm length. Returns x0,y0,x1,y1."""
    e, w = (LELB, LWRI) if side == "l" else (RELB, RWRI)
    fore = float(np.linalg.norm(kps[w, :2] - kps[e, :2]))
    size = max(fore * scale, 0.6 * shoulder_width(kps), 48)
    cx, cy = hand_point(kps, side)
    h, wd = frame_shape[:2]
    x0, y0 = int(max(0, cx - size / 2)), int(max(0, cy - size / 2))
    x1, y1 = int(min(wd, cx + size / 2)), int(min(h, cy + size / 2))
    return x0, y0, x1, y1


def active_hand(kps, min_score=0.2):
    """The hand most likely doing something: the one closer to the mouth."""
    m = mouth(kps)
    best, bd = None, 1e9
    for side, wi in (("l", LWRI), ("r", RWRI)):
        if kps[wi, 2] < min_score:
            continue
        d = np.linalg.norm(hand_point(kps, side) - m)
        if d < bd:
            best, bd = side, d
    return best
