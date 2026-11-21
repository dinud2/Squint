"""Write weeks of made-up history so the app's Trends tab has something to show (demos only).

    python tools/seed_history.py                    # 35 days; the first elder's routine slips lately
    python tools/seed_history.py --decline kathy    # choose who slips ("" = nobody)
    python tools/seed_history.py --clear            # remove everything this tool wrote

Stop buddy.service first: it keeps store.json in memory and would overwrite these days.
Everything written is marked "synthetic": true, so --clear removes exactly that and nothing real.
Today is never touched.
"""
import argparse
import datetime
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from buddy.journal import Journal  # noqa: E402
from buddy.store import Store  # noqa: E402


def at(day, hm, plus_min=0.0):
    h, m = map(int, hm.split(":"))
    return datetime.datetime.combine(day, datetime.time(h, m)).timestamp() + plus_min * 60


def hm(t):
    return datetime.datetime.fromtimestamp(t).strftime("%H:%M")


def clear(store, journal):
    n = 0
    for day, recs in store.d["log"].items():
        for k in [k for k, r in recs.items() if r.get("synthetic")]:
            del recs[k]
            n += 1
    store.d["log"] = {d: r for d, r in store.d["log"].items() if r}
    store._save()
    journal.rewrite(lambda ev: not ev.get("synthetic"))
    print(f"removed {n} synthetic doses and their journal lines")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=35)
    ap.add_argument("--decline", default=None, help="person id whose routine slips (default: first elder)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--clear", action="store_true")
    a = ap.parse_args()

    store, journal = Store(), Journal()
    if a.clear:
        return clear(store, journal)
    clear(store, journal)                     # start from real data only, so reruns don't pile up

    rnd = random.Random(a.seed)
    elders = [p["id"] for p in store.people() if p.get("role", "elder") == "elder"]
    slip = elders[0] if a.decline is None and elders else a.decline
    today = datetime.date.today()
    S = dict(synthetic=True)
    for back in range(a.days, 0, -1):
        day = today - datetime.timedelta(days=back)
        ds = day.isoformat()
        for pid in elders:
            # 0 = their usual; ramps to 1 over the last two weeks for the person who slips
            k = max(0.0, (14 - back) / 14) if pid == slip else 0.0
            meds = [m for m in store.medications() if m["for"] == pid and not (m.get("since") and ds < m["since"])]
            for due in sorted({t for m in meds for t in m.get("times", [])}):
                group = [m for m in meds if due in m.get("times", [])]
                late = rnd.gauss(6 + 70 * k, 7 + 20 * k)
                arrive = at(day, due, late)
                journal.record("arrive", pid, t=arrive, **S)
                took = False
                for m in group:
                    if rnd.random() < 0.03 + 0.25 * k:       # forgot this one
                        continue
                    finish = max(15.0, rnd.gauss(40 + 60 * k, 10 + 15 * k))
                    t = arrive + finish
                    if rnd.random() < 0.04 + 0.2 * k:         # "did you take it?" ... "no"
                        journal.record("unsure", pid, t=t, med=m["id"], reason="said_no", **S)
                    store.d["log"].setdefault(ds, {})[f"{m['id']}|{pid}|{due}"] = {
                        "status": "taken", "at": hm(t), "reason": None, **S}
                    journal.record("dose", pid, t=t, med=m["id"], due=due, at=hm(t), how="tab5",
                                   late_min=round((t - at(day, due)) / 60), since_arrival_s=round(finish), **S)
                    took = True
                    if rnd.random() < 0.01 + 0.3 * k:         # came back for it again later
                        journal.record("double_dose", pid, t=t + 3600, med=m["id"], first_at=hm(t), **S)
                if rnd.random() < 0.01 + 0.1 * k:             # picked up the partner's bottle
                    other = [m for m in store.medications() if m["for"] != pid]
                    if other:
                        journal.record("wrong_bottle", pid, t=arrive + 20, med=other[0]["id"],
                                       owner=other[0]["for"], **S)
                stayed = round(rnd.gauss(70 + 60 * k, 15))
                journal.record("leave", pid, t=arrive + stayed, stayed_s=stayed, **S)
                if not took:
                    journal.record("visit_no_dose", pid, t=arrive + stayed, due=[m["id"] for m in group], **S)
    store._save()
    print(f"seeded {a.days} days for {', '.join(elders)}; routine slipping lately: {slip or 'nobody'}")


if __name__ == "__main__":
    main()
