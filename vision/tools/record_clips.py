"""C5: record labelled intake / look-alike clips at the station (Sat 11:00 session).

    python tools/record_clips.py --who ved

Keys: pick the movement first, then SPACE to start / stop recording. q quits.
  1 bottle to mouth      2 pill from palm to mouth   3 drink water
  4 nose scratch         5 read the label (bottle)   6 chin / face touch
  7 put bottle down / pick up                         8 other (wave, reach, idle)
Each clip -> data/clips/<kind>_<who>_<n>.mp4 + .json {kind, label, armed}
"""
import argparse
import json
import os
import time

import cv2

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KINDS = {ord("1"): ("bottle_to_mouth", 1, True), ord("2"): ("palm_to_mouth", 1, True),
         ord("3"): ("drink_water", 0, False), ord("4"): ("nose_scratch", 0, False),
         ord("5"): ("read_label", 0, True), ord("6"): ("chin_touch", 0, False),
         ord("7"): ("put_down_pick_up", 0, True), ord("8"): ("other", 0, False)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--who", required=True)
    ap.add_argument("--source", default="0")
    a = ap.parse_args()
    out = os.path.join(HERE, "data", "clips")
    os.makedirs(out, exist_ok=True)
    cap = cv2.VideoCapture(int(a.source) if a.source.isdigit() else a.source)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    kind, writer, n = KINDS[ord("1")], None, 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if writer is not None:
            writer.write(frame)
        show = frame.copy()
        cv2.putText(show, f"{kind[0]}  {'REC' if writer else 'ready'}  ({n} saved)", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255) if writer else (0, 255, 0), 2)
        cv2.imshow("record", show)
        k = cv2.waitKey(1) & 0xFF
        if k in KINDS and writer is None:
            kind = KINDS[k]
        elif k == ord(" "):
            if writer is None:
                stem = os.path.join(out, f"{kind[0]}_{a.who}_{int(time.time())}")
                writer = cv2.VideoWriter(stem + ".mp4", cv2.VideoWriter_fourcc(*"mp4v"), 15, (frame.shape[1], frame.shape[0]))
            else:
                writer.release(); writer = None; n += 1
                with open(stem + ".json", "w") as f:
                    json.dump({"kind": kind[0], "label": kind[1], "armed": kind[2], "who": a.who}, f)
        elif k == ord("q"):
            break


if __name__ == "__main__":
    main()
