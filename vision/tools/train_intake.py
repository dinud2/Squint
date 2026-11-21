"""C6: train the intake-anticipation model.

    python tools/train_intake.py --sim            # simulated data only
    python tools/train_intake.py --clips data/clips_pose  [--sim]   # real clips (+ sim)

Writes models/intake_model.json (weights + threshold + consec) and
reports/intake_*.json with validation and test numbers.
"""
import argparse
import glob
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from sim.pose_sim import make_dataset  # noqa: E402
from squint_vision import intake as I  # noqa: E402

POS_FROM_ONSET = 0.12   # s after the hand starts moving
POS_BEFORE_CONTACT = 0.03
POS_MAX_LEAD = 1.0
HARD_NEG_W = 5.0        # negatives done with a bottle in hand are the ones that can sound STOP      # windows more than 1 s before contact are not "imminent"


# ------------------------------------------------------------ data
def load_clips(folder):
    seqs = []
    for f in sorted(glob.glob(os.path.join(folder, "*.npz"))):
        z = np.load(f, allow_pickle=True)
        meta = json.loads(str(z["meta"]))
        seqs.append({"t": z["t"], "kps": z["kps"], "armed": z["armed"], **meta})
    return seqs


def trace(seq):
    """Per frame: t, window features, hand-mouth distance (same FeatureStream as live)."""
    fs, T, X, D = I.FeatureStream(), [], [], []
    for t, k in zip(seq["t"], seq["kps"]):
        x, ff = fs.update(float(t), k)
        if x is None:
            continue
        T.append(float(t)); X.append(x); D.append(ff["d"])
    return np.array(T), np.array(X, np.float32).reshape(-1, len(I.FEATURE_NAMES)), np.array(D)


def labels(seq, T):
    y = np.zeros(len(T), np.float32)
    w = np.ones(len(T), np.float32)
    if seq["label"]:
        tc, ton = seq["t_contact"], seq["t_on"]
        pos = (T >= ton + POS_FROM_ONSET) & (T <= tc - POS_BEFORE_CONTACT) & (T >= tc - POS_MAX_LEAD)
        y[pos] = 1
        w[(T > tc - POS_BEFORE_CONTACT)] = 0          # at/after the mouth: don't care
        w[(T >= ton) & (T < ton + POS_FROM_ONSET)] = 0  # first 120 ms of motion: ambiguous
        w[(T >= ton) & (T < tc - POS_MAX_LEAD)] = 0
    elif bool(np.any(seq["armed"])) and seq["kind"] != "aborted_raise":
        w[:] = HARD_NEG_W
    elif seq["kind"] == "aborted_raise":
        # lifting an already-taken bottle toward the mouth SHOULD warn; don't punish it
        w[T >= seq["t_on"]] = 0
    return y, w


def build(seqs):
    Xs, ys, ws, traces = [], [], [], []
    for s in seqs:
        T, X, D = trace(s)
        y, w = labels(s, T)
        Xs.append(X); ys.append(y); ws.append(w)
        traces.append((T, X, D))
    return np.concatenate(Xs), np.concatenate(ys), np.concatenate(ws), traces


# ------------------------------------------------------------ models (numpy + Adam)
def train(X, y, w, hidden=0, epochs=400, lr=0.02, l2=1e-4, seed=0):
    rng = np.random.default_rng(seed)
    mu, sd = X.mean(0), X.std(0) + 1e-6
    Xn = (X - mu) / sd
    pos_w = (w * (1 - y)).sum() / max((w * y).sum(), 1)
    sw = w * np.where(y > 0, pos_w, 1.0)
    sw = sw / sw.mean()
    dims = [X.shape[1]] + ([hidden] if hidden else []) + [1]
    Ws = [rng.normal(0, 1 / np.sqrt(a), (a, b)) for a, b in zip(dims[:-1], dims[1:])]
    bs = [np.zeros(b) for b in dims[1:]]
    params = Ws + bs
    m = [np.zeros_like(p) for p in params]
    v = [np.zeros_like(p) for p in params]
    n = len(Xn)
    bsz = 4096
    step = 0
    for ep in range(epochs):
        idx = rng.permutation(n)
        for st in range(0, n, bsz):
            j = idx[st:st + bsz]
            xb, yb, wb = Xn[j], y[j], sw[j]
            hs = [xb]
            h = xb
            for i in range(len(Ws)):
                h = h @ Ws[i] + bs[i]
                if i < len(Ws) - 1:
                    h = np.tanh(h)
                hs.append(h)
            p = 1 / (1 + np.exp(-hs[-1][:, 0]))
            g = ((p - yb) * wb / len(j))[:, None]
            gW, gb = [None] * len(Ws), [None] * len(Ws)
            for i in reversed(range(len(Ws))):
                gW[i] = hs[i].T @ g + l2 * Ws[i]
                gb[i] = g.sum(0)
                if i > 0:
                    g = (g @ Ws[i].T) * (1 - hs[i] ** 2)
            grads = gW + gb
            step += 1
            for k, (pa, gr) in enumerate(zip(params, grads)):
                m[k] = 0.9 * m[k] + 0.1 * gr
                v[k] = 0.999 * v[k] + 0.001 * gr * gr
                mh, vh = m[k] / (1 - 0.9 ** step), v[k] / (1 - 0.999 ** step)
                pa -= lr * mh / (np.sqrt(vh) + 1e-8)
        if ep % 100 == 0:
            lr *= 0.6
    return {"kind": "mlp" if hidden else "logreg", "mu": mu.tolist(), "sd": sd.tolist(),
            "W": [x.tolist() for x in Ws], "b": [x.tolist() for x in bs],
            "features": I.FEATURE_NAMES}


# ------------------------------------------------------------ fast sequence-level replay
def replay(T, P, D, armed_fn, thr, consec, hold=8.0):
    """Same state machine as IntakeDetector, on precomputed probabilities."""
    fires, state, hits, last_arm, tcon = [], "idle", 0, -1e9, None
    for t, p, d in zip(T, P, D):
        if armed_fn(t):
            last_arm = t
        is_armed = t - last_arm <= hold
        if state == "idle":
            hits = hits + 1 if p >= thr else 0
            if hits >= consec and is_armed:
                fires.append(t); state = "fired"
        if state == "fired":
            if d < I.CONTACT_D:
                state, tcon = "at_mouth", t
            elif d > I.RESET_D:
                state, hits = "idle", 0
        elif state == "at_mouth":
            if d > I.RELEASE_D or t - tcon > 2.0:
                state, hits, last_arm = "idle", 0, -1e9
    return fires


def seq_score(seqs, traces, probs, thr, consec, latency=0.08, gate=True):
    caught, leads, fa, by_kind = 0, [], 0, {}
    npos = nneg = 0
    fa_armed = n_armed = 0
    for s, (T, X, D), P in zip(seqs, traces, probs):
        armed_any = bool(np.any(s["armed"]))
        fires = replay(T, P, D, (lambda t, a=armed_any: a) if gate else (lambda t: True), thr, consec)
        k = by_kind.setdefault(s["kind"], [0, 0])
        k[1] += 1
        if s["label"]:
            npos += 1
            ok = [f for f in fires if f >= s["t_on"] - 0.2]
            if ok and ok[0] + latency < s["t_contact"]:
                caught += 1; k[0] += 1
                leads.append(s["t_contact"] - ok[0] - latency)
        elif s["kind"] == "aborted_raise":
            if fires:
                k[0] += 1          # reported per kind only: a conservative early STOP
        else:
            nneg += 1
            if armed_any:
                n_armed += 1
                fa_armed += bool(fires)
            if fires:
                fa += 1; k[0] += 1
    leads = np.array(leads or [0.0])
    return {"catch_rate": round(caught / max(npos, 1), 4), "false_alarm_rate": round(fa / max(nneg, 1), 4),
            "fa_armed": round(fa_armed / max(n_armed, 1), 4),
            "lead_ms_median": round(float(np.median(leads)) * 1000), "lead_ms_p10": round(float(np.percentile(leads, 10)) * 1000),
            "n_pos": npos, "n_neg": nneg,
            "by_kind": {kk: round(v[0] / v[1], 3) for kk, v in sorted(by_kind.items())}}


def predict(spec, X):
    return I.IntakeModel(spec).prob(X) if spec != "rule" else I.RuleModel().prob(X)


def choose_threshold(seqs, traces, spec, max_fa=0.05):
    probs = [predict(spec, X) if len(X) else np.zeros(0) for _, X, _ in traces]
    best = None
    grid = [0.5] if spec == "rule" else np.round(np.arange(0.30, 0.99, 0.02), 2)
    for consec in ([1] if spec == "rule" else [1, 2, 3]):
        for thr in grid:
            r = seq_score(seqs, traces, probs, thr, consec)
            # objective: catch as many as possible; false alarms cost 3x
            obj = r["catch_rate"] - 3 * max(0, r["false_alarm_rate"] - max_fa) - 0.5 * r["fa_armed"]
            if best is None or obj > best[0]:
                best = (obj, float(thr), consec, r)
    return best[1], best[2], best[3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--clips")
    ap.add_argument("--n_train", type=int, default=2000)
    ap.add_argument("--n_val", type=int, default=600)
    ap.add_argument("--n_test", type=int, default=1500)
    a = ap.parse_args()
    t0 = time.time()
    train_s, val_s, test_s = [], [], []
    if a.sim or not a.clips:
        train_s += make_dataset(a.n_train, seed=1)
        val_s += make_dataset(a.n_val, seed=2)
        test_s += make_dataset(a.n_test, seed=3)   # never touched while choosing anything
    if a.clips:
        clips = load_clips(a.clips)
        rng = np.random.default_rng(0)
        idx = rng.permutation(len(clips))
        n1, n2 = int(0.6 * len(clips)), int(0.8 * len(clips))
        train_s += [clips[i] for i in idx[:n1]]
        val_s += [clips[i] for i in idx[n1:n2]]
        test_s += [clips[i] for i in idx[n2:]]
    print(f"sequences train/val/test = {len(train_s)}/{len(val_s)}/{len(test_s)}  ({time.time()-t0:.1f}s)")
    Xtr, ytr, wtr, _ = build(train_s)
    _, _, _, tr_val = build(val_s)
    _, _, _, tr_test = build(test_s)
    print(f"train windows {len(Xtr)} (positives {int(ytr.sum())})  ({time.time()-t0:.1f}s)")

    results = {}
    candidates = {"rule": "rule"}
    candidates["logreg"] = train(Xtr, ytr, wtr, hidden=0, epochs=200)
    print(f"trained logreg ({time.time()-t0:.1f}s)")
    candidates["mlp16"] = train(Xtr, ytr, wtr, hidden=16, epochs=300)
    print(f"trained mlp16 ({time.time()-t0:.1f}s)")
    candidates["mlp32"] = train(Xtr, ytr, wtr, hidden=32, epochs=400)
    print(f"trained mlp32 ({time.time()-t0:.1f}s)")
    for name, spec in candidates.items():
        thr, consec, rv = choose_threshold(val_s, tr_val, spec)
        probs = [predict(spec, X) if len(X) else np.zeros(0) for _, X, _ in tr_test]
        rt = seq_score(test_s, tr_test, probs, thr, consec)
        rt_nogate = seq_score(test_s, tr_test, probs, thr, consec, gate=False)
        results[name] = {"threshold": thr, "consec": consec, "val": rv, "test": rt, "test_no_bottle_gate": rt_nogate}
        print(f"{name:7s} thr={thr:.2f} consec={consec} | VAL catch={rv['catch_rate']:.3f} fa={rv['false_alarm_rate']:.3f}"
              f" | TEST catch={rt['catch_rate']:.3f} fa={rt['false_alarm_rate']:.3f} fa_armed={rt['fa_armed']:.3f} lead_med={rt['lead_ms_median']}ms"
              f" p10={rt['lead_ms_p10']}ms | no-gate fa={rt_nogate['false_alarm_rate']:.3f}")

    # pick the winner on VALIDATION, never on test
    def val_obj(r):
        v = r["val"]
        return v["catch_rate"] - 0.5 * v["false_alarm_rate"] - 0.5 * v["fa_armed"]
    learned = {k: v for k, v in results.items() if k != "rule"}
    win = max(learned, key=lambda k: val_obj(learned[k]))
    spec = dict(candidates[win])
    spec.update({"threshold": results[win]["threshold"], "consec": results[win]["consec"],
                 "trained_on": {"sim": bool(a.sim or not a.clips), "clips": a.clips}})
    os.makedirs(os.path.join(HERE, "models"), exist_ok=True)
    with open(I.MODEL_FILE, "w") as f:
        json.dump(spec, f)
    os.makedirs(os.path.join(HERE, "reports"), exist_ok=True)
    tag = "sim" if not a.clips else ("clips+sim" if a.sim else "clips")
    with open(os.path.join(HERE, "reports", f"intake_{tag}.json"), "w") as f:
        json.dump({"winner": win, "results": results, "features": I.FEATURE_NAMES}, f, indent=1)
    print(f"winner on validation: {win} -> {I.MODEL_FILE}  ({time.time()-t0:.1f}s)")


if __name__ == "__main__":
    main()
