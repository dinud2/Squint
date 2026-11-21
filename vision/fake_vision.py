"""fake_vision (C1): scripted Part C messages so B, D and A can build without a camera.

    python fake_vision.py                 # Margaret's morning, then loops
    python fake_vision.py --scenario double
    python fake_vision.py --list

It also answers `enroll_start` with fake `enroll_progress` (0..100 over ~5 s),
so Ved's enrolment screen works against it.
"""
import argparse
import threading
import time

import bus

# (delay before this message in seconds, message)
SCENARIOS = {
    "correct": [  # right bottle, first dose of the day
        (1.0, {"type": "bottle_seen", "med": "warfarin", "confidence": 0.94}),
        (1.5, {"type": "intake_start", "confidence": 0.88, "lead_ms": 420}),
        (0.6, {"type": "intake_done"}),
    ],
    "double": [  # same bottle again: D should answer with STOP
        (1.0, {"type": "bottle_seen", "med": "warfarin", "confidence": 0.95}),
        (1.2, {"type": "intake_start", "confidence": 0.91, "lead_ms": 380}),
    ],
    "robert": [  # someone else's bottle
        (1.0, {"type": "bottle_seen", "med": "metoprolol_robert", "confidence": 0.90}),
        (1.5, {"type": "intake_start", "confidence": 0.84, "lead_ms": 350}),
    ],
    "unknown": [  # a bottle Squint has never been shown
        (1.0, {"type": "bottle_seen", "med": "unknown", "confidence": 0.41}),
    ],
    "water": [  # drinking water: bottle_seen none, no intake_start
        (1.0, {"type": "bottle_seen", "med": "none", "confidence": 0.0}),
    ],
}
SCENARIOS["morning"] = (SCENARIOS["correct"] + [(3.0, {"type": "bottle_seen", "med": "none", "confidence": 0.0})]
                        + SCENARIOS["double"] + [(3.0, {"type": "bottle_seen", "med": "none", "confidence": 0.0})]
                        + SCENARIOS["robert"] + [(3.0, {"type": "bottle_seen", "med": "none", "confidence": 0.0})]
                        + SCENARIOS["unknown"])


def fake_enroll(msg):
    med = msg.get("med", "unknown")

    def run():
        for p in range(0, 101, 10):
            bus.send({"type": "enroll_progress", "med": med, "percent": p})
            time.sleep(0.5)
    threading.Thread(target=run, daemon=True).start()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="morning", choices=sorted(SCENARIOS))
    ap.add_argument("--once", action="store_true", help="play once instead of looping")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        for k, v in SCENARIOS.items():
            print(k, "->", " ".join(m["type"] for _, m in v))
        return
    bus.init("vision")
    bus.on("enroll_start", fake_enroll)
    while True:
        for delay, msg in SCENARIOS[a.scenario]:
            time.sleep(delay)
            print("send", bus.send(msg))
        if a.once:
            time.sleep(1)
            return
        time.sleep(4)


if __name__ == "__main__":
    main()
