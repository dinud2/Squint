"""Find bottle-like objects in a frame: NanoDet-Plus (COCO, OpenCV model zoo, Apache-2.0)
run with cv2.dnn, so it works on QNX's OpenCV. Post-processing follows the zoo's
reference nanodet.py.

Pill bottles show up as COCO "bottle", sometimes "cup" or "vase"; we keep all three and
let the bottle gallery decide what they are.
"""
import os

import cv2
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.path.join(HERE, "models", "object_detection_nanodet_2022nov.onnx")
COCO_BOTTLEISH = {39: "bottle", 41: "cup", 75: "vase"}


class NanoDet:
    SIZE = 416
    STRIDES = (8, 16, 32, 64)
    REG_MAX = 7

    def __init__(self, model=MODEL, score=0.25, iou=0.5, classes=COCO_BOTTLEISH):
        self.net = cv2.dnn.readNet(model)
        self.score, self.iou, self.classes = score, iou, classes
        self.mean = np.array([103.53, 116.28, 123.675], np.float32).reshape(1, 1, 3)
        self.std = np.array([57.375, 57.12, 58.395], np.float32).reshape(1, 1, 3)
        self.project = np.arange(self.REG_MAX + 1)
        self.anchors = []
        for s in self.STRIDES:
            n = int(self.SIZE / s)
            xv, yv = np.meshgrid(np.arange(n) * s, np.arange(n) * s)
            self.anchors.append(np.column_stack((xv.flatten() + 0.5 * (s - 1), yv.flatten() + 0.5 * (s - 1))))

    def _letterbox(self, img):
        h, w = img.shape[:2]
        r = self.SIZE / max(h, w)
        nh, nw = int(round(h * r)), int(round(w * r))
        out = np.zeros((self.SIZE, self.SIZE, 3), np.uint8)
        top, left = (self.SIZE - nh) // 2, (self.SIZE - nw) // 2
        out[top:top + nh, left:left + nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
        return out, r, left, top

    def __call__(self, frame):
        """-> list of (x1, y1, x2, y2, score, class_name) in frame pixels."""
        img, r, left, top = self._letterbox(frame)
        blob = cv2.dnn.blobFromImage(((img.astype(np.float32) - self.mean) / self.std))
        self.net.setInput(blob)
        outs = self.net.forward(self.net.getUnconnectedOutLayersNames())
        # Pair class/box outputs by size, not position: OpenCV builds differ in output order
        # (alternating cls/reg vs all cls then all reg) and in how many levels they return.
        n_cls = 80
        cls_by_n = {o.reshape(-1, o.shape[-1]).shape[0]: o for o in outs if o.shape[-1] == n_cls}
        reg_by_n = {o.reshape(-1, o.shape[-1]).shape[0]: o for o in outs if o.shape[-1] == 4 * (self.REG_MAX + 1)}
        boxes, scores = [], []
        for stride, anc in zip(self.STRIDES, self.anchors):
            if len(anc) not in cls_by_n or len(anc) not in reg_by_n:
                continue
            cls, reg = cls_by_n[len(anc)], reg_by_n[len(anc)]
            cls = cls.reshape(-1, cls.shape[-1])
            reg = np.exp(reg.reshape(-1, self.REG_MAX + 1))
            reg = (reg / reg.sum(1, keepdims=True)) @ self.project
            d = reg.reshape(-1, 4) * stride
            boxes.append(np.column_stack([anc[:, 0] - d[:, 0], anc[:, 1] - d[:, 1],
                                          anc[:, 0] + d[:, 2], anc[:, 1] + d[:, 3]]))
            scores.append(cls)
        boxes, scores = np.concatenate(boxes), np.concatenate(scores)
        keep_cls = list(self.classes)
        sub = scores[:, keep_cls]
        cid = np.array(keep_cls)[sub.argmax(1)]
        conf = sub.max(1)
        m = conf >= self.score
        if not m.any():
            return []
        boxes, conf, cid = boxes[m], conf[m], cid[m]
        wh = boxes.copy(); wh[:, 2:] -= wh[:, :2]
        idx = cv2.dnn.NMSBoxes(wh.tolist(), conf.tolist(), self.score, self.iou)
        out = []
        H, W = frame.shape[:2]
        for i in np.array(idx).reshape(-1):
            x1, y1, x2, y2 = boxes[i]
            x1, x2 = np.clip([(x1 - left) / r, (x2 - left) / r], 0, W)
            y1, y2 = np.clip([(y1 - top) / r, (y2 - top) / r], 0, H)
            out.append((int(x1), int(y1), int(x2), int(y2), float(conf[i]), self.classes[int(cid[i])]))
        return sorted(out, key=lambda b: -b[4])
