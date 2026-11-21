"""Fast checks for Part C.  Run:  .venv/bin/python -m pytest -q tests   (or python tests/test_part_c.py)"""
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from sim.pose_sim import simulate  # noqa: E402
from squint_vision.bottles import EMPTY, BottleTracker, Gallery  # noqa: E402
from squint_vision.intake import FeatureStream, IntakeDetector, load_model  # noqa: E402


def run(kind, armed, seed):
    s = simulate(kind, np.random.default_rng(seed), fps=15)
    det = IntakeDetector(model=load_model())
    evs = []
    for t, k in zip(s["t"], s["kps"]):
        evs += [(float(t), e) for e in det.update(float(t), k, armed)]
    return s, evs


def test_intake_fires_before_mouth_on_most_intakes():
    early = 0
    for seed in range(20):
        s, evs = run("bottle_to_mouth_slow", True, seed)
        starts = [t for t, e in evs if e["type"] == "intake_start"]
        early += bool(starts) and starts[0] < s["t_contact"]
    assert early >= 15, early


def test_no_stop_without_a_bottle():
    for seed in range(10):
        _, evs = run("bottle_to_mouth", False, seed)
        assert not evs, "unarmed intake must never send intake_start"


def test_idle_and_wave_never_fire():
    for kind in ("idle", "wave", "reach_shelf"):
        for seed in range(5):
            _, evs = run(kind, True, seed)
            assert not evs, kind


def test_intake_done_follows_start():
    s, evs = run("bottle_to_mouth_slow", True, 3)
    types = [e["type"] for _, e in evs]
    if "intake_done" in types:
        assert types.index("intake_start") < types.index("intake_done")


def test_feature_stream_sticky_hand():
    s = simulate("idle", np.random.default_rng(1), fps=15)
    fs, sides = FeatureStream(), set()
    for t, k in zip(s["t"], s["kps"]):
        fs.update(float(t), k)
        sides.add(fs.side)
    assert len(sides - {None}) == 1, sides


def test_gallery_open_set():
    g = Gallery(directory="/nonexistent", thresholds={"accept": 0.8, "margin": 0.05, "k": 1})
    a, b = np.eye(4, dtype=np.float32)[0], np.eye(4, dtype=np.float32)[1]
    g.add("warfarin", [a], save=False)
    g.add(EMPTY, [b], save=False)
    assert g.classify(a)[0] == "warfarin"
    assert g.classify(b)[0] == "none"
    q = (a + b) / np.linalg.norm(a + b)            # halfway: must not guess
    assert g.classify(q)[0] == "unknown"


def test_tracker_needs_agreement():
    tr = BottleTracker()
    assert tr.update("warfarin", 0.9) is None      # one frame is not enough
    for _ in range(3):
        r = tr.update("warfarin", 0.9)
    assert r == ("warfarin", 0.9)
    assert tr.update("unknown", 0.5) is None       # one blurry frame does not flip it


def test_bus_roundtrip():
    import bus
    got = []
    bus.on("test_ping", got.append)
    bus.send({"type": "test_ping", "x": 1})
    t = time.time()
    while not got and time.time() - t < 1:
        time.sleep(0.01)
    assert got and got[0]["x"] == 1 and "time" in got[0]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
