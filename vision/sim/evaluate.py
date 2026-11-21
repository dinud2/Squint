"""Sequence-level scoring of the intake detector (shared by sim and real clips).

What we measure is what matters on stage, not per-window accuracy:
  * caught:   intake_start (plus pipeline latency) lands BEFORE the hand reaches the mouth
  * lead_ms:  how early, i.e. time left for the STOP to play
  * false alarm: any intake_start during a sequence that is not an intake
"""
import numpy as np

from squint_vision.intake import IntakeDetector


def run_detector(seq, model, thr, consec, gate=True):
    det = IntakeDetector(model=model, consec=consec, threshold=thr)
    fires = []
    for t, kps, armed in zip(seq["t"], seq["kps"], seq["armed"]):
        for ev in det.update(float(t), kps, bool(armed) if gate else True):
            if ev["type"] == "intake_start":
                fires.append(float(t))
    return fires


def score(seqs, model, thr, consec, latency_s=0.08, gate=True, min_lead_s=0.0):
    caught, leads, fa = 0, [], 0
    n_pos = n_neg = 0
    by_kind = {}
    for s in seqs:
        fires = run_detector(s, model, thr, consec, gate)
        k = by_kind.setdefault(s["kind"], [0, 0])
        k[1] += 1
        if s["label"]:
            n_pos += 1
            early = [f for f in fires if f >= s["t_on"] - 0.2]
            if early and early[0] + latency_s < s["t_contact"] - min_lead_s:
                caught += 1
                k[0] += 1
                leads.append(s["t_contact"] - early[0] - latency_s)
        else:
            n_neg += 1
            if fires:
                fa += 1
                k[0] += 1
    leads = np.array(leads) if leads else np.array([0.0])
    return {
        "catch_rate": caught / max(n_pos, 1),
        "false_alarm_rate": fa / max(n_neg, 1),
        "lead_ms_median": float(np.median(leads) * 1000),
        "lead_ms_p10": float(np.percentile(leads, 10) * 1000),
        "n_pos": n_pos, "n_neg": n_neg,
        "by_kind": {k: v[0] / v[1] for k, v in sorted(by_kind.items())},
    }
