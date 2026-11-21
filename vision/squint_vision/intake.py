"""C5/C6/C8: "is a pill about to go into her mouth?" from pose keypoints.

Pipeline per camera frame:
  keypoints -> frame features (hand-to-mouth distance in shoulder widths, etc.)
  last 0.7 s of frame features -> window features (distance, approach speed,
  time-to-contact, elbow flexion, jitter ...)
  window features -> p(intake imminent) from a tiny model (logistic regression
  or 1-hidden-layer MLP, pure numpy so it runs anywhere, QNX included)
  -> IntakeDetector state machine -> intake_start / intake_done

The learned model only judges the *motion*. Whether a bottle was in her hand
("armed") is a separate, explicit gate from bottle recognition. That keeps a
nose scratch with an empty hand from ever triggering STOP, and makes the
behaviour easy to explain to judges.
"""
import json
import os

import numpy as np

from . import pose as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_FILE = os.path.join(HERE, "models", "intake_model.json")

WINDOW_S = 1.0          # long window; a 0.4 s short window is cut from its end
SHORT_S = 0.4
CONTACT_D = 0.45     # hand-to-mouth distance (shoulder widths) that counts as "at the mouth"
RELEASE_D = 0.85     # hand has left the mouth again
RESET_D = 1.6        # hand back down: approach is over

FEATURE_NAMES = [
    "d_last", "d_min", "d_drop", "slope_d", "slope_d_recent", "accel_d",
    "dy_last", "slope_dy", "dx_last", "elbow_last", "slope_elbow",
    "ttc", "jitter", "conf_mean", "fore_last", "slope_fore",
    "quad_v", "quad_a", "d_stop",
]
BASE_FEATURES = list(FEATURE_NAMES)
FEATURE_NAMES = [f + "_L" for f in BASE_FEATURES] + [f + "_S" for f in BASE_FEATURES]
# the rule and simple code refer to the long-window names below via this map
F = {n: i for i, n in enumerate(FEATURE_NAMES)}


def _stop_estimate(t, d):
    """Fit d(t) = c0 + v*t + a*t^2 over the last 0.4 s (t measured from now).
    A decelerating reach (v<0, a>0) stops where the parabola bottoms out."""
    m = t >= t[-1] - 0.4
    if m.sum() < 4:
        return 0.0, 0.0, float(d[-1])
    tt = t[m] - t[-1]
    A = np.stack([np.ones_like(tt), tt, tt * tt], 1)
    c0, v, a = np.linalg.lstsq(A, d[m], rcond=None)[0]
    if v < 0 and a > 0.05:
        stop = c0 - v * v / (4 * a)
    elif v < 0:
        stop = c0 + v * 0.5            # not slowing yet: assume ~0.5 s more of travel
    else:
        stop = c0
    return float(v), float(a), float(np.clip(stop, -1.0, 3.0))


def _angle(a, b, c):
    v1, v2 = a - b, c - b
    cos = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6)
    return float(np.arccos(np.clip(cos, -1, 1)))


def frame_features(kps, side=None):
    """-> dict or None if the face/hand is not visible."""
    if kps[P.NOSE, 2] < 0.2:
        return None
    side = side or P.active_hand(kps)
    if side is None:
        return None
    S = P.shoulder_width(kps)
    m = P.mouth(kps)
    h = P.hand_point(kps, side)
    sh, el, wr = (P.LSHO, P.LELB, P.LWRI) if side == "l" else (P.RSHO, P.RELB, P.RWRI)
    return {
        "d": float(np.linalg.norm(h - m) / S),
        "dy": float((h[1] - m[1]) / S),
        "dx": float(abs(h[0] - m[0]) / S),
        "elbow": _angle(kps[sh, :2], kps[el, :2], kps[wr, :2]),
        "conf": float(min(kps[wr, 2], kps[P.NOSE, 2], kps[el, 2])),
        "fore": float(np.linalg.norm(kps[wr, :2] - kps[el, :2]) / S),  # short = pointing at the camera
        "side": side,
    }


def _slope(t, y):
    if len(t) < 2:
        return 0.0
    t = t - t.mean()
    den = float((t * t).sum())
    return float((t * (y - y.mean())).sum() / den) if den > 1e-9 else 0.0


def _window_features_one(buf):
    """buf: list of (t, frame_features) covering ~WINDOW_S. -> np.array or None."""
    if len(buf) < 4:
        return None
    t = np.array([b[0] for b in buf])
    d = np.array([b[1]["d"] for b in buf])
    dy = np.array([b[1]["dy"] for b in buf])
    dx = np.array([b[1]["dx"] for b in buf])
    el = np.array([b[1]["elbow"] for b in buf])
    cf = np.array([b[1]["conf"] for b in buf])
    fo = np.array([b[1]["fore"] for b in buf])
    recent = t >= t[-1] - 0.3
    sd = _slope(t, d)
    sdr = _slope(t[recent], d[recent]) if recent.sum() >= 2 else sd
    half = t >= (t[0] + t[-1]) / 2
    accel = _slope(t[half], d[half]) - _slope(t[~half], d[~half]) if half.sum() >= 2 and (~half).sum() >= 2 else 0.0
    fit = d.mean() + sd * (t - t.mean())
    approach = max(-sdr, 0.05)
    ttc = min(max(d[-1] - CONTACT_D, 0.0) / approach, 3.0)
    return np.array([
        d[-1], d.min(), d[0] - d[-1], sd, sdr, accel,
        dy[-1], _slope(t, dy), dx[-1], el[-1], _slope(t, el),
        ttc, float(np.std(d - fit)), float(cf.mean()), fo[-1], _slope(t, fo),
        *_stop_estimate(t, d),
    ], np.float32)


def window_features(buf):
    """Long (1.0 s) + short (0.4 s) window features, concatenated."""
    long_ = _window_features_one(buf)
    if long_ is None:
        return None
    short_buf = [b for b in buf if b[0] >= buf[-1][0] - SHORT_S]
    short = _window_features_one(short_buf) if len(short_buf) >= 4 else long_
    return np.concatenate([long_, short])


class FeatureStream:
    """Keypoints in, window features out. The ONE place features are made,
    used by both the live detector and the trainer (train/run parity).

    * sticky hand choice: switch hands only when the other hand has been
      clearly closer to the mouth (by SWITCH_MARGIN) for SWITCH_FRAMES frames
    * glitch rejection: a hand that "teleports" faster than MAX_SPEED
      shoulder-widths/s is treated as a missed frame
    * the window restarts when the tracked hand changes
    """
    SWITCH_MARGIN = 0.35
    SWITCH_FRAMES = 3
    MAX_SPEED = 12.0

    def __init__(self):
        self.side = None
        self.buf = []
        self.other_better = 0

    def update(self, t, kps):
        """-> (window_features or None, frame_features or None)"""
        sides = {}
        for s, wi in (("l", P.LWRI), ("r", P.RWRI)):
            if kps[wi, 2] >= 0.2:
                sides[s] = frame_features(kps, s)
        sides = {s: f for s, f in sides.items() if f is not None}
        if not sides:
            return None, None
        if self.side not in sides:
            # current hand lost: take the closer one, but only restart if we must
            new = min(sides, key=lambda s: sides[s]["d"])
            if self.side is not None and self.buf and t - self.buf[-1][0] < 0.25:
                return None, None          # brief dropout: skip this frame
            self.side, self.buf, self.other_better = new, [], 0
        else:
            other = "l" if self.side == "r" else "r"
            if other in sides and sides[other]["d"] < sides[self.side]["d"] - self.SWITCH_MARGIN:
                self.other_better += 1
            else:
                self.other_better = 0
            if self.other_better >= self.SWITCH_FRAMES:
                self.side, self.buf, self.other_better = other, [], 0
        ff = sides[self.side]
        if self.buf:
            lt, lf = self.buf[-1]
            if abs(ff["d"] - lf["d"]) / max(t - lt, 1e-3) > self.MAX_SPEED:
                return None, None          # glitch
        self.buf = [b for b in self.buf if b[0] >= t - WINDOW_S] + [(t, ff)]
        return window_features(self.buf), ff


# ---------------------------------------------------------------- models
class IntakeModel:
    """Logistic regression or 1-hidden-layer MLP, weights in JSON."""

    def __init__(self, spec):
        self.spec = spec
        self.mu = np.array(spec["mu"], np.float32)
        self.sd = np.array(spec["sd"], np.float32)
        self.W = [np.array(w, np.float32) for w in spec["W"]]
        self.b = [np.array(b, np.float32) for b in spec["b"]]
        self.threshold = float(spec.get("threshold", 0.5))
        self.kind = spec["kind"]

    @classmethod
    def load(cls, path=MODEL_FILE):
        with open(path) as f:
            return cls(json.load(f))

    def prob(self, X):
        X = (np.atleast_2d(X) - self.mu) / self.sd
        h = X
        for i, (W, b) in enumerate(zip(self.W, self.b)):
            h = h @ W + b
            if i < len(self.W) - 1:
                h = np.tanh(h)
        return 1 / (1 + np.exp(-h[:, 0]))


class RuleModel:
    """C8 backup: no training. Fast approach that will reach the mouth soon."""
    kind = "rule"
    threshold = 0.5

    def prob(self, X):
        X = np.atleast_2d(X)
        i = F
        near = X[:, i["d_last_S"]] < 1.4
        approaching = X[:, i["slope_d_recent_S"]] < -1.0
        soon = X[:, i["ttc_S"]] < 0.6
        not_above = X[:, i["dy_last_S"]] > -0.35   # hand going to eyes/hair stays above the mouth
        steady = X[:, i["jitter_S"]] < 0.08
        return (near & approaching & soon & not_above & steady).astype(np.float32)


def load_model(kind=None):
    kind = kind or os.environ.get("SQUINT_INTAKE", "model")
    if kind == "rule" or not os.path.exists(MODEL_FILE):
        return RuleModel()
    return IntakeModel.load()


# ---------------------------------------------------------------- online detector
class IntakeDetector:
    """Feed it (t, keypoints, armed). It returns events to send on the bus.

    armed = a known bottle was in her hand within the last few seconds
    (set by vision_main from the bottle tracker).
    """

    def __init__(self, model=None, consec=2, threshold=None, arm_hold_s=8.0):
        self.model = model or load_model()
        self.thr = threshold if threshold is not None else self.model.threshold
        self.consec = consec
        self.arm_hold_s = arm_hold_s
        self.stream = FeatureStream()
        self.hits = 0
        self.state = "idle"      # idle -> fired -> at_mouth -> idle
        self.contact_t = None
        self.last_armed_t = -1e9
        self.last_p = 0.0

    def update(self, t, kps, armed):
        if armed:
            self.last_armed_t = t
        is_armed = (t - self.last_armed_t) <= self.arm_hold_s
        events = []
        x, ff = self.stream.update(t, kps)
        if x is None:
            return events
        p = float(self.model.prob(x)[0])
        self.last_p = p
        d = ff["d"]

        if self.state == "idle":
            self.hits = self.hits + 1 if p >= self.thr else 0
            if self.hits >= self.consec and is_armed:
                ttc = float(x[F["ttc_S"]])
                events.append({"type": "intake_start", "confidence": round(p, 3),
                               "lead_ms": int(ttc * 1000)})
                self.state = "fired"
            # No "late" fallback: a hand that merely reaches the mouth area (chin rest,
            # reading the label up close) must not log a dose. A miss falls back to
            # D's "I took it" button.
        if self.state == "fired":
            if d < CONTACT_D:
                self.state, self.contact_t = "at_mouth", t
            elif d > RESET_D:
                self.state, self.hits = "idle", 0       # put the hand down: no pill taken
        elif self.state == "at_mouth":
            if d > RELEASE_D or t - self.contact_t > 2.0:
                events.append({"type": "intake_done"})
                self.state, self.hits = "idle", 0
                self.last_armed_t = -1e9              # that dose is done; re-arm on next bottle
        return events
