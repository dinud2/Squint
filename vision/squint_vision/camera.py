"""Frame sources. Laptop: webcam or video file. Pi/QNX: Part B's get_frame()."""
import importlib
import os
import time

import cv2


class Camera:
    def __init__(self, source="0"):
        self.b = None
        if source == "qnx":
            # Part B exposes get_frame() -> BGR numpy frame (module name via env)
            self.b = importlib.import_module(os.environ.get("SQUINT_CAMERA_MODULE", "camera"))
        else:
            self.cap = cv2.VideoCapture(int(source) if source.isdigit() else source)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.is_file = not source.isdigit()
            self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 15
            self.t_file = 0.0

    def read(self):
        """-> (timestamp_s, frame) or (None, None) at end of a file."""
        if self.b is not None:
            return time.time(), self.b.get_frame()
        ok, frame = self.cap.read()
        if not ok:
            return None, None
        if self.is_file:   # use the video's own clock so replays behave like live
            self.t_file += 1.0 / self.fps
            return self.t_file, frame
        return time.time(), frame
