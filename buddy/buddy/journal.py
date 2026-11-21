"""The journal: one JSON line per thing that happened at the counter.

Append-only (data/journal.jsonl, git-ignored), so a power cut loses at most the line being
written. It is what routine tracking (insights.py, docs/decline-tracking.md) is built from.

Every line: {"t": epoch seconds, "day": "YYYY-MM-DD", "type": ..., "who": [person ids], ...}
  arrive         someone was recognised at the counter
  leave          they left; "stayed_s"
  bottle         picked up / held up their own medicine; "med"
  wrong_bottle   picked up someone else's medicine; "med", "owner"
  double_dose    picked up a medicine already taken today (the STOP); "med", "first_at"
  dose           a dose was confirmed; "med", "due", "at", "late_min", "since_arrival_s", "how"
  unsure         "Did you take it?" answered no, or never answered; "med", "reason"
  visit_no_dose  came while a dose was due and left without taking anything; "due" [med ids]
"""
import json
import os
import threading
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOURNAL = os.path.join(HERE, "data", "journal.jsonl")


class Journal:
    def __init__(self, path=JOURNAL):
        self.path = path
        self.lock = threading.Lock()

    def record(self, type_, who=(), t=None, **fields):
        t = t or time.time()
        line = {"t": round(t, 1), "day": time.strftime("%Y-%m-%d", time.localtime(t)), "type": type_,
                "who": list(who) if not isinstance(who, str) else [who], **fields}
        with self.lock:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "a") as f:
                f.write(json.dumps(line) + "\n")
        return line

    def read(self, since_day=None):
        """All lines (oldest first), optionally only from `since_day` ("YYYY-MM-DD") on."""
        if not os.path.exists(self.path):
            return []
        out = []
        with self.lock, open(self.path) as f:
            for raw in f:
                try:
                    ev = json.loads(raw)
                except ValueError:          # a half-written last line after a power cut
                    continue
                if since_day is None or ev.get("day", "") >= since_day:
                    out.append(ev)
        return out

    def rewrite(self, keep):
        """Keep only lines where keep(line) is true (used by tools/seed_history.py --clear)."""
        lines = [ev for ev in self.read() if keep(ev)]
        with self.lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                for ev in lines:
                    f.write(json.dumps(ev) + "\n")
            os.replace(tmp, self.path)
