"""Send one bus message by hand (stands in for the app until it's wired up).

    python tools/send.py enroll_start med=warfarin     # enrol a bottle: hold it up for ~6 s
    python tools/send.py enroll_start med=_empty       # enrol the empty hand / background
    python tools/send.py meds_changed
Values are sent as strings, except numbers and true/false.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bus  # noqa: E402


def parse(v):
    if v in ("true", "false"):
        return v == "true"
    try:
        return json.loads(v) if v[:1].isdigit() or v[:1] == "-" else v
    except ValueError:
        return v


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    msg = {"type": sys.argv[1]}
    for kv in sys.argv[2:]:
        k, _, v = kv.partition("=")
        msg[k] = parse(v)
    print("sent", bus.send(msg))
    time.sleep(0.05)
    return 0


if __name__ == "__main__":
    sys.exit(main())
