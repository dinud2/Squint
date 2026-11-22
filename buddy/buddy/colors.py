"""Find a pill bottle anywhere in the picture by its label colour.

    Advil = blue label, Motrin = orange, Tylenol = red, on a white bottle.
    Vitamin D (Jamieson) also has a big red "D3", so red is handed to the classifier to decide
    Tylenol vs Vitamin D on a crop around the red patch.

A colour patch only counts if it is
  - strongly coloured (skin, the maroon top, wood are not saturated / bright enough),
  - label-sized (the red text on a lanyard is too small; a red shirt is too big), and
  - mostly surrounded by white (the bottle) - clothes and the background are not.

frame (BGR) -> list of {"name", "box": [x0, y0, x1, y1], "area", "white", "score"} best first.
"""
import cv2
import numpy as np

# hue ranges are OpenCV's 0..180
COLOURS = {
    "advil":   [((100, 135, 70), (126, 255, 255))],                              # blue
    "motrin":  [((7, 150, 120), (21, 255, 255))],                                # orange
    "red":     [((0, 140, 80), (6, 255, 255)), ((168, 140, 80), (180, 255, 255))],  # Tylenol / Vitamin D
}
MIN_AREA = 0.0007      # of the frame (~370 px at 960x544): smaller is text on a lanyard
MAX_AREA = 0.06        # bigger is clothing / a wall
MIN_WHITE = {"advil": 0.18, "motrin": 0.18,   # share of the ring around the patch that is white
             "red": 0.05}   # Vitamin D's label is cream, not white: red is confirmed by the classifier
WHITE_S, WHITE_V = 60, 140


def _masks(hsv):
    out = {}
    for name, ranges in COLOURS.items():
        m = None
        for lo, hi in ranges:
            r = cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
            m = r if m is None else (m | r)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        out[name] = m
    return out


def find(frame, ignore_top=0):
    h, w = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    if ignore_top:
        hsv[:ignore_top] = 0
    white = ((hsv[..., 1] < WHITE_S) & (hsv[..., 2] > WHITE_V)).astype(np.uint8)
    found = []
    for name, m in _masks(hsv).items():
        n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        for i in range(1, n):
            x, y, bw, bh, area = stats[i]
            if not (MIN_AREA * w * h <= area <= MAX_AREA * w * h):
                continue
            pad = max(6, int(0.5 * np.sqrt(area)))
            x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(w, x + bw + pad), min(h, y + bh + pad)
            blob = (lab[y0:y1, x0:x1] == i)
            ring = ~blob
            wf = float(white[y0:y1, x0:x1][ring].mean()) if ring.any() else 0.0
            if wf < MIN_WHITE[name]:
                continue
            found.append({"name": name, "box": [int(x), int(y), int(x + bw), int(y + bh)],
                          "area": int(area), "white": round(wf, 2),
                          "score": float(area) * (0.5 + wf)})
    found.sort(key=lambda f: -f["score"])
    return found


def bottle_crop(frame, box, grow=2.2):
    """A square-ish crop around the label patch, big enough to show the bottle (for the classifier)."""
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    s = max(x1 - x0, y1 - y0) * grow / 2
    a, b = int(max(0, cx - s)), int(max(0, cy - 1.3 * s))
    c, d = int(min(w, cx + s)), int(min(h, cy + 1.3 * s))
    return frame[b:d, a:c]


RED_MIN = 0.25         # classifier share for Tylenol + Vitamin D on the crop, to accept a red patch


def identify(frame, clf=None, ignore_top=0):
    """-> (name, info) with name in advil / motrin / tylenol / vitamind, or (None, info).
    Blue and orange are decided by colour alone. Red needs the classifier (clf: bottles.Classifier)
    to say Tylenol or Vitamin D on a crop around it; without one, red is reported as Tylenol."""
    found = find(frame, ignore_top)
    info = {"candidates": [(f["name"], f["area"], f["white"]) for f in found[:3]]}
    for f in found[:3]:                          # best first; a red patch the classifier rejects
        info["box"] = f["box"]                   # lets the next candidate have a go
        if f["name"] != "red":
            return f["name"], info
        if clf is None:
            return "tylenol", info
        p = clf(bottle_crop(frame, f["box"]))
        t, v = p.get("tylenol", 0.0), p.get("vitamind", 0.0)
        info["red"] = {"tylenol": round(t, 2), "vitamind": round(v, 2), "_other": round(p.get("_other", 0.0), 2)}
        if t + v >= RED_MIN:
            return ("tylenol" if t >= v else "vitamind"), info
    info.pop("box", None)
    return None, info
