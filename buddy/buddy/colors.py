"""Find a pill bottle anywhere in the picture by its label colour, then let the classifier check it.

    Advil = blue label, Motrin = orange, Tylenol = red, Vitamin D (Jamieson) = red "D3".

Two stages, so colour stays the main cue but nothing else in the room is named:
  1. colour (find): saturated, label-sized patches of blue / orange / red that have some white
     (the bottle) around them. With a classifier the ranges are LOOSE (dim rooms, far bottles, the
     pinkish Vitamin D red, washed-out Motrin orange): high recall, and skin, windows, shirts and
     lanyards get through too.
  2. classifier (identify / judge): on a tight crop around the patch (bottle_crop), trained on
     such crops with the background replaced (tools/train_label_classifier.py). A bottle is named
     only if colour and classifier AGREE (blue -> Advil; orange -> Motrin or Omega 3-6-9, red ->
     Tylenol or Vitamin D: the classifier picks, clearly, or it is "not sure"). Classifier says "not a bottle" -> next patch; it sees a medicine
     of ANOTHER colour, or Tylenol vs Vitamin D is close -> "not sure" (never a guess).

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
# Loose ranges, used with the classifier (measured on the training photos: label recall
# Advil 83 %, Motrin 94 %, Tylenol 83 %, Vitamin D 81 %, against 30-55 % for the strict ones).
LOOSE = {
    "advil":   [((98, 110, 50), (128, 255, 255))],
    "motrin":  [((7, 110, 90), (24, 255, 255))],
    "red":     [((0, 100, 60), (7, 255, 255)), ((165, 100, 60), (180, 255, 255))],
}
LOOSE_WHITE = {"advil": 0.18, "motrin": 0.10, "red": 0.03}
MIN_AREA = 0.0007      # of the frame (~370 px at 960x544): smaller is text on a lanyard
MAX_AREA = 0.06        # bigger is clothing / a wall
MIN_WHITE = {"advil": 0.18, "motrin": 0.18,   # share of the ring around the patch that is white
             "red": 0.05}   # Vitamin D's label is cream, not white: red is confirmed by the classifier
WHITE_S, WHITE_V = 60, 140


def _masks(hsv, colours=None):
    out = {}
    for name, ranges in (colours or COLOURS).items():
        m = None
        for lo, hi in ranges:
            r = cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
            m = r if m is None else (m | r)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        out[name] = m
    return out


def find(frame, ignore_top=0, frame_area=None, loose=False):
    """frame_area: the full camera frame's pixel count when `frame` is only a part of it (the
    label-size limits are fractions of the whole picture). loose: the wide colour ranges (only
    with the classifier behind it)."""
    colours, min_white = (LOOSE, LOOSE_WHITE) if loose else (COLOURS, MIN_WHITE)
    h, w = frame.shape[:2]
    fa = frame_area or w * h
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    if ignore_top:
        hsv[:ignore_top] = 0
    white = ((hsv[..., 1] < WHITE_S) & (hsv[..., 2] > WHITE_V)).astype(np.uint8)
    found = []
    for name, m in _masks(hsv, colours).items():
        n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        for i in range(1, n):
            x, y, bw, bh, area = stats[i]
            if not (MIN_AREA * fa <= area <= MAX_AREA * fa):
                continue
            pad = max(6, int(0.5 * np.sqrt(area)))
            x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(w, x + bw + pad), min(h, y + bh + pad)
            blob = (lab[y0:y1, x0:x1] == i)
            ring = ~blob
            wf = float(white[y0:y1, x0:x1][ring].mean()) if ring.any() else 0.0
            if wf < min_white[name]:
                continue
            sat = float(hsv[y0:y1, x0:x1, 1][blob].mean())
            found.append({"name": name, "box": [int(x), int(y), int(x + bw), int(y + bh)],
                          "area": int(area), "white": round(wf, 2), "sat": round(sat),
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


# orange: Motrin's label, or the amber capsules of Omega 3-6-9 (a bottle not in the app)
FAMILY = {"advil": ("advil",), "motrin": ("motrin", "omega369"), "red": ("tylenol", "vitamind")}
MEDS = ("advil", "motrin", "omega369", "tylenol", "vitamind")
CANDIDATES = 3         # patches checked per frame, biggest / whitest first
# Tuned on whole held-out recording sessions (tools/train_label_classifier.py): 0 wrong bottles in
# 339 photos, 1 of 205 no-medicine photos named; the rest of the misses are "not sure" / nothing.
VETO = 0.50            # classifier "_other" >= this: not a medicine bottle, try the next patch
MIN_P = 0.70           # the classifier must agree with the colour this strongly to name a bottle
RIVAL = 0.35           # its top medicine is of ANOTHER colour at >= this: not sure (stops the frame)
RED_MARGIN = 0.20      # two bottles of one colour (Tylenol / Vitamin D, Motrin / Omega) must differ by this


def judge(colour, p):
    """One patch: colour family + classifier probabilities -> ("name" | "_other" | "unsure", why).
    A bottle is named only when colour and classifier agree; they never overrule each other."""
    if p.get("_other", 0.0) >= VETO:
        return "_other", "classifier: not a bottle"
    top = max(MEDS, key=lambda k: p.get(k, 0.0))
    fam = FAMILY[colour]
    if top not in fam:
        if p.get(top, 0.0) >= RIVAL:
            return "unsure", f"colour {colour} but classifier {top} {p.get(top, 0.0):.2f}"
        return "_other", "classifier: no medicine of this colour"
    if p.get(top, 0.0) < MIN_P:
        return "_other", f"classifier {top} only {p.get(top, 0.0):.2f}"
    if len(fam) > 1:
        a, b = sorted(fam, key=lambda k: -p.get(k, 0.0))
        if p.get(a, 0.0) - p.get(b, 0.0) < RED_MARGIN:
            return "unsure", f"{a} {p.get(a, 0.0):.2f} vs {b} {p.get(b, 0.0):.2f}"
    return top, "colour + classifier"


def identify(frame, clf=None, ignore_top=0, frame_area=None):
    """-> (name, info), name in advil / motrin / omega369 / tylenol / vitamind, or None (nothing, or not sure:
    then info["unsure"] says why). Without a classifier: strict colours, red = Tylenol."""
    found = find(frame, ignore_top, frame_area, loose=clf is not None)
    info = {"candidates": [(f["name"], f["area"], f["white"]) for f in found[:CANDIDATES]], "checks": []}
    unsure = None
    for f in found[:CANDIDATES]:                 # best first; a vetoed patch lets the next one try
        if clf is None:
            info["box"] = f["box"]
            return ("tylenol" if f["name"] == "red" else f["name"]), info
        p = clf(bottle_crop(frame, f["box"]))
        verdict, why = judge(f["name"], p)
        info["checks"].append({"colour": f["name"], "box": f["box"], "verdict": verdict, "why": why,
                               "p": {k: round(v, 2) for k, v in p.items()}})
        if f["name"] == "red":                   # kept for /bottles/last and the laptop view
            info["red"] = {k: round(p.get(k, 0.0), 2) for k in ("tylenol", "vitamind", "_other")}
        if verdict == "unsure":                  # never fall through to a later patch: say so
            unsure = {"box": f["box"], "why": why}
            break
        if verdict != "_other":
            info["box"], info["p"] = f["box"], p
            return verdict, info
    if unsure:
        info["unsure"] = unsure["why"]
        info["unsure_box"] = unsure["box"]
    return None, info
