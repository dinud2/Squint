"""Part C's real program: camera -> pose -> bottle + intake -> bus.

    python vision_main.py --source 0 --show          # laptop webcam with debug overlay
    python vision_main.py --source qnx               # on the Pi (Part B's get_frame)
    python vision_main.py --source clip.mp4 --show   # replay a recorded clip
    python vision_main.py --sim double               # no camera: simulated person + bottles

Sends:    bottle_seen {med, confidence}  (med = id | "unknown" | "none"; only on change)
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
        side = self.intake.stream.side or P.active_hand(kps)
        if crop is None and frame is not None:
            if side and kps[P.LWRI if side == "l" else P.RWRI, 2] > 0.2:
                x0, y0, x1, y1 = P.hand_crop_box(kps, side, frame.shape)
                crop = frame[y0:y1, x0:x1] if x1 - x0 > 16 and y1 - y0 > 16 else None
        self.frame_i += 1

        # enrolment has priority over recognition
        with self.lock:
            en = self.enrol
        if en is not None:
            self._enrol_step(t, en, crop if crop is not None else frame)
            return kps, crop, None

        label = None
        if crop is not None and self.frame_i % self.bottle_every == 0:
            label, conf, _ = self.gallery.classify(self.embed(crop))
            ch = self.tracker.update(label, conf)
            if ch:
                self.send({"type": "bottle_seen", "med": ch[0], "confidence": round(ch[1], 3), "frame_time": t})
        armed = self.tracker.current != "none"
        for ev in self.intake.update(t, kps, armed):
            ev["med"] = self.tracker.current
            ev["frame_time"] = t
            self.send(ev)
        return kps, crop, label

    def _enrol_step(self, t, en, img):
        if img is None or t < en["next_t"]:
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
    cv2.putText(frame, f"bottle: {v.tracker.current}  frame: {label}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
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
