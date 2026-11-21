"""Part C's real program: camera -> pose -> bottle + intake -> bus.

    python vision_main.py --source 0 --show          # laptop webcam with debug overlay
    python vision_main.py --source qnx               # on the Pi (Part B's get_frame)
    python vision_main.py --source clip.mp4 --show   # replay a recorded clip
    python vision_main.py --sim double               # no camera: simulated person + bottles

Sends:    bottle_seen {med, confidence, candidates}  (med = id | "unknown" | "none"; only on change)
          candidates = enrolled bottles it could be (look-alikes): D confirms with the NFC tag
          intake_start {confidence, lead_ms, med, frame_time}
          intake_done {med}
          enroll_progress {med, percent}
Listens:  enroll_start {med}, meds_changed
Writes:   data/camera.jpg (latest frame, ~2 Hz) for the API's GET /camera.jpg
"""
import argparse
import json
import os
import threading
import time

import cv2
import numpy as np

import bus
from squint_vision import pose as P
from squint_vision.bottles import EMPTY, BottleTracker, Embedder, Gallery
from squint_vision.intake import IntakeDetector

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
ENROL_SHOTS = 15
ENROL_SECONDS = 6.0
ENROL_TIMEOUT_S = 20.0
PERSON_MIN = 0.3      # nose and at least one shoulder must be this confident
HAND_MIN = 0.3        # ...and the wrist we crop around
FRESH_FRAMES = 3      # bottle frames needed after a dose before the next intake can fire


def person_present(kps):
    return kps[P.NOSE, 2] >= PERSON_MIN and max(kps[P.LSHO, 2], kps[P.RSHO, 2]) >= PERSON_MIN


class Vision:
    def __init__(self, meds_path, bottle_every=1, verbose=True):
        self.pose = None
        self.embed = Embedder()
        self.gallery = Gallery()
        self.tracker = BottleTracker()
        self.intake = IntakeDetector()
        self.meds_path = meds_path
        self.bottle_every = bottle_every
        self.verbose = verbose
        self.frame_i = 0
        self.enrol = None          # {"med", "shots": [], "next_t"}
        self.lock = threading.Lock()
        self.last_jpg_t = 0.0
        self.recent_cands = []     # candidate sets from the last 5 frames
        self.person = False
        self.held_med = "none"     # last bottle seen in hand (survives brief "none" flickers)
        self.intake_med = None     # bottle named in intake_start, reused for its intake_done
        self.fresh_needed = 0      # after a dose: bottle frames still needed before intake can re-arm
        self.load_meds()

    # ---------------- bus handlers
    def load_meds(self, _msg=None):
        try:
            with open(self.meds_path) as f:
                self.meds = {m["id"]: m for m in json.load(f)}
        except (OSError, ValueError):
            self.meds = {}
        self.gallery.reload()
        if self.verbose:
            print(f"[vision] meds={list(self.meds)} enrolled={sorted(self.gallery.items)}")

    def on_enroll_start(self, msg):
        with self.lock:
            self.enrol = {"med": msg["med"], "shots": [], "next_t": 0.0}
        bus.send({"type": "enroll_progress", "med": msg["med"], "percent": 0})

    # ---------------- per frame
    def send(self, ev):
        msg = bus.send(ev)
        if self.verbose:
            print("[vision] ->", json.dumps({k: v for k, v in msg.items() if k not in ("time", "from")}))

    def step(self, t, frame=None, kps=None, crop=None):
        """One frame. In --sim mode kps/crop are given directly."""
        if kps is None:
            if self.pose is None:
                self.pose = P.Pose()
            kps = self.pose(frame)
        # MoveNet always returns 17 points, even for an empty room (low-confidence guesses).
        # Only trust a hand crop when a person AND a wrist are confidently there.
        self.person = person_present(kps)
        side = self.intake.stream.side or P.active_hand(kps, min_score=HAND_MIN)
        hand_ok = self.person and side is not None and kps[P.LWRI if side == "l" else P.RWRI, 2] >= HAND_MIN
        if crop is None and frame is not None and hand_ok:
            x0, y0, x1, y1 = P.hand_crop_box(kps, side, frame.shape)
            crop = frame[y0:y1, x0:x1] if x1 - x0 > 16 and y1 - y0 > 16 else None
        self.frame_i += 1

        # enrolment has priority over recognition; it only ever uses real hand crops
        with self.lock:
            en = self.enrol
        if en is not None:
            self._enrol_step(t, en, crop)
            return kps, crop, None

        label = None
        if self.frame_i % self.bottle_every == 0:
            if crop is not None:
                label, conf, scores = self.gallery.classify(self.embed(crop))
                self.recent_cands = (self.recent_cands + [self.gallery.candidates(scores)])[-5:]
            else:
                # nobody / no hand in view: there is no bottle in a hand. Feeding "none"
                # lets the smoother drop a stale "warfarin" within ~4 frames.
                label, conf = "none", 0.0
            # Mid-intake the bottle is tilted and next to the face, so the crop often looks like
            # an empty hand. The bottle can't have been put down during the reach: ignore "none".
            if label == "none" and self.intake.state != "idle":
                label = None
                self.tracker.keep()
            ch = self.tracker.update(label, conf, t) if label is not None else None
            if ch:
                ev = {"type": "bottle_seen", "med": ch[0], "confidence": round(ch[1], 3), "frame_time": t}
                if ch[0] == "unknown":
                    ev["candidates"] = self.stable_candidates()
                self.send(ev)
        if label is not None and label != "none" and self.fresh_needed:
            self.fresh_needed -= 1
        if self.tracker.current != "none":
            self.held_med = self.tracker.current
        # The smoothed verdict holds a bottle for a few seconds after it disappears, so it can't
        # arm the next dose by itself: after intake_done the bottle must actually be seen again.
        # Otherwise an empty hand raised to the mouth just after a dose re-fires intake_start.
        armed = self.tracker.current != "none" and not self.fresh_needed
        for ev in self.intake.update(t, kps, armed):
            if ev["type"] == "intake_start":
                # armed may come from the 8 s hold after the verdict went to "none": name the held bottle
                med = self.tracker.current if self.tracker.current != "none" else self.held_med
                self.intake_med = med
            else:
                # intake_done is about the same dose as its intake_start, whatever is visible now
                med = self.intake_med if self.intake_med is not None else self.tracker.current
                self.intake_med = None
                self.fresh_needed = FRESH_FRAMES
            ev["med"] = med
            ev["frame_time"] = t
            self.send(ev)
        return kps, crop, label

    def stable_candidates(self):
        counts = {}
        for cs in self.recent_cands:
            for c in cs:
                counts[c] = counts.get(c, 0) + 1
        return sorted(c for c, n in counts.items() if n >= 2)

    def _enrol_step(self, t, en, img):
        en.setdefault("start_t", t)
        if img is None:
            # no confident hand: never fall back to the whole frame (that teaches it the room)
            if not en.get("hinted") and t - en["start_t"] > 3 and not en["shots"]:
                en["hinted"] = True
                self.send({"type": "enroll_progress", "med": en["med"], "percent": 0,
                           "hint": "I can't see your hand. Stand back so your head, shoulders and the hand "
                                   "holding the bottle are in view, bottle at chest height."})
            if t - en["start_t"] > ENROL_TIMEOUT_S:
                self.send({"type": "enroll_progress", "med": en["med"], "percent": -1,
                           "error": f"enrolment stopped: only {len(en['shots'])} of {ENROL_SHOTS} photos had a "
                                    "visible hand. Nothing was saved; try again further back."})
                with self.lock:
                    self.enrol = None
            return
        if t < en["next_t"]:
            return
        en["shots"].append(img.copy())
        en["next_t"] = t + ENROL_SECONDS / ENROL_SHOTS
        pct = int(100 * len(en["shots"]) / ENROL_SHOTS)
        if len(en["shots"]) >= ENROL_SHOTS:
            embs = [self.embed(s) for s in en["shots"]]
            self.gallery.add(en["med"], embs)
            d = os.path.join(DATA, "enroll", en["med"])
            os.makedirs(d, exist_ok=True)
            for i, s in enumerate(en["shots"]):
                cv2.imwrite(os.path.join(d, f"{i:02d}.jpg"), s)
            with self.lock:
                self.enrol = None
            self.tracker = BottleTracker()
            pct = 100
        if pct % 20 == 0 or pct == 100 or len(en["shots"]) % 3 == 0:
            self.send({"type": "enroll_progress", "med": en["med"], "percent": pct})

    def save_jpg(self, t, frame):
        if frame is not None and t - self.last_jpg_t > 0.5:
            self.last_jpg_t = t
            os.makedirs(DATA, exist_ok=True)
            tmp = os.path.join(DATA, "camera.tmp.jpg")
            cv2.imwrite(tmp, frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            os.replace(tmp, os.path.join(DATA, "camera.jpg"))   # atomic: the API never reads half a file


def draw(frame, kps, v, label):
    for i in range(11):
        if kps[i, 2] > 0.2:
            cv2.circle(frame, (int(kps[i, 0]), int(kps[i, 1])), 4, (0, 255, 0), -1)
    m = P.mouth(kps)
    cv2.circle(frame, (int(m[0]), int(m[1])), 6, (0, 0, 255), 2)
    side = v.intake.stream.side
    if side:
        x0, y0, x1, y1 = P.hand_crop_box(kps, side, frame.shape)
        cv2.rectangle(frame, (x0, y0), (x1, y1), (255, 200, 0), 2)
    who = "person" if v.person else "NO PERSON (bottle check off)"
    cv2.putText(frame, f"{who}  bottle: {v.tracker.current}  frame: {label}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (255, 255, 255) if v.person else (0, 165, 255), 2)
    if v.enrol is not None:
        cv2.putText(frame, f"ENROLLING {v.enrol['med']}: {len(v.enrol['shots'])}/{ENROL_SHOTS}  (hand must be visible)",
                    (10, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    cv2.putText(frame, f"intake p={v.intake.last_p:.2f} state={v.intake.state}", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (0, 0, 255) if v.intake.state != "idle" else (255, 255, 255), 2)
    return frame


def run_sim(v, scenario, realtime=True):
    """No camera: simulated keypoints + rendered bottle crops through the same Vision.step."""
    from sim.bottle_sim import BOTTLES, UNKNOWN, render
    from sim.pose_sim import simulate
    rng = np.random.default_rng(int(time.time()))
    plans = {
        "correct": [("warfarin", "bottle_to_mouth")],
        "double": [("warfarin", "bottle_to_mouth"), ("warfarin", "bottle_to_mouth")],
        "robert": [("metoprolol_robert", "bottle_to_mouth")],
        "unknown": [("lisinopril_lookalike", "read_label")],
        "scratch": [(None, "nose_scratch")],
        "read": [("warfarin", "read_label")],
    }
    specs = {**BOTTLES, **UNKNOWN}
    if not v.gallery.items:   # sim enrolment so the demo works out of the box
        for med in BOTTLES:
            v.gallery.add(med, [v.embed(render(BOTTLES[med], rng, "enrol")) for _ in range(ENROL_SHOTS)], save=False)
        v.gallery.add(EMPTY, [v.embed(render(None, rng, "enrol")) for _ in range(ENROL_SHOTS)], save=False)
    t_base = time.time()
    for med, kind in plans[scenario]:
        seq = simulate(kind, rng, fps=15)
        print(f"[sim] {kind} holding {med}  (hand reaches mouth at +{seq['t_contact'] or 0:.2f}s)")
        t0 = time.time() - t_base
        for t, kps in zip(seq["t"], seq["kps"]):
            # the bottle is in hand from the start of the reach until it goes back down
            in_hand = med is not None and t >= seq["t_on"] - 0.4
            crop = render(specs[med] if in_hand else None, rng, "test")
            v.step(t0 + float(t), kps=kps, crop=crop)
            if realtime:
                time.sleep(max(0.0, (t_base + t0 + float(t)) - time.time()))
        # put the bottle down between actions
        for i in range(8):
            v.step(t0 + float(seq["t"][-1]) + 0.07 * (i + 1), kps=seq["kps"][0], crop=render(None, rng, "test"))
        time.sleep(0.5 if realtime else 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="0", help="webcam index, video path, or 'qnx'")
    ap.add_argument("--sim", help="correct|double|robert|unknown|scratch|read")
    ap.add_argument("--meds", default=os.environ.get("SQUINT_MEDS", os.path.join(HERE, "..", "medications.json")))
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--bottle-every", type=int, default=1, help="run bottle recognition every Nth frame (Pi: 2)")
    ap.add_argument("--enroll-empty", action="store_true", help="enrol the empty-hand/background class, then exit")
    a = ap.parse_args()

    bus.init("vision")
    v = Vision(a.meds, a.bottle_every)
    bus.on("enroll_start", v.on_enroll_start)
    bus.on("meds_changed", v.load_meds)
    if a.enroll_empty:
        v.on_enroll_start({"med": EMPTY})
    if a.sim:
        run_sim(v, a.sim)
        time.sleep(0.5)
        return
    cam = Camera(a.source)
    while True:
        t, frame = cam.read()
        if frame is None:
            break
        kps, crop, label = v.step(t, frame)
        v.save_jpg(t, frame)
        if a.enroll_empty and v.enrol is None:
            print("[vision] empty-hand class enrolled")
            return
        if a.show:
            cv2.imshow("squint vision", draw(frame.copy(), kps, v, label))
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break


if __name__ == "__main__":
    from squint_vision.camera import Camera  # noqa: E402  (keeps --sim free of camera imports)
    main()
