"""C5: record labelled intake / look-alike clips at the station (Sat 11:00 session).

    python tools/record_clips.py --who ved --source http://<pi>:8080/stream
    python tools/record_clips.py --who dinu --source http://<pi>:8080/stream --auto bottle_to_mouth --count 6

Keyboard mode: pick the movement first, then SPACE to start / stop recording. q quits.
  1 bottle to mouth      2 pill from palm to mouth   3 drink water
  4 nose scratch         5 read the label (bottle)   6 chin / face touch
  7 put bottle down / pick up                         8 other (wave, reach, idle)
  9 aborted raise (bottle lifted part way, then lowered)

Hands-free mode (--auto KIND): no keys needed, so you can stand at the real distance.
The window counts down in big letters, records --seconds, pauses, and repeats --count times.
Do the movement ONCE per clip, starting from rest, after "GO".

Each clip -> data/clips/<kind>_<who>_<n>.mp4 + .json {kind, label, armed, fps}
The mp4 is written at the frame rate actually measured while recording (the Pi stream
runs at ~20 fps; writing it as 15 fps made every movement 33% slower than real).
"""
import argparse
import json
import os
import sys
import time

import cv2

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from squint_vision.camera import Camera  # noqa: E402

KINDS = {ord("1"): ("bottle_to_mouth", 1, True), ord("2"): ("palm_to_mouth", 1, True),
         ord("3"): ("drink_water", 0, False), ord("4"): ("nose_scratch", 0, False),
         ord("5"): ("read_label", 0, True), ord("6"): ("chin_touch", 0, False),
         ord("7"): ("put_down_pick_up", 0, True), ord("8"): ("other", 0, False),
         ord("9"): ("aborted_raise", 0, True)}
BY_NAME = {v[0]: v for v in KINDS.values()}
HINTS = {"bottle_to_mouth": "bottle in hand: lift it to your mouth, then lower",
         "palm_to_mouth": "tip a pill into your palm, palm to mouth, lower",
         "drink_water": "lift a cup/bottle of water to drink, lower",
         "nose_scratch": "EMPTY hand: scratch your nose, lower",
         "read_label": "bottle in hand: lift it to read the label up close, lower",
         "chin_touch": "EMPTY hand: rest/touch your chin, lower",
         "put_down_pick_up": "put the bottle down, pick it up again",
         "other": "EMPTY hand: wave / reach / stand still",
         "aborted_raise": "bottle in hand: start lifting it, stop half way, lower"}


def save(stem, frames, times, kind, who):
    if len(frames) < 5:
        print("  too short, not saved")
        return False
    fps = (len(times) - 1) / max(times[-1] - times[0], 1e-3)
    h, w = frames[0].shape[:2]
    vw = cv2.VideoWriter(stem + ".mp4", cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for f in frames:
        vw.write(f)
    vw.release()
    with open(stem + ".json", "w") as f:
        json.dump({"kind": kind[0], "label": kind[1], "armed": kind[2], "who": who, "fps": round(fps, 2)}, f)
    print(f"  saved {os.path.basename(stem)}.mp4  {len(frames)} frames @ {fps:.1f} fps")
    return True


def banner(img, lines, color):
    out = img.copy()
    cv2.rectangle(out, (0, 0), (out.shape[1], 40 + 60 * len(lines)), (0, 0, 0), -1)
    for i, (txt, scale) in enumerate(lines):
        cv2.putText(out, txt, (15, 55 + 60 * i), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 3)
    return out


def run_auto(cam, kind, a, out):
    n = 0
    for i in range(a.count):
        # countdown (keeps reading so the shown frame is live)
        end = time.time() + (a.lead if i == 0 else a.gap)
        while time.time() < end:
            _, fr = cam.read()
            left = int(end - time.time()) + 1
            cv2.imshow("record", banner(fr, [(f"{kind[0]}  {i + 1}/{a.count}", 1.1),
                                             (f"get ready... {left}", 1.6),
                                             (HINTS[kind[0]], 0.7)], (0, 255, 255)))
            if (cv2.waitKey(1) & 0xFF) == ord("q"):
                return n
        stem = os.path.join(out, f"{kind[0]}_{a.who}_{int(time.time() * 1000)}")
        frames, times = [], []
        end = time.time() + a.seconds
        while time.time() < end:
            t, fr = cam.read()
            frames.append(fr); times.append(t)
            cv2.imshow("record", banner(fr, [(f"GO  {kind[0]}", 1.6), (f"{end - time.time():.1f}s", 1.2)],
                                        (0, 0, 255)))
            if (cv2.waitKey(1) & 0xFF) == ord("q"):
                return n
        n += save(stem, frames, times, kind, a.who)
    return n


def run_keys(cam, a, out):
    kind, rec, n = KINDS[ord("1")], None, 0
    while True:
        t, frame = cam.read()
        if frame is None:
            break
        if rec is not None:
            rec["frames"].append(frame); rec["times"].append(t)
        show = frame.copy()
        cv2.putText(show, f"{kind[0]}  {'REC' if rec else 'ready'}  ({n} saved)", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255) if rec else (0, 255, 0), 2)
        cv2.imshow("record", show)
        k = cv2.waitKey(1) & 0xFF
        if k in KINDS and rec is None:
            kind = KINDS[k]
        elif k == ord(" "):
            if rec is None:
                rec = {"stem": os.path.join(out, f"{kind[0]}_{a.who}_{int(time.time() * 1000)}"),
                       "frames": [], "times": []}
            else:
                n += save(rec["stem"], rec["frames"], rec["times"], kind, a.who)
                rec = None
        elif k == ord("q"):
            break
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--who", required=True)
    ap.add_argument("--source", default="0")
    ap.add_argument("--auto", choices=sorted(BY_NAME), help="hands-free: record this movement --count times")
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--seconds", type=float, default=4.0, help="clip length in --auto mode")
    ap.add_argument("--lead", type=float, default=8.0, help="countdown before the first clip (walk back)")
    ap.add_argument("--gap", type=float, default=3.0, help="countdown between clips")
    a = ap.parse_args()
    out = os.path.join(HERE, "data", "clips")
    os.makedirs(out, exist_ok=True)
    cam = Camera(a.source)
    n = run_auto(cam, BY_NAME[a.auto], a, out) if a.auto else run_keys(cam, a, out)
    print(f"{n} clips saved to {out}")


if __name__ == "__main__":
    main()
