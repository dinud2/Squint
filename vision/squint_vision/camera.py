"""Frame sources.

  "0", "1"...                webcam (laptop)
  http://<pi>:8080/stream    Dinu's QNX camstream (pi/camstream.c), MJPEG over HTTP
  path/to/clip.mp4           recorded clip, replayed on its own clock
  qnx                        a Python module exposing get_frame() (if B ships one)

For MJPEG we don't use cv2.VideoCapture: its FFmpeg reader buffers several
frames, which adds latency on the STOP path. MjpegCamera reads the stream in a
thread and keeps only the newest JPEG, so a slow consumer drops frames
instead of falling behind.
"""
import importlib
import os
import threading
import time
import urllib.request

import cv2
import numpy as np


class MjpegCamera:
    def __init__(self, url, timeout=5.0):
        self.url = url
        self.timeout = timeout
        self.latest = None          # (arrival_time, jpeg_bytes, seq)
        self.seq = 0
        self.last_read_seq = -1
        self.cond = threading.Condition()
        self.error = None
        self.stopped = False
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        while not self.stopped:
            try:
                with urllib.request.urlopen(self.url, timeout=self.timeout) as r:
                    buf = b""
                    while not self.stopped:
                        # read1 returns as soon as ANY bytes arrive; read(n) would wait for n bytes
                        # and hold a ~9 KB frame until the next one came (half fps, +1 frame of lag)
                        chunk = r.read1(16384)
                        if not chunk:
                            break
                        buf += chunk
                        # a JPEG is everything from FFD8 to FFD9; take the newest complete one
                        while True:
                            s = buf.find(b"\xff\xd8")
                            e = buf.find(b"\xff\xd9", s + 2) if s >= 0 else -1
                            if s < 0 or e < 0:
                                if s > 0:
                                    buf = buf[s:]
                                break
                            jpg, buf = buf[s:e + 2], buf[e + 2:]
                            with self.cond:
                                self.seq += 1
                                self.latest = (time.time(), jpg, self.seq)
                                self.cond.notify_all()
            except Exception as ex:   # camera restarted, Wi-Fi blip: retry
                self.error = str(ex)
                time.sleep(0.5)

    def read(self):
        """Block until a frame newer than the last one returned. -> (t, BGR frame)."""
        with self.cond:
            ok = self.cond.wait_for(lambda: self.latest is not None and self.latest[2] != self.last_read_seq,
                                    timeout=self.timeout)
            if not ok:
                raise TimeoutError(f"no frames from {self.url} ({self.error or 'timeout'})")
            t, jpg, seq = self.latest
            self.last_read_seq = seq
        frame = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
        return t, frame

    def dropped(self):
        return self.seq

    def close(self):
        self.stopped = True


class Camera:
    def __init__(self, source="0"):
        self.b = self.mjpeg = self.cap = None
        self.is_file = False
        if source == "qnx":
            self.b = importlib.import_module(os.environ.get("SQUINT_CAMERA_MODULE", "camera"))
        elif source.startswith(("http://", "https://")):
            self.mjpeg = MjpegCamera(source)
        else:
            self.cap = cv2.VideoCapture(int(source) if source.isdigit() else source)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.is_file = not source.isdigit()
            self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 15
            self.t_file = 0.0

    def read(self):
        """-> (timestamp_s, frame) or (None, None) at the end of a file."""
        if self.b is not None:
            return time.time(), self.b.get_frame()
        if self.mjpeg is not None:
            return self.mjpeg.read()
        ok, frame = self.cap.read()
        if not ok:
            return None, None
        if self.is_file:   # use the video's own clock so replays behave like live
            self.t_file += 1.0 / self.fps
            return self.t_file, frame
        return time.time(), frame
