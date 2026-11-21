"""Run an ONNX model with ONNX Runtime, or fall back to OpenCV DNN.

On QNX we may only have one of the two (see C3). Force one with
SQUINT_BACKEND=ort|cv2.
"""
import os

import numpy as np


class OnnxModel:
    def __init__(self, path, threads=2):
        want = os.environ.get("SQUINT_BACKEND", "ort")
        self.kind = None
        if want == "ort":
            try:
                import onnxruntime as ort
                so = ort.SessionOptions()
                so.intra_op_num_threads = threads
                self.sess = ort.InferenceSession(path, so, providers=["CPUExecutionProvider"])
                self.input = self.sess.get_inputs()[0].name
                self.kind = "ort"
            except ImportError:
                pass
        if self.kind is None:
            import cv2
            self.net = cv2.dnn.readNetFromONNX(path)
            self.kind = "cv2"

    def __call__(self, x):
        if self.kind == "ort":
            return self.sess.run(None, {self.input: x})[0]
        self.net.setInput(x)
        return np.asarray(self.net.forward())
