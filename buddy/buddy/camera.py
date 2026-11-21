"""Frame sources.

  http://<pi>:8080/stream    QNX camstream (pi/camstream.c), MJPEG over HTTP
  "0", "1"...                a local webcam
  path/to/clip.mp4           a recorded clip

For MJPEG we don't use cv2.VideoCapture: its FFmpeg reader buffers several frames
(latency) and isn't available in every OpenCV build. MjpegCamera reads the stream in a
thread and keeps only the newest JPEG, so a slow consumer drops frames instead of
falling behind.
"""
import threading
import time
import urllib.request

import cv2
import numpy as np


class MjpegCamera:
    def __init__(self, url, timeout=5.0):
        self.url, self.timeout = url, timeout
        self.latest = None          # (arrival_time, jpeg_bytes, seq)
        self.seq = 0
        self.last_read = -1
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
                        chunk = r.read1(65536)
                        if not chunk:
                            break
                        buf += chunk
                        while True:                      # newest complete JPEG: FFD8 .. FFD9
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
            except Exception as ex:                      # camera restarted, Wi-Fi blip: retry
                self.error = str(ex)
                time.sleep(0.5)

    def read(self):
        """Block until a frame newer than the last one returned. -> (t, BGR frame)."""
        with self.cond:
            ok = self.cond.wait_for(lambda: self.latest is not None and self.latest[2] != self.last_read,
                                    timeout=self.timeout)
            if not ok:
                raise TimeoutError(f"no frames from {self.url} ({self.error or 'timeout'})")
            t, jpg, seq = self.latest
            self.last_read = seq
        return t, cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)

    def close(self):
        self.stopped = True


class Camera:
    def __init__(self, source):
        self.mjpeg = self.cap = None
        if source.startswith(("http://", "https://")):
            self.mjpeg = MjpegCamera(source)
        else:
            self.cap = cv2.VideoCapture(int(source) if source.isdigit() else source)

    def read(self):
        """-> (timestamp, frame); frame is None at the end of a file."""
        if self.mjpeg is not None:
            return self.mjpeg.read()
        ok, frame = self.cap.read()
        return time.time(), (frame if ok else None)

    def close(self):
        if self.mjpeg is not None:
            self.mjpeg.close()
        if self.cap is not None:
            self.cap.release()
