"""The counter service: camera -> faces -> steady group -> events on the HTTP API.

    python3 -m buddy.service                                   # on the Pi (camera on localhost)
    python3 -m buddy.service --source http://<pi>:8080/stream  # on a laptop

API on port 8081 (people + Tab5 bottles): see buddy/api.py.
"""
import argparse
import time

from .api import Hub, serve
from .bottle_service import BottleService
from .camera import Camera
from .faces import FaceID
from .presence import Presence


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="http://localhost:8080/stream")
    ap.add_argument("--port", type=int, default=8081)
    ap.add_argument("--det-scale", type=float, default=0.5, help="detect faces on a smaller frame (faster)")
    ap.add_argument("--verbose", action="store_true", help="print every frame's result")
    ap.add_argument("--no-faces", action="store_true", help="bottle API only (no counter camera)")
    a = ap.parse_args()

    hub, presence = Hub(), Presence()
    bottles = BottleService(hub)
    serve(hub, a.port, bottles)
    print(f"[buddy] bottles {bottles.info()['bottles']}; API on :{a.port}", flush=True)
    if a.no_faces:
        while True:
            time.sleep(3600)
    fid = FaceID(det_scale=a.det_scale)
    print(f"[buddy] faces enrolled {sorted(fid.people)}", flush=True)
    cam = Camera(a.source)
    while True:
        try:
            t, frame = cam.read()
        except TimeoutError as e:
            print("[buddy] camera:", e, flush=True)
            continue
        hub.last_frame_t = t
        t0 = time.time()
        seen = fid.identify_all(frame)
        names = [n for _, n, _, _ in seen if n != "unknown"]
        unknown = sum(n == "unknown" for _, n, _, _ in seen)
        if a.verbose:
            print(f"[frame] {[(n, round(s, 2)) for _, n, s, _ in seen]} {1000 * (time.time() - t0):.0f} ms", flush=True)
        group = presence.update(t, names, unknown)
        if group is not None:
            hub.publish({"type": "people_present", "people": group, "unknown": unknown})


if __name__ == "__main__":
    main()
