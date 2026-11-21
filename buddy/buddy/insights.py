"""Routine tracking: each person's last week against their own usual (docs/decline-tracking.md).

    insights(store, journal) -> {"generated", "people": [PersonInsight]}

Per person and day it works out the signals below from the dose log (store) and the journal.
"This week" is the 7 days before today (today is still going), "usual" is the 28 days before that.
A signal is `steady`, `watch` or `talk` depending on how far this week moved from usual in the
bad direction, against the floors in THRESHOLDS. It needs MIN_USUAL_DAYS of usual first
(`learning` until then). Steadiness (0-100) is 100 minus a penalty per signal that moved.

This notices change in a routine. It does not diagnose anything, and the app says so.
"""
import datetime
import statistics
import time

WEEK = 7
USUAL = 28
MIN_USUAL_DAYS = 7

# id: (title, unit, kind, watch, talk). kind: "rate" compares daily averages, "count" weekly totals.
# watch / talk: how far worse than usual this week must be (in the signal's unit).
THRESHOLDS = {
    "taken":         ("Doses taken", "%", "rate", 10, 20),           # percentage points lower
    "late":          ("Timing", "min late", "rate", 20, 45),         # minutes later
    "regularity":    ("Regularity", "min spread", "rate", 15, 30),   # spread of lateness, wider
    "double_dose":   ("Double-dose attempts", "a week", "count", 2, 3),  # one slip in a week is normal
    "wrong_bottle":  ("Mix-ups", "a week", "count", 2, 3),
    "unsure":        ("Unsure moments", "a week", "count", 2, 4),
    "visit_no_dose": ("Visits with nothing taken", "a week", "count", 2, 3),
    "finish":        ("Time to finish", "s", "rate", 30, 60),        # seconds slower
}
PENALTY = {"steady": 0, "watch": 8, "talk": 20}
HIGHER_IS_WORSE = {"late", "regularity", "double_dose", "wrong_bottle", "unsure", "visit_no_dose", "finish"}


def _mins(hm):
    h, m = hm.split(":")
    return int(h) * 60 + int(m)


def _median(xs):
    return statistics.median(xs) if xs else None


def daily(store, journal, days, now=None):
    """{person: [{"date", "scheduled", "taken", "late_min", "double_dose", ...}]} oldest first."""
    now = now or time.time()
    hist = store.history(days, now)
    events = journal.read(since_day=hist[0]["date"]) if hist else []
    elders = [p["id"] for p in store.people() if p.get("role", "elder") == "elder"]
    out = {pid: [] for pid in elders}
    for h in hist:
        day = h["date"]
        evs = [e for e in events if e.get("day") == day and len(e.get("who", [])) == 1]  # skip two-person events
        for pid in elders:
            doses = [d for d in h["doses"] if d["for"] == pid]
            done = [d for d in doses if d["status"] in ("taken", "flagged") and d.get("at")]
            mine = [e for e in evs if e["who"][0] == pid]
            finish = [e["since_arrival_s"] for e in mine if e["type"] == "dose" and e.get("since_arrival_s") is not None]
            out[pid].append({
                "date": day,
                "scheduled": len(doses),
                "taken": len(done),
                "late_min": _median([_mins(d["at"]) - _mins(d["due"]) for d in done]),
                "double_dose": sum(e["type"] == "double_dose" for e in mine),
                "wrong_bottle": sum(e["type"] == "wrong_bottle" for e in mine),
                "unsure": sum(e["type"] == "unsure" for e in mine),
                "visit_no_dose": sum(e["type"] == "visit_no_dose" for e in mine),
                "finish_s": _median(finish),
            })
    return out


def _signal_values(days):
    """Values for each signal over a run of days (None when there is no data)."""
    sched = sum(d["scheduled"] for d in days)
    lates = [d["late_min"] for d in days if d["late_min"] is not None]
    finishes = [d["finish_s"] for d in days if d["finish_s"] is not None]
    weeks = max(len(days), 1) / WEEK
    return {
        "taken": 100.0 * sum(d["taken"] for d in days) / sched if sched else None,
        "late": statistics.mean(lates) if lates else None,
        "regularity": statistics.pstdev(lates) if len(lates) >= 3 else None,
        "double_dose": sum(d["double_dose"] for d in days) / weeks,
        "wrong_bottle": sum(d["wrong_bottle"] for d in days) / weeks,
        "unsure": sum(d["unsure"] for d in days) / weeks,
        "visit_no_dose": sum(d["visit_no_dose"] for d in days) / weeks,
        "finish": statistics.mean(finishes) if finishes else None,
    }


def _level(sid, recent, usual):
    if recent is None or usual is None:
        return "steady", 0.0
    worse = (recent - usual) if sid in HIGHER_IS_WORSE else (usual - recent)
    _, _, _, watch, talk = THRESHOLDS[sid]
    return ("talk" if worse >= talk else "watch" if worse >= watch else "steady"), worse


def _sentence(name, partner, sid, recent, usual):
    r, u = round(recent or 0), round(usual or 0)
    return {
        "taken": f"{name} took {r}% of doses this week, down from {u}% usually.",
        "late": f"{name}'s doses are coming about {r - u} min later than usual this week.",
        "regularity": f"{name}'s pill times have been less regular this week than usual.",
        "double_dose": f"{name} tried to take a medicine a second time {r}× this week (usually {u}).",
        "wrong_bottle": f"{name} picked up {partner or 'someone else'}'s pills {r}× this week (usually {u}).",
        "unsure": f"{name} wasn't sure whether they'd taken a dose {r}× this week (usually {u}).",
        "visit_no_dose": f"{name} came to the counter and left without their pills {r}× this week.",
        "finish": f"{name} is taking about {r - u} s longer than usual to get through a dose.",
    }[sid]


def insights(store, journal, days=35, now=None):
    now = now or time.time()
    per = daily(store, journal, max(days, WEEK + USUAL + 1), now)
    people = {p["id"]: p for p in store.people()}
    out = []
    for pid, series in per.items():
        name = people.get(pid, {}).get("name", pid.capitalize())
        partner = next((people[o]["name"] for o in per if o != pid and o in people), None)
        past = series[:-1]                                   # today is still going
        recent, usual = past[-WEEK:], past[-(WEEK + USUAL):-WEEK]
        usual = [d for d in usual if d["scheduled"]]
        have = len([d for d in past if d["scheduled"]])
        learning = len(usual) < MIN_USUAL_DAYS
        rv, uv = _signal_values(recent), _signal_values(usual)
        signals = []
        for sid, (title, unit, kind, _, _) in THRESHOLDS.items():
            lvl, worse = ("steady", 0.0) if learning else _level(sid, rv[sid], uv[sid])
            signals.append({
                "id": sid, "title": title, "unit": unit,
                "recent": None if rv[sid] is None else round(rv[sid], 1),
                "usual": None if uv[sid] is None else round(uv[sid], 1),
                "level": lvl, "worse_by": round(worse, 1),
                "higher_is_worse": sid in HIGHER_IS_WORSE,
            })
        moved = sorted([s for s in signals if s["level"] != "steady"],
                       key=lambda s: (s["level"] != "talk", -s["worse_by"] / THRESHOLDS[s["id"]][4]))
        if learning:
            headline = f"Squint is still learning {name}'s routine ({min(have, MIN_USUAL_DAYS + WEEK)} of {MIN_USUAL_DAYS + WEEK} days)."
            level = "learning"
        elif moved:
            s = moved[0]
            headline = _sentence(name, partner, s["id"], s["recent"], s["usual"])
            level = s["level"]
        else:
            headline = f"{name}'s routine looks like usual."
            level = "steady"
        steadiness = None if learning else max(0, 100 - sum(PENALTY[s["level"]] for s in signals))
        out.append({
            "person": pid, "name": name, "days_of_data": have, "learning": learning,
            "steadiness": steadiness, "level": level, "headline": headline, "signals": signals,
            "daily": series[-days:],
        })
    return {"generated": datetime.datetime.fromtimestamp(now).isoformat(timespec="seconds"), "people": out}
