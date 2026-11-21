"""Simulated MoveNet keypoint sequences for training and testing the intake model.

Why simulate: real clips (C5) take an hour of acting and come late on Saturday.
The simulator gives thousands of labelled sequences tonight, with the hard
cases built in, and the same file format as real clips, so
train_intake.py / eval_intake.py run unchanged on either.

Model of the scene (the station's camera: chest height, ~60 cm away):
  * 3D upper body in metres, camera at origin looking +z, y down.
  * Arms are 2-link chains solved with IK; the hand follows a minimum-jerk
    path (how human reaches actually look) with an arc, optional pauses.
  * Pinhole projection f=500 px, 640x480, random camera roll / height / yaw of
    the person, distance 0.45-1.0 m, body size 0.85-1.15.
  * MoveNet-style noise: AR(1) jitter that grows with hand speed (motion blur),
    face keypoints degraded when the hand covers the face, dropouts, wrist
    glitches, uneven frame timing and dropped frames, 10-20 fps.

Sequence dict: t (T,), kps (T,17,3) px+score, kind, label (1 = pill intake),
armed (bottle in hand per frame), t_on (approach start), t_contact (hand at
mouth; None for negatives).
"""
import numpy as np

F, W, H = 330.0, 640, 480    # Pi Camera Module 3 Wide (~102 deg diagonal) at 640x480
NOSE, LEYE, REYE, LEAR, REAR, LSHO, RSHO, LELB, RELB, LWRI, RWRI, LHIP, RHIP = range(13)

POSITIVE = ["bottle_to_mouth", "palm_to_mouth", "bottle_to_mouth_slow", "hesitant_intake"]
NEGATIVE = ["drink_water", "nose_scratch", "rub_eye", "touch_hair", "chin_touch", "phone_to_ear",
            "read_label", "read_label_close", "reach_shelf", "wave", "collar", "aborted_raise",
            "put_down_pick_up", "idle", "cough_cover"]


def min_jerk(tau):
    tau = np.clip(tau, 0, 1)
    return 10 * tau ** 3 - 15 * tau ** 4 + 6 * tau ** 5


def rot_y(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def ik_elbow(sh, wr, L1, L2, pole):
    """2-link IK: elbow position given shoulder, wrist target, bone lengths, pole dir."""
    v = wr - sh
    D = np.linalg.norm(v)
    D = np.clip(D, abs(L1 - L2) + 1e-3, L1 + L2 - 1e-3)
    u = v / (np.linalg.norm(v) + 1e-9)
    a = (L1 ** 2 - L2 ** 2 + D ** 2) / (2 * D)
    h = np.sqrt(max(L1 ** 2 - a ** 2, 1e-9))
    p = pole - np.dot(pole, u) * u
    p /= np.linalg.norm(p) + 1e-9
    return sh + a * u + h * p, sh + D * u


class Person:
    def __init__(self, rng):
        k = rng.uniform(0.85, 1.15)
        self.k = k
        self.L1, self.L2 = 0.30 * k, 0.26 * k
        self.Z = rng.uniform(0.5, 1.0)
        self.x0 = rng.uniform(-0.12, 0.12)
        self.y_sh = rng.uniform(-0.06, 0.10)      # shoulders vs camera (camera ~chin/chest height, face in view)
        self.yaw = rng.uniform(-0.45, 0.45)
        self.roll = rng.uniform(-0.08, 0.08)
        self.hand = "r" if rng.random() < 0.75 else "l"

    def skeleton(self, sway, head_tilt):
        """Body points in camera coords (no arms of the active side)."""
        k, R = self.k, rot_y(self.yaw)
        c = np.array([self.x0 + sway[0], self.y_sh + sway[1], self.Z])
        pts = {
            LSHO: [0.19 * k, 0, 0], RSHO: [-0.19 * k, 0, 0],
            LHIP: [0.15 * k, 0.5 * k, 0.02], RHIP: [-0.15 * k, 0.5 * k, 0.02],
            NOSE: [0, -0.22 * k, -0.10 * k],
            LEYE: [0.032 * k, -0.262 * k, -0.08 * k], REYE: [-0.032 * k, -0.262 * k, -0.08 * k],
            LEAR: [0.075 * k, -0.25 * k, -0.0], REAR: [-0.075 * k, -0.25 * k, -0.0],
        }
        out = {}
        neck = np.array([0, -0.12 * k, 0])
        for i, p in pts.items():
            p = np.array(p, float)
            if i in (NOSE, LEYE, REYE, LEAR, REAR):   # head pitches back about the neck
                q = p - neck
                ca, sa = np.cos(head_tilt), np.sin(head_tilt)
                q = np.array([q[0], ca * q[1] + sa * q[2], -sa * q[1] + ca * q[2]])
                p = q + neck
            out[i] = R @ p + c
        return out

    def mouth3d(self, body):
        eyes = (body[LEYE] + body[REYE]) / 2
        return body[NOSE] + 0.9 * (body[NOSE] - eyes)


def project(p, roll, cy_off):
    x, y = F * p[0] / p[2], F * p[1] / p[2]
    c, s = np.cos(roll), np.sin(roll)
    return np.array([W / 2 + c * x - s * y, H / 2 + cy_off + s * x + c * y])


def target_for(kind, body, mouth, side, rng, k):
    sgn = -1 if side == "r" else 1
    n, ey = body[NOSE], body[LEYE] if side == "l" else body[REYE]
    jitter = rng.normal(0, 0.008, 3)
    if kind in ("bottle_to_mouth", "palm_to_mouth", "bottle_to_mouth_slow", "hesitant_intake", "drink_water",
                "aborted_raise", "cough_cover"):
        t = mouth + np.array([0, 0.01, -0.03])
    elif kind == "nose_scratch":
        t = n + np.array([sgn * 0.01, -0.005, -0.03])
    elif kind == "rub_eye":
        t = ey + np.array([0, 0, -0.03])
    elif kind == "touch_hair":
        t = n + np.array([sgn * 0.06, -0.16 * k, 0.02])
    elif kind == "chin_touch":
        t = mouth + np.array([0, 0.055 * k, -0.02])
    elif kind == "phone_to_ear":
        t = (body[LEAR] if side == "l" else body[REAR]) + np.array([sgn * 0.03, 0.02, 0])
    elif kind == "read_label":
        t = mouth + np.array([sgn * -0.02, rng.uniform(0.02, 0.10), -rng.uniform(0.22, 0.32)])
    elif kind == "read_label_close":
        t = mouth + np.array([0, rng.uniform(-0.03, 0.04), -rng.uniform(0.14, 0.2)])
    elif kind == "reach_shelf":
        t = body[LSHO if side == "l" else RSHO] + np.array([sgn * 0.15, -0.45 * k, -0.25])
    elif kind == "wave":
        t = body[LSHO if side == "l" else RSHO] + np.array([sgn * 0.2, -0.35 * k, -0.1])
    elif kind == "collar":
        t = mouth + np.array([sgn * 0.03, 0.15 * k, 0.0])
    elif kind == "put_down_pick_up":
        t = body[LSHO if side == "l" else RSHO] + np.array([sgn * -0.05, 0.25 * k, -0.30])
    else:  # idle
        t = None
    return None if t is None else t + jitter


def simulate(kind, rng, fps=None):
    P = Person(rng)
    fps = fps or rng.uniform(10, 20)
    k = P.k
    side = P.hand
    # timing
    t_idle0 = rng.uniform(0.4, 2.0)
    slow = kind in ("bottle_to_mouth_slow",)
    T_app = rng.uniform(1.1, 2.0) if slow else rng.uniform(0.45, 1.3)
    pause = rng.uniform(0.3, 0.9) if kind == "hesitant_intake" else 0.0
    dwell = rng.uniform(0.3, 1.5)
    T_ret = rng.uniform(0.5, 1.2)
    t_idle1 = rng.uniform(0.3, 1.5)
    total = t_idle0 + T_app + pause + dwell + T_ret + t_idle1
    # timestamps with jitter and dropped frames
    ts, t = [], 0.0
    while t < total:
        if rng.random() > 0.03:
            ts.append(t)
        t += (1 / fps) * rng.uniform(0.85, 1.15)
    ts = np.array(ts)

    rest_off = np.array([(-1 if side == "r" else 1) * 0.02, 0.28 * k, -0.22 * k])
    sway_f, sway_a = rng.uniform(0.1, 0.4), rng.uniform(0.002, 0.012)
    other_rest = np.array([(1 if side == "r" else -1) * 0.04, 0.33 * k, -0.15])

    roll, cy_off = P.roll, rng.uniform(-20, 20)
    arc = rng.uniform(0.03, 0.10)            # hand path bulges forward/out
    over = rng.uniform(0.0, 0.25) if kind == "aborted_raise" else 1.0
    tilt_max = rng.uniform(0.05, 0.25) if kind in ("bottle_to_mouth", "bottle_to_mouth_slow", "hesitant_intake",
                                                   "drink_water") else rng.uniform(0, 0.04)
    if kind == "aborted_raise":
        over = rng.uniform(0.35, 0.7)        # gets partway, then lowers the hand

    kps = np.zeros((len(ts), 17, 3), np.float32)
    true_d = np.zeros(len(ts))
    t_on = t_idle0
    t_arrive = None
    noise_state = np.zeros((17, 2))
    prev_hand2d = None
    sh_i, el_i, wr_i = (LSHO, LELB, LWRI) if side == "l" else (RSHO, RELB, RWRI)
    o_sh, o_el, o_wr = (RSHO, RELB, RWRI) if side == "l" else (LSHO, LELB, LWRI)
    pole = np.array([(1 if side == "l" else -1) * 0.5, 1.0, 0.3])
    phase_osc = rng.uniform(0, 6.28)

    for fi, tt in enumerate(ts):
        sway = sway_a * np.array([np.sin(2 * np.pi * sway_f * tt), 0.5 * np.sin(2 * np.pi * sway_f * 1.3 * tt)])
        # progress along the approach: 0 at rest, 1 at target
        if tt < t_on:
            s = 0.0
        elif tt < t_on + T_app + pause:
            if pause > 0:
                t1 = T_app * 0.5
                if tt < t_on + t1:
                    s = 0.5 * min_jerk((tt - t_on) / t1)
                elif tt < t_on + t1 + pause:
                    s = 0.5
                else:
                    s = 0.5 + 0.5 * min_jerk((tt - t_on - t1 - pause) / (T_app - t1))
            else:
                s = min_jerk((tt - t_on) / T_app)
            s *= over
        elif tt < t_on + T_app + pause + dwell:
            s = over
        elif tt < t_on + T_app + pause + dwell + T_ret:
            s = over * (1 - min_jerk((tt - t_on - T_app - pause - dwell) / T_ret))
        else:
            s = 0.0
        if kind == "aborted_raise" and t_on + T_app * 0.6 < tt:
            # lower straight after reaching the partial point
            ta = tt - t_on - T_app * 0.6
            s = over * min_jerk(min((tt - t_on) / (T_app * 0.6), 1)) * (1 - min_jerk(ta / T_ret))
        tilt = tilt_max * (s / max(over, 1e-3)) ** 3 if kind != "aborted_raise" else 0.0
        body = P.skeleton(sway, tilt)
        mouth = P.mouth3d(body)
        sh = body[sh_i]
        rest = sh + rest_off
        tgt = target_for(kind, body, mouth, side, rng, k) if kind != "idle" else None
        if tgt is None:
            hand = rest + np.array([0, 0.01 * np.sin(tt * 2), 0])
        else:
            hand = rest + s * (tgt - rest)
            bulge = np.array([(-1 if side == "r" else 1) * 0.3, 0, -1.0])
            hand = hand + arc * np.sin(np.pi * min(s / max(over, 1e-3), 1)) * bulge / np.linalg.norm(bulge)
            if kind in ("nose_scratch", "rub_eye") and s > 0.95 * over:
                hand = hand + 0.012 * np.array([np.sin(tt * 25 + phase_osc), 0.5 * np.cos(tt * 25), 0])
            if kind == "wave" and s > 0.9:
                hand = hand + 0.07 * np.array([np.sin(tt * 9), 0, 0])
        # solve the wrist so that hand = wrist + 0.3*(wrist - elbow)
        wr = hand.copy()
        for _ in range(4):
            el, wr_s = ik_elbow(sh, wr, P.L1, P.L2, pole)
            fore = (wr_s - el) / (np.linalg.norm(wr_s - el) + 1e-9)
            wr = hand - 0.3 * P.L2 * fore
        el, wr = ik_elbow(sh, wr, P.L1, P.L2, pole)
        hand_true = wr + 0.3 * (wr - el)
        dist = np.linalg.norm(hand_true - mouth)
        true_d[fi] = dist
        if kind in POSITIVE and t_arrive is None and tt > t_on and dist < 0.035 + 0.01:
            t_arrive = tt
        # other arm rests
        oel, owr = ik_elbow(body[o_sh], body[o_sh] + other_rest, P.L1, P.L2,
                            np.array([(1 if side == "r" else -1) * 0.5, 1.0, 0.3]))
        pts = dict(body)
        pts.update({el_i: el, wr_i: wr, o_el: oel, o_wr: owr})
        for i in range(13):
            kps[fi, i, :2] = project(pts[i], roll, cy_off)
            kps[fi, i, 2] = 0.85
        kps[fi, 13:, 2] = 0.05          # legs: off screen
        kps[fi, 13:, :2] = kps[fi, LHIP, :2]

        # ---- MoveNet-like noise
        S = np.linalg.norm(kps[fi, LSHO, :2] - kps[fi, RSHO, :2]) + 1e-6
        S = max(S, 0.3 * F * 0.38 * k / P.Z)   # strongly yawed body: keep scale sane for noise
        hand2d = kps[fi, wr_i, :2]
        speed = 0.0 if prev_hand2d is None else np.linalg.norm(hand2d - prev_hand2d) * fps / S
        prev_hand2d = hand2d.copy()
        base = rng.uniform(0.008, 0.02)
        sig = np.full(17, base) * S
        sig[[LWRI, RWRI]] *= 1.5 + 0.6 * min(speed, 4)
        sig[[LELB, RELB]] *= 1.3
        face_d = np.linalg.norm(hand2d - kps[fi, NOSE, :2]) / S
        if face_d < 0.35:   # hand covers the face
            sig[[NOSE, LEYE, REYE]] *= 2.5
            kps[fi, [NOSE, LEYE, REYE], 2] *= rng.uniform(0.4, 0.9)
        noise_state = 0.6 * noise_state + 0.4 * rng.normal(0, 1, (17, 2)) * sig[:, None]
        kps[fi, :, :2] += noise_state
        kps[fi, :13, 2] = np.clip(kps[fi, :13, 2] + rng.normal(0, 0.05, 13), 0, 1)
        out = (kps[fi, :, 0] < 0) | (kps[fi, :, 0] >= W) | (kps[fi, :, 1] < 0) | (kps[fi, :, 1] >= H)
        kps[fi, out, 2] = np.minimum(kps[fi, out, 2], rng.uniform(0.0, 0.15))   # MoveNet can't see off-frame points
        if rng.random() < 0.03:                     # dropout of the active wrist
            kps[fi, wr_i, 2] = rng.uniform(0.0, 0.18)
        if rng.random() < 0.01:                     # wrist glitch
            kps[fi, wr_i, :2] += rng.normal(0, 0.5 * S, 2)

    label = 1 if kind in POSITIVE else 0
    if label and t_arrive is None:
        t_arrive = t_on + T_app + pause
    armed_seq = kind in POSITIVE or kind in ("read_label", "read_label_close", "put_down_pick_up", "aborted_raise")
    return {"t": ts.astype(np.float32), "kps": kps, "kind": kind, "label": label,
            "armed": np.full(len(ts), armed_seq), "t_on": float(t_on),
            "t_contact": float(t_arrive) if label else None, "fps": float(fps)}


def make_dataset(n, seed, pos_frac=0.4):
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        if rng.random() < pos_frac:
            kind = POSITIVE[rng.integers(len(POSITIVE))]
        else:
            kind = NEGATIVE[rng.integers(len(NEGATIVE))]
        out.append(simulate(kind, rng))
    return out
