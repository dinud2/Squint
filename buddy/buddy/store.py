"""People, medications and today's doses, in the shapes of docs/api-contract.md.

Kept in data/store.json (git-ignored: it is personal). Medication ids are the bottle
names the Tab5 recognises (tylenol, omega369, ...), person ids the enrolled faces.
"""
import json
import os
import re
import threading
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(HERE, "data", "store.json")
WINDOW_MIN = 120          # a dose is "due" until 2 h after its time, then "missed"

SEED = {
    "people": [
        {"id": "dinu", "name": "Dinu", "role": "elder", "photo_url": None},
        {"id": "kathy", "name": "Kathy", "role": "elder", "photo_url": None},
    ],
    "medications": [
        {"id": "tylenol", "name": "Tylenol", "strength": "500 mg", "for": "dinu", "times": ["08:00", "20:00"],
         "notes": "1 caplet", "risk": "normal"},
        {"id": "metformin", "name": "Metformin", "strength": "500 mg", "for": "dinu", "times": ["08:00"],
         "notes": "with food", "risk": "high"},
        {"id": "omega369", "name": "Omega 3-6-9", "strength": "1200 mg", "for": "kathy", "times": ["08:00"],
         "notes": "1 softgel", "risk": "normal"},
    ],
    "log": {},            # "YYYY-MM-DD" -> {"med|person|HH:mm": {"status", "at", "reason"}}
}


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower()) or "item"


def _hm(t):
    return time.strftime("%H:%M", time.localtime(t))


def _mins(hm):
    h, m = hm.split(":")
    return int(h) * 60 + int(m)


class Store:
    def __init__(self, path=STORE):
        self.path = path
        self.lock = threading.Lock()
        if os.path.exists(path):
            with open(path) as f:
                self.d = json.load(f)
        else:
            self.d = json.loads(json.dumps(SEED))
            self._save()

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.d, f, indent=1)
        os.replace(tmp, self.path)

    # ------------------------------------------------------------ people / medications (iOS API)
    def people(self):
        return list(self.d["people"])

    def person(self, pid):
        return next((p for p in self.d["people"] if p["id"] == pid), None)

    def name(self, pid):
        p = self.person(pid)
        return p["name"] if p else pid.capitalize()

    def add_person(self, p):
        with self.lock:
            p = {"role": "elder", "photo_url": None, **p}
            p["id"] = p.get("id") or self._new_id(_slug(p.get("name", "person")), self.d["people"])
            self.d["people"].append(p)
            self._save()
        return p

    def medications(self):
        return list(self.d["medications"])

    def med(self, mid):
        return next((m for m in self.d["medications"] if m["id"] == mid), None)

    def add_med(self, m):
        with self.lock:
            m = {"strength": "", "times": [], "notes": "", "risk": "normal", **m}
            m["id"] = m.get("id") or self._new_id(_slug(m.get("name", "med")), self.d["medications"])
            self.d["medications"].append(m)
            self._save()
        return m

    def put_med(self, mid, m):
        with self.lock:
            for i, old in enumerate(self.d["medications"]):
                if old["id"] == mid:
                    self.d["medications"][i] = {**old, **m, "id": mid}
                    self._save()
                    return self.d["medications"][i]
        return None

    def delete_med(self, mid):
        with self.lock:
            n = len(self.d["medications"])
            self.d["medications"] = [m for m in self.d["medications"] if m["id"] != mid]
            self._save()
            return len(self.d["medications"]) < n

    @staticmethod
    def _new_id(base, items):
        ids = {x["id"] for x in items}
        i, cand = 2, base
        while cand in ids:
            cand, i = f"{base}{i}", i + 1
        return cand

    # ------------------------------------------------------------ doses
    def today(self, now=None):
        """[Dose] for every scheduled dose today, oldest first."""
        now = now or time.time()
        day = time.strftime("%Y-%m-%d", time.localtime(now))
        nowm = _mins(_hm(now))
        log = self.d["log"].get(day, {})
        out = []
        for m in self.d["medications"]:
            for due in m.get("times", []):
                rec = log.get(f"{m['id']}|{m['for']}|{due}")
                if rec:
                    dose = {"med": m["id"], "for": m["for"], "due": due, **rec}
                else:
                    status = "due" if nowm <= _mins(due) + WINDOW_MIN else "missed"
                    dose = {"med": m["id"], "for": m["for"], "due": due, "status": status, "at": None, "reason": None}
                out.append(dose)
        return sorted(out, key=lambda d: (d["due"], d["for"], d["med"]))

    def open_doses(self, pid, now=None):
        """Doses this person still has to take today (due or missed, not yet taken)."""
        return [d for d in self.today(now) if d["for"] == pid and d["status"] in ("due", "missed")]

    def taken_today(self, mid, pid, now=None):
        return [d for d in self.today(now) if d["med"] == mid and d["for"] == pid and d["status"] in ("taken", "flagged")]

    def mark(self, mid, pid, status="taken", reason=None, now=None):
        """Mark the earliest open dose of this med for this person. -> the Dose, or None."""
        now = now or time.time()
        open_ = [d for d in self.open_doses(pid, now) if d["med"] == mid]
        if not open_:
            return None
        d = open_[0]
        day = time.strftime("%Y-%m-%d", time.localtime(now))
        with self.lock:
            self.d["log"].setdefault(day, {})[f"{mid}|{pid}|{d['due']}"] = {
                "status": status, "at": _hm(now), "reason": reason}
            self._save()
        return {**d, "status": status, "at": _hm(now), "reason": reason}
