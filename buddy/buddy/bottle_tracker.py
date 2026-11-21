"""Which bottle was picked up? Bottles stand on the counter in front of the Tab5 camera.

Per enrolled bottle we keep whether it is steadily on the counter and where. A bottle
that was steady (seen for STEADY_S) is "picked up" when it

  * disappears for MISSING_S (lifted out of view or hidden in a hand), or
  * rises by LIFT_FRAC of the frame height (lifted in view).

It is "put back" when it is steady again near the bottom of where it was. Unknown
objects are ignored here: they are never reported as a medicine.
"""


class BottleTracker:
    STEADY_S = 1.5
    MISSING_S = 0.7
    LIFT_FRAC = 0.12

    def __init__(self):
        self.st = {}   # name -> {"first": t, "last": t, "box": (x1,y1,x2,y2), "rest_y": y, "steady": bool, "picked": bool}

    def update(self, t, seen, frame_h):
        """seen: list of (name, score, box) for this frame (enrolled names only).
        -> list of events: {"type": "bottle_picked"|"bottle_returned", "bottle": name, "how": ...}"""
        events = []
        now = {}
        for name, score, box in seen:          # one box per name: the most confident
            if name not in now or score > now[name][0]:
                now[name] = (score, box)
        for name, (score, box) in now.items():
            s = self.st.get(name)
            cy = (box[1] + box[3]) / 2
            if s is None or t - s["last"] > 3.0:
                s = self.st[name] = {"first": t, "last": t, "box": box, "rest_y": cy, "steady": False, "picked": False}
            s["last"], s["box"] = t, box
            if not s["steady"] and t - s["first"] >= self.STEADY_S:
                s["steady"], s["rest_y"] = True, cy
                if s["picked"]:
                    s["picked"] = False
                    events.append({"type": "bottle_returned", "bottle": name})
            if s["steady"] and not s["picked"]:
                if s["rest_y"] - cy > self.LIFT_FRAC * frame_h:
                    s["picked"], s["steady"], s["first"] = True, False, t
                    events.append({"type": "bottle_picked", "bottle": name, "how": "lifted", "score": round(score, 3)})
                else:
                    s["rest_y"] = 0.9 * s["rest_y"] + 0.1 * cy        # follow small nudges
        for name, s in self.st.items():
            if name in now:
                continue
            if s["steady"] and not s["picked"] and t - s["last"] >= self.MISSING_S:
                s["picked"], s["steady"] = True, False
                events.append({"type": "bottle_picked", "bottle": name, "how": "gone"})
            if not s["steady"] and t - s["last"] > 0.3:
                s["first"] = t                  # a new steady streak starts when it is seen again
        return events

    def on_counter(self):
        return sorted(n for n, s in self.st.items() if s["steady"])
