"""Teach MobileNetV3-Small to embed *bottles*, not backgrounds (domain-randomised metric learning).

Training data: thousands of random, made-up bottles in look-alike families
(same body/cap/band, different label text), rendered with heavy clutter,
fingers, blur and lighting changes. None of the demo or test bottles are used.
Loss: CosFace (normalised softmax with an additive margin) over bottle identities.
Output: models/bottle_embed.onnx, same interface as the plain embedder
(float32 [1,3,224,224] ImageNet-normalised RGB -> L2-normalised [1,256]).

    python tools/train_bottle_embed.py --steps 1500
"""
import argparse
import os
import string
import sys
import time

import cv2
import numpy as np
import torch
import torch.nn.functional as Fn
import torchvision

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from sim.bottle_sim import BOTTLES, UNKNOWN, render  # noqa: E402

MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)
HELD_OUT = {s["name"] for s in list(BOTTLES.values()) + list(UNKNOWN.values())}
PALETTE_BODY = [(40, 110, 190), (40, 110, 190), (235, 235, 230), (245, 245, 245), (30, 160, 230), (30, 30, 140),
                (200, 200, 205), (60, 140, 70), (20, 70, 150), (90, 60, 40)]
PALETTE_CAP = [(240, 240, 240), (30, 30, 30), (30, 120, 230), (220, 60, 40), (200, 200, 205), (20, 60, 20)]
PALETTE_BAND = [(160, 90, 30), (60, 140, 40), (30, 30, 200), (20, 120, 200), (240, 240, 240), (120, 40, 120)]


def rand_word(rng, lo=5, hi=12):
    while True:
        w = "".join(rng.choice(list(string.ascii_uppercase), int(rng.integers(lo, hi))))
        if w not in HELD_OUT:
            return w


def make_identities(n_fam, per_fam, rng):
    ids = []
    for _ in range(n_fam):
        jit = lambda c: tuple(int(np.clip(v + rng.integers(-25, 25), 0, 255)) for v in c)  # noqa: E731
        base = dict(body=jit(PALETTE_BODY[rng.integers(len(PALETTE_BODY))]),
                    cap=jit(PALETTE_CAP[rng.integers(len(PALETTE_CAP))]),
                    band=jit(PALETTE_BAND[rng.integers(len(PALETTE_BAND))]),
                    h=float(rng.uniform(0.8, 1.3)), who=rand_word(rng, 4, 7) + " " + rand_word(rng, 1, 2))
        for _ in range(per_fam):   # look-alikes: only the text differs
            s = dict(base)
            s.update(name=rand_word(rng), dose=f"{int(rng.choice([1, 2, 5, 10, 20, 25, 50, 81, 100, 200, 500]))} MG")
            if rng.random() < 0.3:
                s["who"] = rand_word(rng, 4, 7) + " " + rand_word(rng, 1, 2)
            ids.append(s)
    return ids


class Net(torch.nn.Module):
    def __init__(self, dim=256):
        super().__init__()
        m = torchvision.models.mobilenet_v3_small(weights="IMAGENET1K_V1")
        self.features = m.features
        self.proj = torch.nn.Linear(576, dim)

    def forward(self, x):
        f = self.features(x)
        f = f.clamp(min=1e-6).pow(3).mean((2, 3)).pow(1 / 3)     # GeM pooling
        return Fn.normalize(self.proj(f), dim=1)


def to_tensor(img):
    x = cv2.resize(img, (224, 224))[:, :, ::-1].astype(np.float32) / 255.0
    return ((x - MEAN) / STD).transpose(2, 0, 1)


class Stream(torch.utils.data.IterableDataset):
    """Endless (image, identity) pairs, rendered in worker processes."""

    def __init__(self, ids, batch):
        self.ids, self.batch = ids, batch

    def __iter__(self):
        wi = torch.utils.data.get_worker_info()
        rng = np.random.default_rng(1000 + (wi.id if wi else 0) + int(time.time()))
        while True:
            y = rng.integers(0, len(self.ids), self.batch)
            imgs = np.stack([to_tensor(render(self.ids[i], rng, "test" if rng.random() < 0.75 else "enrol")) for i in y])
            yield torch.from_numpy(imgs), torch.from_numpy(y)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=1500)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--families", type=int, default=300)
    ap.add_argument("--per_family", type=int, default=3)
    a = ap.parse_args()
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    rng = np.random.default_rng(0)
    ids = make_identities(a.families, a.per_family, rng)
    net = Net().to(dev)
    # freeze the early layers: they already know edges/textures; adapt the last blocks
    for i, layer in enumerate(net.features):
        for p in layer.parameters():
            p.requires_grad = i >= 7
    W = torch.nn.Parameter(torch.randn(len(ids), 256, device=dev) * 0.01)
    opt = torch.optim.AdamW([p for p in net.parameters() if p.requires_grad] + [W], lr=1e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=2e-3, total_steps=a.steps)
    s_scale, margin = 24.0, 0.25
    t0 = time.time()
    net.train()
    loader = iter(torch.utils.data.DataLoader(Stream(ids, a.batch), batch_size=None, num_workers=6, prefetch_factor=4))
    for step in range(a.steps):
        x, yt = next(loader)
        x, yt = x.to(dev), yt.to(dev)
        e = net(x)
        logits = e @ Fn.normalize(W, dim=1).T
        logits = s_scale * (logits - margin * Fn.one_hot(yt, len(ids)))
        loss = Fn.cross_entropy(logits, yt)
        opt.zero_grad(); loss.backward(); opt.step(); sched.step()
        if step % 100 == 0 or step == a.steps - 1:
            acc = (logits.argmax(1) == yt).float().mean().item()
            print(f"step {step:5d} loss {loss.item():.3f} batch-acc {acc:.2f} ({time.time()-t0:.0f}s)", flush=True)
    net = net.cpu().eval()
    path = os.path.join(HERE, "models", "bottle_embed.onnx")
    torch.onnx.export(net, torch.zeros(1, 3, 224, 224), path, input_names=["input"], output_names=["embedding"],
                      opset_version=13, dynamo=False)
    print("wrote", path)


if __name__ == "__main__":
    main()
