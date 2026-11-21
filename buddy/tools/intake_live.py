"""Live window for the hand-to-mouth check: what the camera sees and what the Pi decides.

    python tools/intake_live.py                     # Pi at 172.20.10.9

Draws (computed on the laptop, same models as the Pi): the face, the mouth point (red), palm
boxes (blue; green when "at the mouth"). Shows the Pi's own state: which dose is waiting for
"Did you take it?" (after a bottle is shown) and its live events (bottle_shown, intake + its
confidence, dose_taken, say). Try: hold up your bottle, then bring your palm to your mouth.
q quits.
"""
import argparse
import json
import os
import sys
import threading
import time
import urllib.request

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from buddy.camera import Camera  # noqa: E402
from buddy.faces import FaceID  # noqa: E402
from buddy.intake import MODEL, NEAR, box_distance, mouth_of  # noqa: E402
from buddy.palmdet import MPPalmDet  # noqa: E402

GREEN, BLUE, RED, WHITE, GREY, AMBER = (80, 200, 80), (255, 160, 60), (60, 60, 230), (255, 255, 255), (150, 150, 150), (39, 159, 239)


class PiState:
    def __init__(self, host):
        self.api = f"http://{host}:8081"
        self.pending = None
        self.events = []
        self.error = None
        threading.Thread(target=self._poll, daemon=True).start()
        threading.Thread(target=self._events, daemon=True).start()

    def _poll(self):
        while True:
            try:
                self.pending = json.loads(urllib.request.urlopen(self.api + "/doses/pending", timeout=3).read()).get("pending")
                self.error = None
            except Exception as e:
                self.error = str(e)
            time.sleep(0.4)

    def _events(self):
        while True:
            try:
                with urllib.request.urlopen(self.api + "/events", timeout=60) as r:
                    for raw in r:
                        line = raw.decode("utf-8", "ignore").strip()
                        if not line.startswith("data:"):
                            continue
                        ev = json.loads(line[5:])
                        t = ev.get("type")
                        if t == "bottle_shown":
                            txt = f"bottle shown: {ev['bottle']} ({ev.get('score', 0):.2f})"
                        elif t == "intake":
                            txt = f"HAND TO MOUTH: {ev.get('person')} confidence {ev.get('confidence')} ({ev.get('frames')} frames)"
                        elif t == "dose_taken":
                            txt = f"DOSE TAKEN: {ev['med']} for {ev['for']} ({ev.get('how')})"
                        elif t == "say":
                            txt = f'say: "{ev["text"]}"'
                        elif t == "people_present":
                            txt = f"people: {', '.join(ev['people']) or 'nobody'}"
                        else:
                            continue
                        self.events = (self.events + [(time.strftime("%H:%M:%S"), txt)])[-7:]
            except Exception:
                time.sleep(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pi", default="172.20.10.9")
    ap.add_argument("--faces", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "faces"),
                    help="face gallery folder (for names)")
    a = ap.parse_args()
    pi = PiState(a.pi)
    fid, palms = FaceID(gallery_dir=a.faces, det_scale=0.5), MPPalmDet(MODEL, scoreThreshold=0.5)
    cam = Camera(f"http://{a.pi}:8080/stream")
    last_mouth = None
    while True:
        try:
            t, frame = cam.read()
        except TimeoutError:
            if (cv2.waitKey(300) & 0xFF) == ord("q"):
                break
            continue
        seen = fid.identify_all(frame)
        for face, name, score, _ in seen:
            x, y, w, h = face[:4].astype(int)
            cv2.rectangle(frame, (x, y), (x + w, y + h), GREY, 2)
            cv2.putText(frame, f"{name} {score:.2f}", (x, max(20, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, GREY, 2)
            m, fw = mouth_of(face)
            last_mouth = (m, fw, t)
        mouth = last_mouth if last_mouth and t - last_mouth[2] < 1.2 else None
        if mouth:
            cv2.circle(frame, (int(mouth[0][0]), int(mouth[0][1])), 7, RED, -1)
            cv2.circle(frame, (int(mouth[0][0]), int(mouth[0][1])), int(NEAR * mouth[1]), RED, 1)
        at_mouth = False
        for p in palms.infer(frame):
            x1, y1, x2, y2 = p[:4].astype(int)
            near = mouth is not None and box_distance(p[:4], mouth[0]) <= NEAR * mouth[1]
            at_mouth |= near
            cv2.rectangle(frame, (x1, y1), (x2, y2), GREEN if near else BLUE, 3)
            cv2.putText(frame, f"palm {p[-1]:.2f}", (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        GREEN if near else BLUE, 2)
        # banner: the Pi's state
        h, w = frame.shape[:2]
        canvas = cv2.copyMakeBorder(frame, 0, 230, 0, 0, cv2.BORDER_CONSTANT, value=(20, 20, 20))
        if pi.error:
            line, col = f"Pi not reachable: {pi.error[:60]}", RED
        elif pi.pending:
            line, col = f"Pi is waiting for 'Did you take it?': {pi.pending['name']} ({pi.pending['for']})  -> bring your palm to your mouth", AMBER
        else:
            line, col = "No dose waiting. Hold your bottle up to the camera first.", WHITE
        cv2.putText(canvas, line, (12, h + 32), cv2.FONT_HERSHEY_SIMPLEX, 0.65, col, 2)
        cv2.putText(canvas, "AT MOUTH" if at_mouth else "", (w - 170, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, GREEN, 3)
        for i, (ts, txt) in enumerate(reversed(pi.events)):
            cv2.putText(canvas, f"{ts}  {txt}"[:110], (12, h + 66 + 24 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                        GREEN if ("TAKEN" in txt or "HAND" in txt) else WHITE, 1)
        cv2.imshow("squint hand-to-mouth", canvas)
        if (cv2.waitKey(1) & 0xFF) == ord("q"):
            break
    cam.close()


if __name__ == "__main__":
    main()
