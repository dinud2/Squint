"""C4/C9: tune and test open-set bottle recognition on simulated hand crops.

Writes models/bottle_thresholds.json and reports/bottle_report.json.
Safety metric = WRONG ACCEPT: naming a bottle that is not the one in her hand.
"""
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from sim.bottle_sim import BOTTLES, UNKNOWN, render  # noqa: E402
from squint_vision.bottles import EMPTY, THRESH_FILE, BottleTracker, Embedder, Gallery  # noqa: E402

N_ENROL = 15


def embed_set(emb, rng, n_known, n_unknown, n_empty, mode="test"):
    items = []
    for med, spec in BOTTLES.items():
        items += [(med, emb(render(spec, rng, mode))) for _ in range(n_known)]
    for med, spec in UNKNOWN.items():
        items += [("unknown:" + med, emb(render(spec, rng, mode))) for _ in range(n_unknown)]
    items += [("none", emb(render(None, rng, mode))) for _ in range(n_empty)]
    return items


def frame_metrics(gal, items):
    ok = wrong = 0
    per = {}
    for truth, e in items:
        pred, _, _ = gal.classify(e)
        want = truth if truth in BOTTLES else ("none" if truth == "none" else "unknown")
        good = pred == want or (want == "unknown" and pred == "none") or (want == "none" and pred == "unknown")
        # naming a medication that is not in her hand is the only dangerous error
        bad = pred in BOTTLES and pred != truth
        ok += good; wrong += bad
        d = per.setdefault(truth, {"n": 0, "correct": 0, "wrong_accept": 0, "said_unknown": 0})
        d["n"] += 1; d["correct"] += good; d["wrong_accept"] += bad; d["said_unknown"] += pred == "unknown"
    known = [x for x in items if x[0] in BOTTLES]
    acc_known = np.mean([gal.classify(e)[0] == t for t, e in known])
    return {"correct": ok / len(items), "wrong_accept": wrong / len(items), "known_recognised": float(acc_known),
            "per_class": {k: {kk: (round(v / d["n"], 3) if kk != "n" else v) for kk, v in d.items()} for k, d in per.items()}}


def seq_metrics(gal, rng, emb, n_seq=40, frames=10):
    """Pick-ups: 10 frames each, through the 4-of-5 tracker, like vision_main."""
    res = {"right": 0, "wrong": 0, "unknown_or_none": 0, "n": 0}
    unk_wrong = unk_n = 0
    cand_hit = cand_n = 0
    cand_sizes = []
    for med, spec in list(BOTTLES.items()) + [("unknown:" + k, v) for k, v in UNKNOWN.items()]:
        for _ in range(n_seq if med in BOTTLES else n_seq // 2):
            tr = BottleTracker()
            said = set()
            counts = {}
            for _ in range(frames):
                lab, conf, sc = gal.classify(emb(render(spec, rng, "test")))
                for c in gal.candidates(sc):
                    counts[c] = counts.get(c, 0) + 1
                ch = tr.update(lab, conf)
                if ch:
                    said.add(ch[0])
            cands = {c for c, n in counts.items() if n >= 2}
            if med in BOTTLES and "unknown" in said and med not in said:
                cand_n += 1
                cand_hit += med in cands
                cand_sizes.append(len(cands))
            named = {s for s in said if s in BOTTLES}
            if med in BOTTLES:
                res["n"] += 1
                if named - {med}:
                    res["wrong"] += 1
                elif med in named:
                    res["right"] += 1
                else:
                    res["unknown_or_none"] += 1
            else:
                unk_n += 1
                unk_wrong += bool(named)
    return {"enrolled_pickups": res["n"], "named_right": res["right"] / res["n"], "named_wrong": res["wrong"] / res["n"],
            "only_unknown": res["unknown_or_none"] / res["n"],
            "unknown_pickups": unk_n, "unknown_named_as_a_med": unk_wrong / max(unk_n, 1),
            "when_unknown_truth_in_candidates": cand_hit / max(cand_n, 1),
            "mean_candidates": float(np.mean(cand_sizes)) if cand_sizes else 0.0}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="ONNX embedder (default: trained if present)")
    ap.add_argument("--no-save", action="store_true", help="don't overwrite thresholds")
    a = ap.parse_args()
    t0 = time.time()
    emb = Embedder(a.model) if a.model else Embedder()
    print("embedder:", os.path.basename(a.model) if a.model else "default")
    rng = np.random.default_rng(10)
    gal = Gallery(directory=os.path.join(HERE, "data", "sim_gallery"))
    for med, spec in BOTTLES.items():
        gal.add(med, [emb(render(spec, rng, "enrol")) for _ in range(N_ENROL)], save=False)
    gal.add(EMPTY, [emb(render(None, rng, "enrol")) for _ in range(N_ENROL)], save=False)
    print(f"enrolled {len(gal.items)} classes ({time.time()-t0:.1f}s)")
    val = embed_set(emb, np.random.default_rng(11), 80, 25, 60)
    test = embed_set(emb, np.random.default_rng(12), 150, 40, 100)
    print(f"embedded val {len(val)} / test {len(test)} ({time.time()-t0:.1f}s)")

    grid = []
    for acc in np.round(np.arange(0.40, 0.96, 0.02), 2):
        for mar in [0.0, 0.01, 0.02, 0.03, 0.05, 0.07, 0.1]:
            gal.t = {"accept": float(acc), "margin": mar, "k": 3}
            m = frame_metrics(gal, val)
            grid.append((acc, mar, m["known_recognised"], m["wrong_accept"]))
    grid = np.array(grid)
    # safest setting that still recognises most bottles: wrong accepts <= 1% of frames, then max recognition
    ok = grid[grid[:, 3] <= 0.01]
    best = ok[np.argmax(ok[:, 2])] if len(ok) else grid[np.argmin(grid[:, 3])]
    th = {"accept": float(best[0]), "margin": float(best[1]), "k": 3}
    gal.t = th
    print(f"chosen on val: accept={th['accept']} margin={th['margin']} (val recognised {best[2]:.3f}, wrong {best[3]:.4f})")
    ft = frame_metrics(gal, test)
    sq = seq_metrics(gal, np.random.default_rng(13), emb)
    gal.t = {"accept": 0.0, "margin": 0.0, "k": 3}
    closed = frame_metrics(gal, [x for x in test if x[0] in BOTTLES])
    print(f"TEST frames: known recognised {ft['known_recognised']:.3f}  wrong accept {ft['wrong_accept']:.4f}")
    print(f"TEST pickups: {sq}")
    print(f"closed-set (no thresholds) top-1 on enrolled bottles: {closed['known_recognised']:.3f}")
    for k, v in ft["per_class"].items():
        print(f"   {k:32s} {v}")
    if a.no_save:
        return
    with open(THRESH_FILE, "w") as f:
        json.dump(th, f)
    os.makedirs(os.path.join(HERE, "reports"), exist_ok=True)
    with open(os.path.join(HERE, "reports", "bottle_report.json"), "w") as f:
        json.dump({"thresholds": th, "test_frames": ft, "test_pickups": sq, "closed_set_top1": closed["known_recognised"],
                   "grid_val": grid.tolist()}, f, indent=1)
    print(f"done ({time.time()-t0:.1f}s)")


if __name__ == "__main__":
    main()
