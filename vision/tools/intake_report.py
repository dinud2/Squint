"""C9: intake numbers + plots for Devpost, on a fresh simulated test set.

1. Trade-off curve: catch-before-mouth vs. false STOPs, sweeping the threshold.
2. Parity check: the fast replay scorer vs. the real live IntakeDetector.
3. Lead-time histogram and a per-movement table.
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from sim.evaluate import score as live_score  # noqa: E402
from sim.pose_sim import make_dataset  # noqa: E402
from squint_vision import intake as I  # noqa: E402
from tools.train_intake import build, seq_score  # noqa: E402

OUT = os.path.join(HERE, "reports")


def main():
    os.makedirs(OUT, exist_ok=True)
    test = make_dataset(1500, seed=4)          # a seed nothing was tuned on
    _, _, _, traces = build(test)
    model = I.IntakeModel.load()
    rule = I.RuleModel()
    consec = int(model.spec.get("consec", 2))
    probs = [model.prob(X) if len(X) else np.zeros(0) for _, X, _ in traces]
    rprobs = [rule.prob(X) if len(X) else np.zeros(0) for _, X, _ in traces]

    curve = []
    for thr in np.round(np.arange(0.30, 0.995, 0.02), 3):
        r = seq_score(test, traces, probs, thr, consec)
        curve.append((thr, r["catch_rate"], r["fa_armed"], r["false_alarm_rate"], r["lead_ms_median"]))
    curve = np.array(curve)
    chosen = seq_score(test, traces, probs, model.threshold, consec)
    rule_r = seq_score(test, traces, rprobs, 0.5, 1)

    # parity: real detector on a subset
    sub = test[:300]
    _, _, _, tr_sub = build(sub)
    fast = seq_score(sub, tr_sub, [model.prob(X) if len(X) else np.zeros(0) for _, X, _ in tr_sub],
                     model.threshold, consec)
    live = live_score(sub, model, model.threshold, consec)

    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    ax[0].plot(curve[:, 2] * 100, curve[:, 1] * 100, "-o", ms=3, color="#2a6fdb", label=f"{model.kind} (threshold sweep)")
    ax[0].plot([chosen["fa_armed"] * 100], [chosen["catch_rate"] * 100], "*", ms=16, color="#e4572e",
               label=f"chosen: thr {model.threshold:.2f}")
    ax[0].plot([rule_r["fa_armed"] * 100], [rule_r["catch_rate"] * 100], "s", ms=9, color="#777", label="hand-written rule")
    ax[0].set_xlabel("false STOPs while holding a bottle (%)")
    ax[0].set_ylabel("intakes caught before the mouth (%)")
    ax[0].set_title("Catch vs. false STOP (simulated test set)")
    ax[0].grid(alpha=0.3); ax[0].legend(loc="lower right", fontsize=8)
    leads = []
    from tools.train_intake import replay
    for s, (T, X, D), P in zip(test, traces, probs):
        if not s["label"]:
            continue
        f = [x for x in replay(T, P, D, lambda t: True, model.threshold, consec) if x >= s["t_on"] - 0.2]
        if f:
            leads.append((s["t_contact"] - f[0] - 0.08) * 1000)
    ax[1].hist(leads, bins=30, color="#2a6fdb", alpha=0.85)
    ax[1].axvline(0, color="#e4572e", lw=2, label="hand reaches mouth")
    ax[1].set_xlabel("warning lead time before the mouth (ms, incl. 80 ms pipeline)")
    ax[1].set_ylabel("intakes"); ax[1].set_title("How early STOP fires"); ax[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "intake_tradeoff.png"), dpi=130)

    report = {"model": model.kind, "threshold": model.threshold, "consec": consec,
              "chosen": chosen, "rule": rule_r,
              "parity_fast_vs_live": {"fast": {k: fast[k] for k in ("catch_rate", "false_alarm_rate", "fa_armed")},
                                      "live": {k: live[k] for k in ("catch_rate", "false_alarm_rate")}},
              "curve": curve.tolist()}
    with open(os.path.join(OUT, "intake_report.json"), "w") as f:
        json.dump(report, f, indent=1)
    print(json.dumps({k: report[k] for k in ("model", "threshold", "consec", "parity_fast_vs_live")}, indent=1))
    print("chosen:", {k: chosen[k] for k in ("catch_rate", "false_alarm_rate", "fa_armed", "lead_ms_median", "lead_ms_p10")})
    print("rule:  ", {k: rule_r[k] for k in ("catch_rate", "false_alarm_rate", "fa_armed", "lead_ms_median")})
    print("by kind:", chosen["by_kind"])
    print("curve (thr, catch, fa_armed, fa_all, lead):")
    for row in curve[::3]:
        print("  ", np.round(row, 3).tolist())


if __name__ == "__main__":
    main()
