"""Train the label classifier the Pi runs behind the colour finder (buddy/colors.py).

    python tools/train_label_classifier.py --data <buddy/data>            # held-out sessions: report only
    python tools/train_label_classifier.py --data <buddy/data> --all      # train on everything, write models/

What it learns: the tight crop around a colour patch, exactly as the Pi cuts it
(colors.find(loose=True) + colors.bottle_crop), -> _other / advil / motrin / omega369 / tylenol / vitamind.
Colour stays the main cue: the Pi only lets the classifier veto a patch, split red into Tylenol vs
Vitamin D, or say "not sure" when it sees a medicine of another colour (colors.judge).

Made to not care about the room / light / distance / who holds it:
  * tight crops (little background), and the background inside them is REPLACED in ~65 % of
    the samples (GrabCut cut-out of the bottle + hand pasted on other rooms, the venue, textures,
    random colourful shapes), random box jitter (fingers over the label), scale (far away: down to
    20 px and back), rotation, blur, noise, JPEG, brightness / contrast / gamma. No hue jitter.
  * negatives: every colour patch found in photos without a medicine (skin, shirts, lanyards,
    windows, water bottles, faces) plus random boxes.

Honest numbers: whole recording sessions are held out (the last one of each bottle, a second
camera's Tylenol photos, Kathy's face frames), and the whole pipeline (colour + classifier, the
code the Pi runs) is scored per photo: right / WRONG BOTTLE / not sure / missed. --real <dir> adds
full camera frames with a truth.json ({"file.jpg": "advil" | "_other", ...}), e.g. the Pi's
data/shown/raw.

Data (--data, default buddy/data):
  train_raw/<class>/<ms>.jpg       centre-box crops from tools/capture_bottle.py (960x544 frames)
  frames/<class>/<session>/*.jpg   full frames from tools/capture_frames.py (any room / person)
  faces/<person>/full/*.jpg        the Pi's face frames: no medicine in them -> negatives
--extra <class>:<dir>[:<frame_scale>] more photo folders (one session each), e.g. another camera.
"""
import argparse
import json
import os
import random
import sys
import time
from multiprocessing import Pool

import cv2
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from buddy import colors  # noqa: E402

# omega369 is a bottle nobody takes here: the Pi must know it to say "not registered in the app"
# (its amber capsules look orange, like Motrin, so it is in the orange family)
CLASSES = ["_other", "advil", "motrin", "omega369", "tylenol", "vitamind"]
FAM = {"advil": "advil", "motrin": "motrin", "omega369": "motrin", "tylenol": "red", "vitamind": "red"}
AS_OTHER = {"_other", "_empty"}                  # folders of photos with no medicine
SIZE = 224
MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]
PI_FRAME = 960 * 544
GAP_MS = 30_000                                 # a pause this long starts a new recording session


# ---------------------------------------------------------------- photos and sessions
def photos(a):
    """-> [{"path", "cls", "session", "frame_area"}]"""
    out = []
    raw = os.path.join(a.data, "train_raw")
    if os.path.isdir(raw):
        for c in sorted(os.listdir(raw)):
            d = os.path.join(raw, c)
            fs = sorted((int(f[:-4]), f) for f in os.listdir(d) if f.endswith(".jpg") and f[:-4].isdigit())
            k, prev = 0, None
            for t, f in fs:
                if prev is not None and t - prev > GAP_MS:
                    k += 1
                prev = t
                out.append({"path": os.path.join(d, f), "cls": c, "session": f"raw/{c}/{k}", "frame_area": PI_FRAME})
    fr = os.path.join(a.data, "frames")
    if os.path.isdir(fr):
        for c in sorted(os.listdir(fr)):
            for s in sorted(os.listdir(os.path.join(fr, c))):
                d = os.path.join(fr, c, s)
                for f in sorted(os.listdir(d)):
                    if f.endswith(".jpg"):
                        out.append({"path": os.path.join(d, f), "cls": c, "session": f"frames/{c}/{s}", "frame_area": None})
    faces = os.path.join(a.data, "faces")
    if os.path.isdir(faces):
        for p in sorted(os.listdir(faces)):
            d = os.path.join(faces, p, "full")
            if os.path.isdir(d):
                for f in sorted(os.listdir(d)):
                    if f.endswith(".jpg"):
                        out.append({"path": os.path.join(d, f), "cls": "_other", "session": f"faces/{p}", "frame_area": None})
    for spec in a.extra:
        parts = spec.split(":")
        c, d, scale = parts[0], parts[1], float(parts[2]) if len(parts) > 2 else 1.0
        for f in sorted(os.listdir(d)):
            if f.endswith(".jpg"):
                p = os.path.join(d, f)
                h, w = cv2.imread(p).shape[:2]
                out.append({"path": p, "cls": c, "session": f"extra/{c}/{d}", "frame_area": int(w * h * scale)})
    for o in out:
        o["label"] = "_other" if o["cls"] in AS_OTHER else o["cls"]
    return out


def held_out(items):
    """Whole sessions for testing: the last session of each bottle (and of omega369), the extra
    folders and Kathy's face frames. A class recorded in one session only (_other) gives its
    later half (o["half"])."""
    sessions = {}
    for o in items:
        sessions.setdefault(o["cls"], [])
        if o["session"] not in sessions[o["cls"]]:
            sessions[o["cls"]].append(o["session"])
    test = {"faces/kathy"}
    for c, ss in sessions.items():
        own = [s for s in ss if not s.startswith(("extra/", "faces/"))]
        if len(own) > 1:
            test.add(own[-1])
        elif len(own) == 1:
            same = [o for o in items if o["session"] == own[0]]
            for k, o in enumerate(same):
                o["half"] = k >= len(same) // 2
        test.update(s for s in ss if s.startswith("extra/"))
    return test


def is_test(o, test):
    return o["session"] in test or o.get("half", False)


# ---------------------------------------------------------------- patches + bottle masks
def patches(o):
    """Label patches in one photo, as the Pi finds them. Bottle photo: the best patch of the
    bottle's colour (other patches of that colour are left out: maybe part of the label).
    Patches of other colours, and everything in no-medicine photos -> negatives."""
    img = cv2.imread(o["path"])
    found = colors.find(img, frame_area=o["frame_area"], loose=True)[:5]
    out = []
    if o["label"] == "_other":
        out = [(f["box"], "_other", f["name"]) for f in found]
    else:
        mine = [f for f in found if f["name"] == FAM[o["label"]]]
        if mine:
            b = mine[0]["box"]
            out.append((b, o["label"], mine[0]["name"]))
            for f in found:
                if f["name"] != FAM[o["label"]] and not _overlap(f["box"], _grow(b, 2.6)):
                    out.append((f["box"], "_other", f["name"]))
    return out


def _grow(b, g):
    cx, cy, s = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2, max(b[2] - b[0], b[3] - b[1]) * g / 2
    return [cx - s, cy - 1.3 * s, cx + s, cy + 1.3 * s]


def _overlap(a, b):
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def bottle_mask(args):
    """GrabCut the bottle (+ the hand holding it) around a label patch -> uint8 0/255 mask, full size."""
    path, box = args
    img = cv2.imread(path)
    h, w = img.shape[:2]
    r = [int(max(0, v)) for v in _grow(box, 3.0)]
    r[2], r[3] = min(w, r[2]), min(h, r[3])
    sub = img[r[1]:r[3], r[0]:r[2]]
    m = np.full(sub.shape[:2], cv2.GC_PR_BGD, np.uint8)
    inner = [int(v) for v in _grow(box, 1.5)]
    m[max(0, inner[1] - r[1]):max(0, inner[3] - r[1]), max(0, inner[0] - r[0]):max(0, inner[2] - r[0])] = cv2.GC_PR_FGD
    m[box[1] - r[1]:box[3] - r[1], box[0] - r[0]:box[2] - r[0]] = cv2.GC_FGD
    for side in (m[:3], m[-3:], m[:, :3], m[:, -3:]):   # the crop border (inside the picture) is background
        side[side == cv2.GC_PR_BGD] = cv2.GC_BGD
    try:
        cv2.grabCut(sub, m, None, np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64), 4, cv2.GC_INIT_WITH_MASK)
    except cv2.error:
        return None
    full = np.zeros((h, w), np.uint8)
    full[r[1]:r[3], r[0]:r[2]] = np.where((m == cv2.GC_FGD) | (m == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    return cv2.imencode(".png", full)[1].tobytes()


# ---------------------------------------------------------------- augmentation
class Backgrounds:
    def __init__(self, paths, rng):
        self.imgs = [cv2.imread(p) for p in paths]
        self.rng = rng

    def get(self, h, w):
        r = self.rng
        k = r.random()
        if k < 0.55 and self.imgs:                       # another room / the venue / a shirt
            im = self.imgs[r.randrange(len(self.imgs))]
            H, W = im.shape[:2]
            s = r.uniform(0.25, 1.0)
            ch, cw = max(8, int(H * s)), max(8, int(W * s))
            y, x = r.randrange(H - ch + 1), r.randrange(W - cw + 1)
            bg = cv2.resize(im[y:y + ch, x:x + cw], (w, h))
            if r.random() < 0.5:
                bg = cv2.flip(bg, 1)
            return bg
        if k < 0.75:                                     # plain wall / counter, any colour
            c = np.array([r.randrange(256) for _ in range(3)], np.uint8)
            c2 = np.array([r.randrange(256) for _ in range(3)], np.float32)
            g = np.linspace(0, 1, h if r.random() < 0.5 else w, dtype=np.float32)
            g = g[:, None] if len(g) == h else g[None, :]
            bg = (c[None, None] * (1 - g[..., None] * 0.5) + c2[None, None] * g[..., None] * 0.5)
            bg = np.broadcast_to(bg, (h, w, 3)).astype(np.float32)
            bg += np.random.default_rng(r.randrange(1 << 30)).normal(0, r.uniform(0, 12), (h, w, 3))
            return np.clip(bg, 0, 255).astype(np.uint8)
        bg = np.full((h, w, 3), [r.randrange(256) for _ in range(3)], np.uint8)   # clutter: colourful shapes
        for _ in range(r.randrange(3, 12)):
            col = [r.randrange(256) for _ in range(3)]
            x0, y0 = r.randrange(w), r.randrange(h)
            if r.random() < 0.5:
                cv2.rectangle(bg, (x0, y0), (x0 + r.randrange(5, w // 2 + 6), y0 + r.randrange(5, h // 2 + 6)), col, -1)
            else:
                cv2.circle(bg, (x0, y0), r.randrange(4, max(5, min(h, w) // 3)), col, -1)
        return cv2.GaussianBlur(bg, (0, 0), r.uniform(0.5, 3))


def augment(img, box, mask, bgs, rng, train=True):
    """-> the crop the classifier sees (BGR), from a photo, a patch box and (bottles) a bottle mask."""
    h, w = img.shape[:2]
    if not train:
        return colors.bottle_crop(img, box)
    if mask is not None and rng.random() < 0.65:
        m = cv2.GaussianBlur(mask, (5, 5), 0).astype(np.float32)[..., None] / 255.0
        img = (img * m + bgs.get(h, w) * (1 - m)).astype(np.uint8)
    bw, bh = box[2] - box[0], box[3] - box[1]
    cx = (box[0] + box[2]) / 2 + rng.uniform(-0.15, 0.15) * bw
    cy = (box[1] + box[3]) / 2 + rng.uniform(-0.15, 0.15) * bh
    sx, sy = bw * rng.uniform(0.7, 1.3) / 2, bh * rng.uniform(0.7, 1.3) / 2
    jb = [int(cx - sx), int(cy - sy), int(cx + sx), int(cy + sy)]
    c = colors.bottle_crop(img, jb, grow=rng.uniform(1.9, 2.6))
    if c.shape[0] < 8 or c.shape[1] < 8:
        c = colors.bottle_crop(img, box)
    ch, cw = c.shape[:2]
    if rng.random() < 0.7:
        M = cv2.getRotationMatrix2D((cw / 2, ch / 2), rng.uniform(-20, 20), 1.0)
        c = cv2.warpAffine(c, M, (cw, ch), borderMode=cv2.BORDER_REFLECT)
    if rng.random() < 0.45:                                  # far away: few pixels
        s = rng.uniform(18, 70) / max(ch, cw)
        if s < 1:
            c = cv2.resize(c, (max(4, int(cw * s)), max(4, int(ch * s))), interpolation=cv2.INTER_AREA)
    c = cv2.resize(c, (SIZE, SIZE), interpolation=cv2.INTER_LINEAR)
    c = cv2.convertScaleAbs(c, alpha=rng.uniform(0.55, 1.45), beta=rng.uniform(-45, 45))
    g = rng.uniform(0.6, 1.6)                                # the same gamma on every channel: hue kept
    c = (255 * (c / 255.0) ** g).astype(np.uint8)
    if rng.random() < 0.35:
        c = cv2.GaussianBlur(c, (0, 0), rng.uniform(0.5, 2.0))
    if rng.random() < 0.3:
        c = np.clip(c + np.random.default_rng(rng.randrange(1 << 30)).normal(0, rng.uniform(2, 10), c.shape), 0, 255).astype(np.uint8)
    if rng.random() < 0.5:
        c = cv2.imdecode(cv2.imencode(".jpg", c, [cv2.IMWRITE_JPEG_QUALITY, rng.randrange(30, 90)])[1], cv2.IMREAD_COLOR)
    return c


def to_tensor(c):
    x = cv2.resize(c, (SIZE, SIZE), interpolation=cv2.INTER_AREA)[:, :, ::-1].astype(np.float32) / 255.0
    return ((x - np.array(MEAN, np.float32)) / np.array(STD, np.float32)).transpose(2, 0, 1)


# ---------------------------------------------------------------- whole-pipeline scoring
def score_pipeline(clf, rows, title):
    """rows: [(img, truth, frame_area)] -> prints right / wrong / not sure / missed; returns the counts."""
    res = {"right": 0, "wrong": 0, "unsure": 0, "missed": 0, "neg_ok": 0, "neg_named": 0, "neg_unsure": 0}
    per = {}
    wrong = []
    for img, truth, fa, path in rows:
        name, info = colors.identify(img, clf, frame_area=fa)
        if truth == "_other":
            k = "neg_named" if name else ("neg_unsure" if info.get("unsure") else "neg_ok")
        else:
            k = "right" if name == truth else "wrong" if name else "unsure" if info.get("unsure") else "missed"
        res[k] += 1
        per.setdefault(truth, {}).setdefault(k, 0)
        per[truth][k] += 1
        if k in ("wrong", "neg_named"):
            wrong.append((os.path.basename(path), truth, name))
    nb = res["right"] + res["wrong"] + res["unsure"] + res["missed"]
    nn = res["neg_ok"] + res["neg_named"] + res["neg_unsure"]
    print(f"\n== {title}: {nb} bottle photos, {nn} without a medicine")
    if nb:
        print(f"   right {res['right']} ({100 * res['right'] / nb:.0f} %)   WRONG BOTTLE {res['wrong']}   "
              f"not sure {res['unsure']}   missed {res['missed']}")
    if nn:
        print(f"   no medicine: named a bottle {res['neg_named']}, not sure {res['neg_unsure']}, ok {res['neg_ok']}")
    for t in sorted(per):
        print(f"     {t:9s} {per[t]}")
    for w in wrong[:12]:
        print("     wrong:", w)
    return res


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(HERE, "data"))
    ap.add_argument("--extra", action="append", default=[], help="class:dir[:frame_scale]")
    ap.add_argument("--real", action="append", default=[], help="dir of full camera frames with truth.json")
    ap.add_argument("--all", action="store_true", help="train on every session and write models/")
    ap.add_argument("--out", default=os.path.join(HERE, "models"))
    ap.add_argument("--epochs", type=int, default=14)
    ap.add_argument("--per-epoch", type=int, default=4000)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--cache", default=None, help="where to keep the GrabCut masks (default: <data>/.label_masks)")
    a = ap.parse_args()

    import torch
    import torch.nn as nn
    from torchvision import models
    torch.manual_seed(0)
    torch.set_num_threads(os.cpu_count() or 4)
    rng = random.Random(0)

    items = photos(a)
    test = set() if a.all else held_out(items)
    print(f"{len(items)} photos in {len({o['session'] for o in items})} sessions; "
          f"held out: {sorted(test) if test else 'nothing (--all)'}", flush=True)

    # patches (= training crops), with a bottle mask for each bottle patch
    with Pool(os.cpu_count()) as pool:
        found = pool.map(patches, items, chunksize=8)
    crops = []
    for o, ps in zip(items, found):
        for box, label, colour in ps:
            crops.append({**o, "box": box, "y": label, "colour": colour})
    cache = a.cache or os.path.join(a.data, ".label_masks")
    os.makedirs(cache, exist_ok=True)

    def key(c):
        return os.path.join(cache, (c["path"].replace("/", "_") + "_" + "_".join(map(str, c["box"])))[-180:] + ".png")
    todo = [c for c in crops if c["y"] != "_other" and not os.path.exists(key(c))]
    if todo:
        t0 = time.time()
        with Pool(os.cpu_count()) as pool:
            for c, png in zip(todo, pool.map(bottle_mask, [(c["path"], c["box"]) for c in todo], chunksize=4)):
                if png:
                    open(key(c), "wb").write(png)
        print(f"GrabCut masks for {len(todo)} bottle patches in {time.time() - t0:.0f}s (cached in {cache})", flush=True)
    for c in crops:
        c["mask"] = key(c) if c["y"] != "_other" and os.path.exists(key(c)) else None

    train = [c for c in crops if not is_test(c, test)]
    held = [c for c in crops if is_test(c, test)]
    neg_photos = [o for o in items if o["label"] == "_other" and not is_test(o, test)]
    for name, xs in (("train", train), ("held-out", held)):
        print(f"{name} crops: " + ", ".join(f"{k} {sum(c['y'] == k for c in xs)}" for k in CLASSES), flush=True)
    bg_paths = [o["path"] for o in neg_photos]
    print(f"{len(bg_paths)} background photos (+ synthetic walls and clutter)", flush=True)

    # one sample = a patch crop (or a random box in a no-medicine photo), freshly augmented
    class Samples(torch.utils.data.Dataset):
        def __init__(self, n, seed):
            self.n, self.seed = n, seed
            self.bgs = None
            self.cache = {}

        def __len__(self):
            return self.n

        def img(self, p):
            if p not in self.cache:
                self.cache[p] = cv2.imread(p)
            return self.cache[p]

        def __getitem__(self, i):
            r = random.Random(self.seed * 1_000_003 + i + int(time.time() * 1000) % 100_000)
            if self.bgs is None:
                self.bgs = Backgrounds(bg_paths, random.Random(r.randrange(1 << 30)))
            self.bgs.rng = r
            y = r.choice(CLASSES + ["_other"])                      # _other twice as often
            if y == "_other" and r.random() < 0.3:                  # a random box in a no-medicine photo
                o = neg_photos[r.randrange(len(neg_photos))]
                im = self.img(o["path"])
                h, w = im.shape[:2]
                s = r.uniform(12, 90)
                x0, y0 = r.uniform(0, w - s), r.uniform(0, h - s)
                box = [int(x0), int(y0), int(x0 + s * r.uniform(0.5, 1.5)), int(y0 + s)]
                c = augment(im, box, None, self.bgs, r)
            else:
                pool_ = by_class[y]
                cr = pool_[r.randrange(len(pool_))]
                m = cv2.imread(cr["mask"], cv2.IMREAD_GRAYSCALE) if cr["mask"] else None
                c = augment(self.img(cr["path"]), cr["box"], m, self.bgs, r)
            return torch.from_numpy(to_tensor(c)), CLASSES.index(y)

    by_class = {k: [c for c in train if c["y"] == k] for k in CLASSES}
    dl = torch.utils.data.DataLoader(Samples(a.per_epoch, 1), batch_size=48, num_workers=min(12, os.cpu_count()),
                                     persistent_workers=True)

    net = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.DEFAULT)
    net.classifier[3] = nn.Linear(net.classifier[3].in_features, len(CLASSES))
    opt = torch.optim.AdamW(net.parameters(), lr=a.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=a.lr, total_steps=a.epochs * len(dl))
    lossf = nn.CrossEntropyLoss(label_smoothing=0.05)

    def crop_eval(xs):
        net.eval()
        P = []
        with torch.no_grad():
            for i in range(0, len(xs), 64):
                b = np.stack([to_tensor(colors.bottle_crop(cv2.imread(c["path"]), c["box"])) for c in xs[i:i + 64]])
                P.append(torch.softmax(net(torch.from_numpy(b)), 1).numpy())
        P = np.concatenate(P) if P else np.zeros((0, len(CLASSES)))
        Y = np.array([CLASSES.index(c["y"]) for c in xs])
        return P, Y

    t0 = time.time()
    for ep in range(a.epochs):
        net.train()
        tot, n = 0.0, 0
        for x, y in dl:
            opt.zero_grad()
            loss = lossf(net(x), y)
            loss.backward()
            opt.step()
            sched.step()
            tot, n = tot + loss.item() * len(y), n + len(y)
        msg = f"epoch {ep + 1:2d}/{a.epochs}  loss {tot / n:.3f}"
        if held:
            P, Y = crop_eval(held)
            msg += f"  held-out crop acc {(P.argmax(1) == Y).mean():.3f}"
        print(msg + f"  ({time.time() - t0:.0f}s)", flush=True)

    if held:
        P, Y = crop_eval(held)
        print("\nheld-out crops, confusion (rows = true, cols = predicted " + " ".join(CLASSES) + "):")
        for i, c in enumerate(CLASSES):
            print(f"  {c:9s} " + " ".join(f"{int(((Y == i) & (P.argmax(1) == j)).sum()):5d}" for j in range(len(CLASSES))))

    # export (cv2.dnn on the Pi: opset 13) and score the whole pipeline with exactly that file
    out_dir = a.out if a.all else os.path.join(a.cache or os.path.join(a.data, ".label_masks"), "eval_model")
    os.makedirs(out_dir, exist_ok=True)
    onnx_p, meta_p = os.path.join(out_dir, "bottle_classifier.onnx"), os.path.join(out_dir, "bottle_classes.json")
    net.eval()
    torch.onnx.export(net, torch.zeros(1, 3, SIZE, SIZE), onnx_p, opset_version=13,
                      input_names=["image"], output_names=["logits"], dynamo=False)
    with open(meta_p, "w") as f:
        json.dump({"classes": CLASSES, "size": SIZE, "mean": MEAN, "std": STD, "kind": "label-crop",
                   "trained": time.strftime("%Y-%m-%d %H:%M"), "held_out": sorted(test)}, f, indent=1)
    from buddy.bottles import Classifier
    clf = Classifier(onnx_p, meta_p)
    x = np.random.default_rng(0).integers(0, 255, (120, 90, 3), dtype=np.uint8)
    with torch.no_grad():
        pt = torch.softmax(net(torch.from_numpy(to_tensor(x))[None]), 1).numpy()[0]
    print(f"\nwrote {onnx_p}; cv2.dnn vs torch max difference {max(abs(clf(x)[k] - pt[i]) for i, k in enumerate(CLASSES)):.1e}")

    held_photos = [o for o in items if is_test(o, test)]
    if held_photos:
        rows = [(cv2.imread(o["path"]), o["label"], o["frame_area"], o["path"]) for o in held_photos]
        score_pipeline(clf, rows, "held-out sessions, whole pipeline (colour + classifier)")
        for s in sorted({o["session"] for o in held_photos}):
            score_pipeline(clf, [r for r, o in zip(rows, held_photos) if o["session"] == s], f"  session {s}")
    for d in a.real:
        truth = json.load(open(os.path.join(d, "truth.json")))
        rows = [(cv2.imread(os.path.join(d, f)), t, None, f) for f, t in sorted(truth.items())
                if os.path.exists(os.path.join(d, f))]
        score_pipeline(clf, rows, f"real camera frames {d}")


if __name__ == "__main__":
    main()
