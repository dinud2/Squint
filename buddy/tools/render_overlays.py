"""Overlays and Squint's voice for the demo-video takes (tools/record_webcam.py).

    python tools/render_overlays.py                       # every take in ~/Videos/squint
    python tools/render_overlays.py ~/Videos/squint/take_20261122-022121.mp4 --shift -0.3

For each take_<time>.mp4 (+ its .jsonl, what Squint recognised) this writes, next to it:
  take_<time>_overlay.mov   overlays ONLY, transparent (ProRes 4444 with alpha), 1920x1088, the
                            take's frame rate and length: lay it over the take in the editor
  take_<time>_voice.wav     one track the length of the take: Squint's spoken lines (same Piper
                            voice and chime as live) where it said them, silence elsewhere
  take_<time>_preview.mp4   the take upscaled to 1920x1088 with the overlays and voice burned in,
                            to check timing quickly

Overlays, in the Squint style (the app's colours, M PLUS Rounded like the Tab5 face, thin
rounded shapes, dark translucent pills):
  bottle label   a rounded box round the bottle once Squint named it, and a pill
                 "Tylenol · Dinu's" (blue: the person at the counter's own medicine; amber:
                 someone else's; grey: "Omega 3-6-9 · Not in the app")
  at the counter top-left tag with who Squint sees: "Dinu", "Kathy", "Unknown"
  status moments short centred badges: "Hand to mouth ✓", "Taken", "Not registered",
                 "Not yours"

--shift moves every overlay and voice line in time (s, negative = earlier; default -0.3): Squint's
readings come ~0.3 s after the real moment, its decisions a little later (3 of 4 checks).
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import urllib.request

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")
W, H = 1920, 1088                 # 2x the camera's 960x544: crisp text when the editor is at 1080p
SRC_W, SRC_H = 960, 544
S = W / SRC_W

# The app's palette (ios/Shared/Theme.swift, dark variants: they sit on video)
BLUE = (0x5A, 0xAD, 0xF5)
AMBER = (0xF0, 0xA0, 0x30)
GREEN = (0x4C, 0xCB, 0x8E)
GREY = (0x8E, 0x97, 0xA3)
INK = (0x0E, 0x11, 0x16)          # pill background (at ~72 % opacity)
WHITE = (0xF1, 0xF4, 0xF8)

MEDS = {  # fallback if the Pi can't be asked: id -> (name, owner id)
    "advil": ("Advil", "kathy"), "motrin": ("Motrin", "dinu"),
    "tylenol": ("Tylenol", "dinu"), "vitamind": ("Vitamin D", "kathy")}
NOT_IN_APP = {"omega369": "Omega 3-6-9"}
FADE = 0.22                       # s, every element fades in and out
GAP = 0.8                         # s between bottle readings still drawn as one continuous box


def font(weight, size):
    return ImageFont.truetype(os.path.join(FONTS, f"MPLUSRounded1c-{weight}-latin.ttf"), int(size))


def meds_from_pi(pi):
    try:
        ms = json.load(urllib.request.urlopen(f"http://{pi}:8081/medications", timeout=3))
        return {m["id"]: (m["name"], m["for"]) for m in ms}
    except Exception:
        return dict(MEDS)


# ---------------------------------------------------------------- timeline from the .jsonl
def load(jsonl):
    rows = [json.loads(line) for line in open(jsonl)]
    states = [r for r in rows if r.get("type") == "state"]
    events = [(r["t"], r["event"]) for r in rows if "event" in r]
    end = max((r["t"] for r in rows), default=0)
    return states, events, end


def build(states, events, meds, shift, duration):
    """-> lists of timed elements: bottles, counter tags, badges, voice lines."""
    bottles, tags, badges, lines = [], [], [], []
    # who is at the counter, over time (people_present events; 'unknown' only when nobody known)
    who, since = None, 0.0
    for t, e in events:
        if e["type"] != "people_present":
            continue
        now = ", ".join(p.capitalize() for p in e.get("people") or []) or ("Unknown" if e.get("unknown") else None)
        if now != who:
            if who:
                tags.append({"t0": since, "t1": t, "text": who})
            who, since = now, t
    if who:
        tags.append({"t0": since, "t1": duration - shift, "text": who})

    def at_counter(t):
        names = [x for x in tags if x["t0"] <= t < x["t1"]]
        return names[-1]["text"].lower().split(", ") if names else []

    for t, e in events:
        typ = e["type"]
        if typ == "bottle_shown":
            b = e["bottle"]
            here = at_counter(t)
            if b in NOT_IN_APP:
                text, col = f"{NOT_IN_APP[b]}  ·  Not in the app", GREY
                badges.append({"t0": t, "t1": t + 2.2, "text": "Not registered", "col": GREY})
            elif b in meds:
                name, owner = meds[b]
                mine = owner in here
                text = f"{name}  ·  {owner.capitalize()}'s"
                col = BLUE if (mine or not here) else AMBER
                if here and not mine:
                    badges.append({"t0": t, "t1": t + 2.2, "text": "Not yours", "col": AMBER})
            else:
                continue
            # Once named, the box shows whenever the Pi reads this bottle (until another bottle
            # is named): readings less than GAP s apart are one span, so it doesn't flicker.
            nxt = next((tt for tt, ee in events if tt > t and ee["type"] == "bottle_shown" and ee["bottle"] != b),
                       duration - shift)
            reads = [(s_["t"], s_["box"]) for s_ in states
                     if t - 1.0 <= s_["t"] < nxt and s_.get("bottle") == b and any(s_.get("box") or [])]
            spans = []
            for r in reads:
                if spans and r[0] - spans[-1][-1][0] <= GAP:
                    spans[-1].append(r)
                else:
                    spans.append([r])
            for sp in spans:
                if sp[-1][0] < t - 0.1 and len(sp) < 2:
                    continue
                bottles.append({"t0": max(sp[0][0], t - 0.6), "t1": max(sp[-1][0] + 0.45, t + 1.2),
                                "track": sp, "text": text, "col": col})
        elif typ == "intake" and e.get("confidence", 0) >= 0.75:
            badges.append({"t0": t, "t1": t + 2.0, "text": "Hand to mouth", "col": BLUE, "check": True})
        elif typ == "dose_taken":
            badges.append({"t0": t + 0.1, "t1": t + 2.4, "text": "Taken", "col": GREEN, "check": True})
        elif typ == "say":
            lines.append((t, e["text"]))
    for group in (bottles, tags, badges):
        for x in group:
            x["t0"] += shift
            x["t1"] += shift
    # badges must not overlap: each starts after the previous one has gone
    badges.sort(key=lambda b: b["t0"])
    for a, b in zip(badges, badges[1:]):
        if b["t0"] < a["t1"]:
            a["t1"] = b["t0"]
    lines = [(t + shift, s) for t, s in lines]
    return bottles, tags, badges, lines


# ---------------------------------------------------------------- drawing
def fade(t, t0, t1):
    if t < t0 or t >= t1:
        return 0.0
    return max(0.0, min(1.0, (t - t0) / FADE, (t1 - t) / FADE))


def box_at(track, t):
    """Bottle box at time t: the Pi's label patch (interpolated between readings), grown to the
    whole bottle, in output pixels."""
    if not track:
        return None
    if t <= track[0][0]:
        bx = track[0][1]
    elif t >= track[-1][0]:
        bx = track[-1][1]
    else:
        i = next(k for k in range(1, len(track)) if track[k][0] >= t)
        (ta, a), (tb, b) = track[i - 1], track[i]
        f = (t - ta) / max(1e-6, tb - ta)
        f = f * f * (3 - 2 * f)
        bx = [a[j] + (b[j] - a[j]) * f for j in range(4)]
    x0, y0, x1, y1 = bx
    cx, cy, s = (x0 + x1) / 2, (y0 + y1) / 2, max(x1 - x0, y1 - y0)
    hw, hh = max(s * 1.05, 34), max(s * 1.45, 48)           # the label sits on a taller bottle
    out = [max(4, cx - hw), max(4, cy - hh), min(SRC_W - 4, cx + hw), min(SRC_H - 4, cy + hh)]
    return [v * S for v in out]


def with_alpha(col, a):
    return (*col, int(255 * a))


def pill_width(d, text, f):
    asc, desc = f.getmetrics()
    return 26 * 2 + (asc + desc) * 0.62 + 16 + d.textlength(text, font=f)


def pill(d, x, y, text, col, a, f, dot=True, check=False, anchor="lt"):
    """Dark translucent pill with a coloured dot (or check) and white text. Returns its box."""
    pad_x, pad_y, gap = 26, 14, 16
    tw = d.textlength(text, font=f)
    asc, desc = f.getmetrics()
    th = asc + desc
    icon = th * 0.62 if (dot or check) else 0
    w = pad_x * 2 + icon + (gap if icon else 0) + tw
    h = pad_y * 2 + th
    if anchor == "mt":
        x -= w / 2
    box = [x, y, x + w, y + h]
    d.rounded_rectangle(box, radius=h / 2, fill=(*INK, int(184 * a)), outline=with_alpha(col, 0.55 * a), width=2)
    ix, iy = x + pad_x, y + h / 2
    if check:
        r = icon / 2
        d.ellipse([ix, iy - r, ix + 2 * r, iy + r], fill=with_alpha(col, a))
        d.line([(ix + r * 0.55, iy + r * 0.02), (ix + r * 0.88, iy + r * 0.36), (ix + r * 1.45, iy - r * 0.34)],
               fill=(*INK, int(255 * a)), width=max(3, int(r * 0.26)), joint="curve")
    elif dot:
        r = icon * 0.3
        d.ellipse([ix + icon / 2 - r, iy - r, ix + icon / 2 + r, iy + r], fill=with_alpha(col, a))
    d.text((x + pad_x + icon + (gap if icon else 0), y + pad_y - 2), text, font=f, fill=with_alpha(WHITE, a))
    return box


def render(t, bottles, tags, badges, fonts):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f_label, f_tag, f_badge, f_small = fonts
    for b in bottles:
        a = fade(t, b["t0"], b["t1"])
        bx = box_at(b["track"], t) if a > 0 else None
        if not bx:
            continue
        d.rounded_rectangle(bx, radius=28, outline=with_alpha(b["col"], 0.95 * a), width=5)
        ly = bx[1] - 74 if bx[1] > 90 else bx[3] + 14
        half = pill_width(d, b["text"], f_label) / 2           # centred on the box, kept on screen
        lx = min(max(16 + half, (bx[0] + bx[2]) / 2), W - 16 - half)
        pill(d, lx, ly, b["text"], b["col"], a, f_label, anchor="mt")
    for g in tags:
        a = fade(t, g["t0"], g["t1"])
        if a <= 0:
            continue
        col = GREY if g["text"] == "Unknown" else BLUE
        d.text((40, 34), "AT THE COUNTER", font=f_small, fill=with_alpha(WHITE, 0.75 * a))
        pill(d, 36, 70, g["text"], col, a, f_tag)
    for b in badges:
        a = fade(t, b["t0"], b["t1"])
        if a <= 0:
            continue
        rise = (1 - min(1.0, (t - b["t0"]) / FADE)) * 18      # a small lift as it appears
        pill(d, W / 2, H - 170 + rise, b["text"], b["col"], a, f_badge, dot=not b.get("check"),
             check=b.get("check", False), anchor="mt")
    return img


# ---------------------------------------------------------------- voice track
def home_dir():
    repo = os.path.dirname(os.path.dirname(HERE))
    for h in (os.path.join(repo, "home"), "/home/dinu/Documents/hackwestern/home"):
        if os.path.isdir(os.path.join(h, "voices")) and os.path.exists(os.path.join(h, ".venv/bin/python")):
            return h
    return None


def voice_track(lines, duration, out):
    """One WAV, the take's length, Squint's lines at their times (Piper voice + chime, as live)."""
    rate = 48000
    files = []
    home = home_dir()
    if lines and home:
        code = ("import json,sys,voice\n"
                "print(json.dumps([voice.synth(t) for t in json.loads(sys.argv[1])]))")
        r = subprocess.run([os.path.join(home, ".venv/bin/python"), "-c", code, json.dumps([s for _, s in lines])],
                           cwd=home, capture_output=True, text=True)
        if r.returncode == 0:
            paths = json.loads(r.stdout.strip().splitlines()[-1])
            files = [(t, os.path.splitext(p)[0] + ".wav") for (t, _), p in zip(lines, paths)]
        else:
            print("  voice: could not synthesise:", r.stderr.strip()[-300:])
    elif lines:
        print("  voice: no Piper voice found (home/voices); the track is silent")
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-t", f"{duration:.3f}",
           "-i", f"anullsrc=r={rate}:cl=stereo"]
    for _, f in files:
        cmd += ["-i", f]
    if files:
        parts = [f"[{i + 1}:a]aresample={rate},aformat=channel_layouts=stereo,adelay={max(0, int(t * 1000))}:all=1[v{i}]"
                 for i, (t, _) in enumerate(files)]
        mix = "[0:a]" + "".join(f"[v{i}]" for i in range(len(files)))
        flt = ";".join(parts) + f";{mix}amix=inputs={len(files) + 1}:normalize=0:duration=first[a]"
        cmd += ["-filter_complex", flt, "-map", "[a]"]
    cmd += ["-c:a", "pcm_s16le", out]
    subprocess.run(cmd, check=True)
    return len(files)


# ---------------------------------------------------------------- one take
def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=r_frame_rate:format=duration", "-of", "json", path], capture_output=True, text=True)
    j = json.loads(r.stdout)
    num, den = j["streams"][0]["r_frame_rate"].split("/")
    return float(j["format"]["duration"]), float(num) / float(den)


def do_take(mp4, meds, shift, extra=()):
    base = os.path.splitext(mp4)[0]
    jsonl = base + ".jsonl"
    if not os.path.exists(jsonl):
        print(f"skip {mp4}: no {os.path.basename(jsonl)}")
        return
    duration, fps = probe(mp4)
    states, events, _ = load(jsonl)
    bottles, tags, badges, lines = build(states, events, meds, shift, duration)
    lines = sorted(lines + list(extra))         # --say: added lines, at video time (no shift)
    print(f"{os.path.basename(mp4)}: {duration:.1f} s @ {fps:g} fps | bottles {len(bottles)}, "
          f"counter tags {len(tags)}, badges {[b['text'] for b in badges]}, lines {[s for _, s in lines]}")
    fonts = (font("Bold", 38), font("Bold", 40), font("Bold", 42), font("Medium", 22))
    n = int(round(duration * fps))
    mov = base + "_overlay.mov"
    ff = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba",
                           "-s", f"{W}x{H}", "-r", f"{fps:g}", "-i", "-", "-c:v", "prores_ks", "-profile:v", "4444",
                           "-pix_fmt", "yuva444p10le", "-vendor", "apl0", mov], stdin=subprocess.PIPE)
    blank = np.zeros((H, W, 4), np.uint8).tobytes()
    for i in range(n):
        t = i / fps
        active = any(fade(t, x["t0"], x["t1"]) > 0 for g in (bottles, tags, badges) for x in g)
        ff.stdin.write(render(t, bottles, tags, badges, fonts).tobytes() if active else blank)
    ff.stdin.close()
    ff.wait()
    wav = base + "_voice.wav"
    said = voice_track(lines, duration, wav)
    prev = base + "_preview.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", mp4, "-i", mov, "-i", wav, "-filter_complex",
                    f"[0:v]scale={W}:{H}:flags=lanczos[v];[v][1:v]overlay=format=auto[o]", "-map", "[o]", "-map", "2:a",
                    "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", prev], check=True)
    print(f"  -> {os.path.basename(mov)}, {os.path.basename(wav)} ({said} lines), {os.path.basename(prev)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("takes", nargs="*", help="take_*.mp4 (default: every take in --dir)")
    ap.add_argument("--dir", default=os.path.expanduser("~/Videos/squint"))
    ap.add_argument("--shift", type=float, default=-0.3,
                    help="move overlays and voice by this many seconds (Squint reads ~0.3 s after the moment)")
    ap.add_argument("--pi", default="172.20.10.9", help="asked for the medication list (owners)")
    ap.add_argument("--say", action="append", default=[], metavar="SECONDS|TEXT",
                    help="add a spoken line at this time of the video, e.g. '2.4|Hi Dinu.' (repeatable)")
    a = ap.parse_args()
    takes = a.takes or sorted(f for f in glob.glob(os.path.join(a.dir, "take_*.mp4"))
                              if not f.endswith(("_preview.mp4",)))
    if not takes:
        sys.exit(f"no takes in {a.dir}")
    meds = meds_from_pi(a.pi)
    extra = []
    for x in a.say:
        t, _, text = x.partition("|")
        extra.append((float(t), text.strip()))
    for mp4 in takes:
        do_take(mp4, meds, a.shift, extra)


if __name__ == "__main__":
    main()
