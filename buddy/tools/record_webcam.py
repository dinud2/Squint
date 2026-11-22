"""Record the Pi's webcam (Logitech C270) for the demo video: clean footage, nothing drawn on it.

    python tools/record_webcam.py                    # Pi at 172.20.10.9, takes in ~/Videos/squint
    python tools/record_webcam.py --out ~/Desktop/takes --fps 30

A preview window opens. r = start / stop a take (each take is a new file), q = quit (a take
in progress is finished properly). The red REC dot is on the preview only, never in the file.

Every take writes two files with the same name:
  take_<date-time>.mp4     every frame the camera sent, H.264, constant frame rate (--fps), real
                           timing (frames are timestamped on arrival, ffmpeg fills / drops to keep
                           the clock), so it lines up with other footage in the editor
  take_<date-time>.jsonl   what Squint recognised during the take, one JSON object per line, "t" =
                           seconds from the start of the video: the Pi's events (people_present,
                           bottle_shown, say, intake, dose_taken), and 5x a second the bottle box /
                           label and who is at the counter. Enough to draw overlays afterwards,
                           in sync, in any style.

The stream is read separately from Squint's own loops (camstream serves several clients), so
recording does not slow the Pi's recognition. Needs ffmpeg on the laptop.
"""
import argparse
import json
import os
import queue
import subprocess
import threading
import time
import urllib.request

import cv2
import numpy as np


class Stream:
    """Every JPEG from the MJPEG stream, in order (not only the newest: a video wants them all)."""

    def __init__(self, url):
        self.url = url
        self.latest = None                    # newest (t, jpg) for the preview
        self.sinks = []                       # callables(t, jpg) that get every frame
        self.lock = threading.Lock()
        self.error = None
        self.stopped = False
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while not self.stopped:
            try:
                with urllib.request.urlopen(self.url, timeout=5) as r:
                    buf = b""
                    while not self.stopped:
                        chunk = r.read1(65536)
                        if not chunk:
                            break
                        buf += chunk
                        while True:
                            s = buf.find(b"\xff\xd8")
                            e = buf.find(b"\xff\xd9", s + 2) if s >= 0 else -1
                            if s < 0 or e < 0:
                                if s > 0:
                                    buf = buf[s:]
                                break
                            jpg, buf = buf[s:e + 2], buf[e + 2:]
                            t = time.time()
                            with self.lock:
                                self.latest = (t, jpg)
                                sinks = list(self.sinks)
                            for f in sinks:
                                f(t, jpg)
                            self.error = None
            except Exception as ex:           # Pi restarting, Wi-Fi blip: keep trying
                self.error = str(ex)
                time.sleep(0.5)


class Take:
    """One recording: ffmpeg for the video, a thread for Squint's data."""

    def __init__(self, stream, pi, out_dir, fps):
        os.makedirs(out_dir, exist_ok=True)
        self.base = os.path.join(out_dir, "take_" + time.strftime("%Y%m%d-%H%M%S"))
        self.t0 = time.time()
        self.frames = 0
        self.pi = pi
        self.stopped = False
        self.q = queue.Queue(maxsize=600)     # ~30 s of frames if ffmpeg ever stalls
        self.ff = subprocess.Popen(
            ["ffmpeg", "-loglevel", "error", "-y",
             "-f", "image2pipe", "-c:v", "mjpeg", "-use_wallclock_as_timestamps", "1", "-i", "-",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p",
             "-r", str(fps), "-movflags", "+faststart", self.base + ".mp4"],
            stdin=subprocess.PIPE)
        self.data = open(self.base + ".jsonl", "w")
        self.data_lock = threading.Lock()
        self.note({"type": "take", "file": os.path.basename(self.base) + ".mp4", "pi": pi,
                   "started": time.strftime("%Y-%m-%d %H:%M:%S")})
        threading.Thread(target=self._write, daemon=True).start()
        threading.Thread(target=self._events, daemon=True).start()
        threading.Thread(target=self._poll, daemon=True).start()
        stream.sinks.append(self.frame)
        self.stream = stream

    def frame(self, t, jpg):
        if not self.stopped:
            try:
                self.q.put_nowait(jpg)
            except queue.Full:
                pass

    def _write(self):
        while True:
            jpg = self.q.get()
            if jpg is None:
                break
            try:
                self.ff.stdin.write(jpg)
                self.frames += 1
            except (BrokenPipeError, ValueError):
                break

    def note(self, obj):
        with self.data_lock:
            if not self.data.closed:
                self.data.write(json.dumps({"t": round(time.time() - self.t0, 3), **obj}) + "\n")
                self.data.flush()

    def _events(self):
        """The Pi's event stream (SSE): every event, as it happens."""
        try:
            with urllib.request.urlopen(f"http://{self.pi}:8081/events", timeout=10) as r:
                for raw in r:
                    if self.stopped:
                        break
                    line = raw.decode("utf-8", "replace").strip()
                    if line.startswith("data:"):
                        try:
                            ev = json.loads(line[5:])
                        except ValueError:
                            continue
                        ev.pop("time", None)
                        self.note({"event": ev})
        except Exception as e:
            self.note({"type": "events_lost", "error": str(e)})

    def _poll(self):
        """5x a second: the bottle box / label and who is at the counter (for drawing overlays)."""
        last = None
        while not self.stopped:
            try:
                b = json.load(urllib.request.urlopen(f"http://{self.pi}:8081/bottles/last", timeout=2))
                d = json.load(urllib.request.urlopen(f"http://{self.pi}:8081/doses/pending", timeout=2))
                snap = {"type": "state", "bottle": b.get("name"), "score": b.get("score"),
                        "box": b.get("box"), "unsure": b.get("unsure"), "unsure_box": b.get("unsure_box"),
                        "at_counter": d.get("at_counter"), "unknown": d.get("unknown"),
                        "pending": d.get("pending")}
                if snap != last:              # only changes: the file stays small
                    self.note(snap)
                    last = snap
            except Exception:
                pass
            time.sleep(0.2)

    def stop(self):
        self.stopped = True
        try:
            self.stream.sinks.remove(self.frame)
        except ValueError:
            pass
        self.q.put(None)
        time.sleep(0.3)
        try:
            self.ff.stdin.close()
        except Exception:
            pass
        self.ff.wait(timeout=30)
        self.note({"type": "end", "frames": self.frames})
        with self.data_lock:
            self.data.close()
        return self.base + ".mp4", self.frames, time.time() - self.t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pi", default="172.20.10.9")
    ap.add_argument("--stream", help="default http://<pi>:8080/stream (the C270, 960x544)")
    ap.add_argument("--out", default=os.path.expanduser("~/Videos/squint"))
    ap.add_argument("--fps", type=int, default=30, help="frame rate of the saved video (constant)")
    a = ap.parse_args()
    stream = Stream(a.stream or f"http://{a.pi}:8080/stream")
    win = "Squint webcam recorder  (r = record / stop, q = quit)"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, 960, 544)
    take = None
    last_shown = None
    print(f"recording to {a.out}; r = start / stop a take, q = quit", flush=True)
    while True:
        with stream.lock:
            latest = stream.latest
        if latest and (latest is not last_shown):
            last_shown = latest
            view = cv2.imdecode(np.frombuffer(latest[1], np.uint8), cv2.IMREAD_COLOR)
        elif not latest:
            view = np.zeros((544, 960, 3), np.uint8)
            cv2.putText(view, f"Waiting for the camera... {stream.error or ''}"[:80], (20, 280),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (80, 80, 230), 2)
        else:
            view = None                       # no new frame: keep the window as it is
        if view is not None:
            if take:                          # preview only: the file stays clean
                cv2.circle(view, (30, 30), 12, (40, 40, 230), -1)
                cv2.putText(view, f"REC {time.time() - take.t0:5.1f}s  {take.frames} frames", (52, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            elif stream.error and latest:
                cv2.putText(view, "camera stream lost - retrying", (20, 40), cv2.FONT_HERSHEY_SIMPLEX,
                            0.8, (80, 80, 230), 2)
            cv2.imshow(win, view)
        k = cv2.waitKey(15) & 0xFF
        if k == ord("r"):
            if take is None:
                take = Take(stream, a.pi, a.out, a.fps)
                print(f"REC  {take.base}.mp4", flush=True)
            else:
                path, n, secs = take.stop()
                print(f"saved {path}  ({n} frames, {secs:.1f} s, ~{n / max(secs, 0.1):.1f} fps from the camera)", flush=True)
                take = None
        elif k == ord("q"):
            if take is not None:
                path, n, secs = take.stop()
                print(f"saved {path}  ({n} frames, {secs:.1f} s)", flush=True)
            break
    stream.stopped = True
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
