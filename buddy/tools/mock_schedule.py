"""Demo schedule: one medicine per person due a few minutes from now, on the Pi's live store.

    python tools/mock_schedule.py              # Dinu: Tylenol, Kathy: Vitamin D at now+5 min, rounded up to :x0/:x5
    python tools/mock_schedule.py --restore    # put back the times saved before the last run

The other medicines move to 20:00 so they're "not yet". The Pi must run the real schedule
(squint_start.sh with SQUINT_DEMO= ), not --demo, which ignores dose times.
"""
import argparse
import json
import math
import os
import time
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP = os.path.join(HERE, "data", "schedule_backup.json")
NOW_MEDS = {"tylenol", "vitamind"}     # due at the demo time; everything else goes to LATER
LATER = "20:00"


def call(method, url, body=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read() or b"null")


def demo_time(lead_min=5, step=5):
    t = time.localtime(time.time() + lead_min * 60)
    m = math.ceil((t.tm_hour * 60 + t.tm_min + (1 if t.tm_sec else 0)) / step) * step
    return f"{m // 60 % 24:02d}:{m % 60:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pi", default="172.20.10.9")
    ap.add_argument("--restore", action="store_true")
    a = ap.parse_args()
    base = f"http://{a.pi}:8081"
    meds = call("GET", f"{base}/medications")
    if a.restore:
        saved = json.load(open(BACKUP))
        for mid, times in saved.items():
            call("PUT", f"{base}/medications/{mid}", {"times": times})
            print(f"{mid}: {times}")
        return
    if not os.path.exists(BACKUP):          # keep the first (real) schedule, not a previous mock
        os.makedirs(os.path.dirname(BACKUP), exist_ok=True)
        json.dump({m["id"]: m["times"] for m in meds}, open(BACKUP, "w"), indent=1)
    at = demo_time()
    for m in meds:
        times = [at] if m["id"] in NOW_MEDS else [LATER]
        call("PUT", f"{base}/medications/{m['id']}", {"times": times})
        print(f"{m['for']:>6}: {m['name']} at {times[0]}")
    print(f"demo dose time {at} (backup of the real times: {BACKUP})")


if __name__ == "__main__":
    main()
