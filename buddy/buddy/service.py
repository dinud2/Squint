"""The Squint service: cameras -> faces + bottles -> coordinator -> events on the HTTP API.

    python3 -m buddy.service                       # on the Pi: bottles from the Logitech (localhost)
    python3 -m buddy.service --face-source http://<laptop>:8090/stream   # faces from another camera

Camera layout (medicine-buddy design):
  * Logitech C270 on the Pi, pointing DOWN at the counter -> bottle detection (--bottle-source)
  * Tab5 front camera, ~20 degrees UP at the person      -> faces (--face-source, once the
    Tab5 camera streams; until then any MJPEG camera works, e.g. a laptop webcam)

API on port 8081: see buddy/api.py.
"""
import argparse
import threading
import time

from .api import Hub, serve
from .bottle_service import BottleService
from .camera import Camera
from .coordinator import Coordinator
from .faces import FaceID
from .journal import Journal
from .presence import Presence
from .store import Store


class Frames:
    """A camera that never ends the loop that reads it: a lost stream, a JPEG that won't decode,
    a webcam hiccup or the end of a test clip just mean "no frame yet". A clip starts over."""

    def __init__(self, src, label):
        self.src, self.label = src, label
        self.cam = Camera(src)
        self.is_file = not src.startswith(("http://", "https://")) and not src.isdigit()

    def read(self):
        """-> (timestamp, BGR frame), blocking until there is one."""
        while True:
            try:
                t, frame = self.cam.read()
            except TimeoutError as e:
                print(f"[buddy] {self.label} camera:", e, flush=True)
                continue
            if frame is not None and frame.size:
                return t, frame
            if self.is_file:                                     # end of the clip: play it again
                self.cam.close()
                self.cam = Camera(self.src)
            time.sleep(0.05)


def face_loop(src, hub, det_scale, verbose):
    presence = Presence()
    fid = FaceID(det_scale=det_scale)
    print(f"[buddy] faces from {src}, enrolled {sorted(fid.people)}", flush=True)
    hub.diag.faces["source"] = src
    cam = Frames(src, "face")
    while True:
        t, frame = cam.read()
        hub.last_frame_t = t
        t0 = time.time()
        try:
            seen = fid.identify_all(frame)
        except Exception as e:                  # one bad frame must not stop Squint seeing people
            print("[buddy] face frame skipped:", e, flush=True)
            hub.diag.error("face", e)
            continue
        hub.diag.faces["enrolled"] = sorted(fid.people)
        hub.diag.face_frame(t, frame.shape, fid.last_raw, len(seen), seen)
        names = [n for _, n, _, _ in seen if n != "unknown"]
        unknown = sum(n == "unknown" for _, n, _, _ in seen)
        if verbose:
            print(f"[faces] {[(n, round(s, 2)) for _, n, s, _ in seen]} {1000 * (time.time() - t0):.0f} ms", flush=True)
        group = presence.update(t, names, unknown)
        if group is not None:
            hub.publish({"type": "people_present", "people": group, "unknown": unknown})


def bottle_loop(src, hub, bottles, fps, verbose):
    print(f"[buddy] bottles from {src} at {fps} fps, enrolled {sorted(bottles.info()['bottles'])}", flush=True)
    hub.diag.bottles.update(source=src, mode=bottles.mode)
    cam = Frames(src, "bottle")
    period = 1.0 / fps
    while True:
        t0 = time.time()
        t, frame = cam.read()                   # always the newest frame
        hub.last_frame_t = t
        try:
            r = bottles.frame_image(frame)
        except Exception as e:
            print("[buddy] bottle frame skipped:", e, flush=True)
            hub.diag.error("bottle", e)
            continue
        hub.diag.bottles["enrolled"] = sorted(bottles.info()["bottles"])
        hub.diag.bottle_frame(t, r)
        if verbose:
            print(f"[bottles] {[(b['name'], b['score']) for b in r['bottles']]} on counter {r['on_counter']} "
                  f"{r['ms']} ms", flush=True)
        time.sleep(max(0.0, period - (time.time() - t0)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bottle-source", default="http://localhost:8080/stream",
                    help="camera looking down at the counter ('' = only frames POSTed to /tab5/frame)")
    ap.add_argument("--bottle-fps", type=float, default=4.0)
    ap.add_argument("--bottle-mode", choices=("show", "counter"), default="show",
                    help="show: bottle held up to the camera; counter: bottles stand under it")
    ap.add_argument("--face-source", default="", help="camera looking at the person ('' = off)")
    ap.add_argument("--port", type=int, default=8081)
    ap.add_argument("--det-scale", type=float, default=0.5, help="detect faces on a smaller frame (faster)")
    ap.add_argument("--verbose", action="store_true", help="print every frame's result")
    ap.add_argument("--announce", default=None,
                    help="Nest voice endpoint, e.g. http://<laptop>:8765/announce (home/server.py)")
    a = ap.parse_args()

    hub = Hub()
    bottles = BottleService(hub, a.bottle_mode)
    hub.diag.voice["url"] = a.announce
    coord = Coordinator(hub, Store(), a.announce, journal=Journal())
    serve(hub, a.port, bottles, coord)
    print(f"[buddy] API on :{a.port}", flush=True)
    loops = []
    if a.bottle_source:
        loops.append(threading.Thread(target=bottle_loop, daemon=True,
                                      args=(a.bottle_source, hub, bottles, a.bottle_fps, a.verbose)))
    if a.face_source:
        loops.append(threading.Thread(target=face_loop, daemon=True,
                                      args=(a.face_source, hub, a.det_scale, a.verbose)))
    for th in loops:
        th.start()
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
