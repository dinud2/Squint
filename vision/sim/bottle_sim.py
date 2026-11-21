"""Synthetic pill-bottle hand crops for testing few-shot, open-set recognition.

Each bottle is a recipe (body colour, cap, label band, text). A view is rendered as:
label texture wrapped on a cylinder (axis rotation shows a different part of the
label) -> bottle sprite -> random tilt/scale/position on a cluttered background
-> fingers drawn over it -> lighting, colour temperature, blur, noise, JPEG.

`enrol` views are easy (held up to the camera, slowly turned); `test` views are
hard (in motion, tilted toward the mouth, occluded, badly lit).
"""
import zlib

import cv2
import numpy as np

BOTTLES = {
    # the demo props (Part D prints these labels)
    "warfarin":          dict(body=(40, 110, 190), cap=(240, 240, 240), band=(160, 90, 30), name="WARFARIN", dose="5 MG", who="MARGARET H", h=1.0),
    "metoprolol_robert": dict(body=(40, 110, 190), cap=(240, 240, 240), band=(160, 90, 30), name="METOPROLOL", dose="25 MG", who="ROBERT H", h=1.0),
    "atorvastatin":      dict(body=(235, 235, 230), cap=(30, 30, 30), band=(60, 140, 40), name="ATORVASTATIN", dose="20 MG", who="MARGARET H", h=0.85),
}
UNKNOWN = {
    "lisinopril_lookalike": dict(body=(40, 110, 190), cap=(240, 240, 240), band=(160, 90, 30), name="LISINOPRIL", dose="10 MG", who="MARGARET H", h=1.0),
    "vitamin_d":   dict(body=(30, 160, 230), cap=(30, 120, 230), band=(30, 30, 200), name="VITAMIN D3", dose="1000 IU", who="", h=1.2),
    "aspirin":     dict(body=(245, 245, 245), cap=(220, 60, 40), band=(30, 30, 180), name="ASPIRIN", dose="81 MG", who="", h=0.8),
    "ibuprofen":   dict(body=(30, 30, 140), cap=(240, 240, 240), band=(240, 240, 240), name="IBUPROFEN", dose="200 MG", who="", h=1.1),
    "metformin":   dict(body=(200, 200, 205), cap=(200, 200, 205), band=(20, 120, 200), name="METFORMIN", dose="500 MG", who="ROBERT H", h=1.15),
    "green_tea":   dict(body=(60, 140, 70), cap=(20, 60, 20), band=(230, 230, 230), name="GREEN TEA", dose="", who="", h=1.3),
}
SKIN = [(140, 170, 220), (110, 150, 200), (80, 110, 160), (60, 85, 120), (170, 195, 235)]


def label_texture(spec, rng, w=360, h=150):
    tex = np.full((h, w, 3), (235, 238, 240), np.uint8)
    cv2.rectangle(tex, (0, 0), (w, 30), spec["band"], -1)
    cv2.putText(tex, "RX  SHOPPERS PHARMACY", (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(tex, spec["name"], (10, 68), cv2.FONT_HERSHEY_DUPLEX, 0.95, (20, 20, 20), 2, cv2.LINE_AA)
    cv2.putText(tex, spec["dose"], (10, 98), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2, cv2.LINE_AA)
    cv2.putText(tex, spec["who"], (10, 128), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (40, 40, 40), 1, cv2.LINE_AA)
    x = 240
    r = np.random.default_rng(zlib.crc32(spec["name"].encode()))   # barcode fixed per bottle (crc32: stable across runs, unlike hash())
    while x < w - 10:
        bw = int(r.integers(1, 4))
        cv2.rectangle(tex, (x, 95), (x + bw, 140), (10, 10, 10), -1)
        x += bw + int(r.integers(1, 4))
    cv2.putText(tex, "TAKE 1 TABLET DAILY", (170, 62), cv2.FONT_HERSHEY_PLAIN, 0.9, (60, 60, 60), 1, cv2.LINE_AA)
    return tex


def bottle_sprite(spec, rng, turn):
    """Bottle image with alpha. turn in [0,1): rotation about the bottle's own axis."""
    H = int(260 * spec["h"]); Wd = 140
    cap_h = 50
    img = np.zeros((H + cap_h, Wd, 3), np.uint8)
    alpha = np.zeros((H + cap_h, Wd), np.uint8)
    # cylinder shading
    xs = np.linspace(-1, 1, Wd)
    shade = (0.55 + 0.45 * np.sqrt(np.clip(1 - xs ** 2, 0, 1)))[None, :, None]
    body = np.full((H, Wd, 3), spec["body"], np.float32)
    # translucent amber: a bit of the label's back shows through
    tex = label_texture(spec, rng)
    tw = tex.shape[1] * 2
    wrap = np.concatenate([tex, np.full_like(tex, spec["body"])], 1)   # label covers half the circumference
    # map each column to an angle on the cylinder, shifted by `turn`
    ang = (np.arcsin(np.clip(xs, -1, 1)) / np.pi + 0.5) * 0.5 + turn
    cols = ((ang % 1.0) * tw).astype(int) % tw
    lab = wrap[:, cols]
    lab = cv2.resize(lab, (Wd, int(H * 0.55)))
    y0 = int(H * 0.25)
    body[y0:y0 + lab.shape[0]] = lab
    body = np.clip(body * shade, 0, 255).astype(np.uint8)
    img[cap_h:] = body
    cap = np.full((cap_h, Wd - 16, 3), spec["cap"], np.float32)
    for x in range(0, cap.shape[1], 6):             # child-proof ridges
        cap[:, x:x + 2] *= 0.8
    cap = np.clip(cap * shade[:, 8:-8], 0, 255).astype(np.uint8)
    img[:cap_h, 8:-8] = cap
    alpha[cap_h:, :] = 255
    alpha[:cap_h, 8:-8] = 255
    return img, alpha


def background(rng, size):
    bg = np.zeros((size, size, 3), np.float32)
    c1, c2 = rng.uniform(40, 220, 3), rng.uniform(40, 220, 3)
    g = np.linspace(0, 1, size)[:, None, None]
    bg[:] = c1 * (1 - g) + c2 * g
    for _ in range(rng.integers(2, 8)):    # cupboard doors, tiles, a kettle...
        x0, y0 = rng.integers(0, size, 2)
        x1, y1 = x0 + rng.integers(10, size // 2), y0 + rng.integers(10, size // 2)
        cv2.rectangle(bg, (int(x0), int(y0)), (int(x1), int(y1)), rng.uniform(20, 240, 3).tolist(), -1)
    bg += rng.normal(0, 6, bg.shape)
    return np.clip(bg, 0, 255).astype(np.uint8)


def render(spec, rng, mode="test", size=224):
    """One hand crop. spec=None renders an empty hand."""
    hard = mode == "test"
    img = background(rng, size)
    skin = SKIN[rng.integers(len(SKIN))]
    scale = rng.uniform(0.45, 0.85) if hard else rng.uniform(0.6, 0.8)
    if spec is not None:
        spr, a = bottle_sprite(spec, rng, rng.uniform(0, 1) if hard else rng.uniform(0, 0.5))
        s = scale * size / spr.shape[0]
        spr = cv2.resize(spr, None, fx=s, fy=s)
        a = cv2.resize(a, None, fx=s, fy=s)
        tilt = rng.uniform(-70, 70) if (hard and rng.random() < 0.4) else rng.uniform(-20, 20)
        h, w = spr.shape[:2]
        D = int(np.hypot(h, w)) + 2
        canvas = np.zeros((D, D, 3), np.uint8); ca = np.zeros((D, D), np.uint8)
        oy, ox = (D - h) // 2, (D - w) // 2
        canvas[oy:oy + h, ox:ox + w] = spr; ca[oy:oy + h, ox:ox + w] = a
        M = cv2.getRotationMatrix2D((D / 2, D / 2), tilt, 1.0)
        canvas = cv2.warpAffine(canvas, M, (D, D)); ca = cv2.warpAffine(ca, M, (D, D))
        jitter = 0.25 if hard else 0.08
        cx = int(size / 2 + rng.uniform(-jitter, jitter) * size); cy = int(size / 2 + rng.uniform(-jitter, jitter) * size)
        x0, y0 = cx - D // 2, cy - D // 2
        sx0, sy0 = max(0, -x0), max(0, -y0)
        dx0, dy0 = max(0, x0), max(0, y0)
        dx1, dy1 = min(size, x0 + D), min(size, y0 + D)
        if dx1 > dx0 and dy1 > dy0:
            patch = canvas[sy0:sy0 + dy1 - dy0, sx0:sx0 + dx1 - dx0]
            pa = ca[sy0:sy0 + dy1 - dy0, sx0:sx0 + dx1 - dx0, None] / 255.0
            img[dy0:dy1, dx0:dx1] = (patch * pa + img[dy0:dy1, dx0:dx1] * (1 - pa)).astype(np.uint8)
        hand_c = (cx + rng.integers(-20, 20), cy + rng.integers(-10, 30))
    else:
        hand_c = (size // 2 + rng.integers(-40, 40), size // 2 + rng.integers(-40, 40))
    # hand: palm + fingers wrapped around the bottle
    n_f = rng.integers(2, 5) if (hard or spec is None) else rng.integers(1, 3)
    cv2.ellipse(img, (int(hand_c[0] + rng.integers(-30, 30)), int(hand_c[1] + 50)), (int(size * 0.18), int(size * 0.12)),
                float(rng.uniform(0, 180)), 0, 360, skin, -1)
    for i in range(n_f):
        fx = int(hand_c[0] + rng.integers(-45, 45)); fy = int(hand_c[1] + rng.integers(-40, 40))
        cv2.ellipse(img, (fx, fy), (int(rng.integers(30, 60)), int(rng.integers(9, 15))), float(rng.uniform(-30, 30)), 0, 360,
                    tuple(int(c * rng.uniform(0.9, 1.05)) for c in skin), -1)
    # camera effects
    f = img.astype(np.float32)
    gain = rng.uniform(0.55, 1.4) if hard else rng.uniform(0.85, 1.15)
    temp = rng.uniform(0.85, 1.15, 3) if hard else rng.uniform(0.95, 1.05, 3)
    f = f * gain * temp
    f = 255 * (np.clip(f, 0, 255) / 255) ** rng.uniform(0.8, 1.25)
    if hard and rng.random() < 0.5:
        k = int(rng.integers(3, 11))
        ker = np.zeros((k, k), np.float32)
        ker[k // 2] = 1.0 / k
        ker = cv2.warpAffine(ker, cv2.getRotationMatrix2D((k / 2, k / 2), float(rng.uniform(0, 180)), 1.0), (k, k))
        f = cv2.filter2D(f, -1, ker / max(ker.sum(), 1e-6))
    f += rng.normal(0, rng.uniform(2, 9) if hard else 2, f.shape)
    img = np.clip(f, 0, 255).astype(np.uint8)
    q = int(rng.integers(35, 85)) if hard else 90
    img = cv2.imdecode(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])[1], 1)
    return img
