"""Train the bottle classifier on the laptop; the Pi only runs the result (cv2.dnn).

    python tools/clean_bottle_data.py            # data/train_raw -> data/train_clean
    python tools/train_bottle_classifier.py      # -> models/bottle_classifier.onnx + bottle_classes.json

MobileNetV3-small (ImageNet weights) fine-tuned on the box crops collected with the trainer,
6 classes: the bottles + "_other" (no medicine). Validation holds out whole runs of 8
consecutive shots (neighbouring shots are near-duplicates, so a random split would flatter it).
Input: the camera box crop, resized to 224x224, RGB, ImageNet normalisation (same as the Pi).
"""
import argparse
import json
import os
import random
import time

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]
SIZE = 224


def split(src, val_frac=0.2, run=8, seed=0):
    classes = sorted(d for d in os.listdir(src) if os.path.isdir(os.path.join(src, d)) and d != "dropped")
    rng = random.Random(seed)
    train, val = [], []
    for ci, c in enumerate(classes):
        files = sorted(f for f in os.listdir(os.path.join(src, c)) if f.endswith(".jpg"))
        runs = [files[i:i + run] for i in range(0, len(files), run)]
        rng.shuffle(runs)
        n_val = max(1, round(val_frac * len(runs)))
        for k, r in enumerate(runs):
            (val if k < n_val else train).extend((os.path.join(src, c, f), ci) for f in r)
    return classes, train, val


class Photos(Dataset):
    def __init__(self, items, tf):
        self.items, self.tf = items, tf

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        p, y = self.items[i]
        return self.tf(Image.open(p).convert("RGB")), y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(HERE, "data", "train_clean"))
    ap.add_argument("--epochs", type=int, default=14)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=6e-4)
    a = ap.parse_args()
    torch.manual_seed(0)
    torch.set_num_threads(max(1, os.cpu_count() or 1))

    classes, train, val = split(a.src)
    print(f"classes {classes}\ntrain {len(train)} photos, val {len(val)} photos (held out in runs of 8)", flush=True)
    tf_train = transforms.Compose([
        transforms.RandomResizedCrop(SIZE, scale=(0.55, 1.0), ratio=(0.6, 1.4)),
        transforms.RandomRotation(15),
        transforms.ColorJitter(0.4, 0.4, 0.3, 0.03),
        transforms.RandomApply([transforms.GaussianBlur(5, sigma=(0.1, 2.0))], p=0.4),
        transforms.RandomGrayscale(0.05),
        transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
    tf_val = transforms.Compose([transforms.Resize((SIZE, SIZE)), transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
    dl_train = DataLoader(Photos(train, tf_train), batch_size=a.batch, shuffle=True, num_workers=4)
    dl_val = DataLoader(Photos(val, tf_val), batch_size=64, num_workers=2)

    net = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.DEFAULT)
    net.classifier[3] = nn.Linear(net.classifier[3].in_features, len(classes))
    opt = torch.optim.AdamW(net.parameters(), lr=a.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=a.lr, total_steps=a.epochs * len(dl_train))
    lossf = nn.CrossEntropyLoss(label_smoothing=0.05)

    def evaluate():
        net.eval()
        P, Y = [], []
        with torch.no_grad():
            for x, y in dl_val:
                P.append(torch.softmax(net(x), 1).numpy())
                Y.append(y.numpy())
        return np.concatenate(P), np.concatenate(Y)

    best, best_state = -1, None
    t0 = time.time()
    for ep in range(a.epochs):
        net.train()
        tot = 0.0
        for x, y in dl_train:
            opt.zero_grad()
            loss = lossf(net(x), y)
            loss.backward()
            opt.step()
            sched.step()
            tot += loss.item() * len(y)
        P, Y = evaluate()
        acc = float((P.argmax(1) == Y).mean())
        print(f"epoch {ep + 1:2d}/{a.epochs}  loss {tot / len(train):.3f}  val acc {acc:.3f}  ({time.time() - t0:.0f}s)", flush=True)
        if acc >= best:
            best, best_state = acc, {k: v.clone() for k, v in net.state_dict().items()}
    net.load_state_dict(best_state)

    # report on the held-out runs, with the confidence rule the Pi will use
    P, Y = evaluate()
    pred, conf = P.argmax(1), P.max(1)
    other = classes.index("_other")
    print(f"\nbest val accuracy {best:.3f}\nper class (top-1):")
    for ci, c in enumerate(classes):
        m = Y == ci
        print(f"  {c:9s} {int((pred[m] == ci).sum())}/{int(m.sum())}")
    print("\nconfusion (rows = true, cols = predicted):\n" + "\n".join(
        f"  {c:9s} " + " ".join(f"{int(((Y == i) & (pred == j)).sum()):3d}" for j in range(len(classes)))
        for i, c in enumerate(classes)))
    for thr in (0.6, 0.7, 0.8, 0.9):
        named = (conf >= thr) & (pred != other)
        bottle = Y != other
        ok = named & (pred == Y)
        print(f"  confidence >= {thr}: bottles named correctly {int(ok[bottle].sum())}/{int(bottle.sum())}, "
              f"wrong bottle {int((named & (pred != Y) & bottle).sum())}, "
              f"no-medicine named as a bottle {int(named[~bottle].sum())}/{int((~bottle).sum())}")

    # export for the Pi
    out = os.path.join(HERE, "models", "bottle_classifier.onnx")
    net.eval()
    torch.onnx.export(net, torch.zeros(1, 3, SIZE, SIZE), out, opset_version=13,
                      input_names=["image"], output_names=["logits"], dynamo=False)
    with open(os.path.join(HERE, "models", "bottle_classes.json"), "w") as f:
        json.dump({"classes": classes, "size": SIZE, "mean": MEAN, "std": STD, "val_acc": round(best, 4),
                   "trained": time.strftime("%Y-%m-%d %H:%M")}, f, indent=1)
    print(f"\nwrote {out}")

    # the Pi runs it with cv2.dnn: check it gives the same answer as torch
    import cv2
    dn = cv2.dnn.readNet(out)
    x, _ = Photos(val[:1], tf_val)[0]
    dn.setInput(x.unsqueeze(0).numpy())
    a1 = dn.forward().reshape(-1)
    with torch.no_grad():
        a2 = net(x.unsqueeze(0)).numpy().reshape(-1)
    print(f"cv2.dnn vs torch max difference: {np.abs(a1 - a2).max():.2e}")


if __name__ == "__main__":
    main()
