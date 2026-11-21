"""Enrol a pill bottle from the bottle camera (the Brio on the Pi).

    python tools/enroll_bottle.py --name tylenol --reset
    python tools/enroll_bottle.py --name _other         # anything that is not a medicine

Hold the bottle up in front of the bottle camera, filling the middle of the picture, the way
it will be shown in use. After the countdown it takes --shots photos (the Pi uses its newest
camera frame each time); turn the bottle a little and move it slightly between shots. The
name must match the medication id (GET /medications).
For _other: show the empty view, your hand, your face, a cup, a water bottle (anything that
is NOT a medicine), a few shots each.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--api", default="http://172.20.10.9:8081")
    ap.add_argument("--shots", type=int, default=15)
    ap.add_argument("--every", type=float, default=0.8, help="seconds between shots")
    ap.add_argument("--reset", action="store_true", help="forget this bottle's old photos first")
    a = ap.parse_args()

    def post(path):
        req = urllib.request.Request(a.api + path, data=b"", method="POST")
        try:
            return json.loads(urllib.request.urlopen(req, timeout=30).read())
        except urllib.error.HTTPError as e:
            return json.loads(e.read())

    if a.reset:
        print(post(f"/bottles/reset?name={a.name}"))
    for i in range(5, 0, -1):
        print(f"hold {a.name} up to the camera... {i}", flush=True)
        time.sleep(1)
    ok = 0
    for i in range(a.shots):
        r = post(f"/bottles/enroll?name={a.name}")
        if "error" in r:
            print(f"  {i + 1:2d}/{a.shots}  {r['error']}", flush=True)
        else:
            ok += 1
            print(f"  {i + 1:2d}/{a.shots}  ok  box {r.get('box')}  ({r['photos']} photos total)", flush=True)
        time.sleep(a.every)
    print(f"{a.name}: {ok}/{a.shots} photos enrolled")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
