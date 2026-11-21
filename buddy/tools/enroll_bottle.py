"""Enrol a pill bottle from the counter camera (the Logitech pointing down).

    python tools/enroll_bottle.py --name tylenol
    python tools/enroll_bottle.py --name _other      # cups, water bottles, hands, the empty counter

Put the bottle on the counter under the camera. After the countdown it takes --shots photos
(the Pi uses its newest camera frame each time); move the bottle around a little and turn it
between shots so it learns several positions and sides. The name must match the medication id
(GET /medications).
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
        print(f"put {a.name} under the camera... {i}", flush=True)
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
