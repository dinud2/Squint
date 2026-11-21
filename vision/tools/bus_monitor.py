"""Print every bus message (except alive unless --alive). Handy for all four parts."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bus  # noqa: E402

show_alive = "--alive" in sys.argv


def show(m):
    if m.get("type") == "alive" and not show_alive:
        return
    print(time.strftime("%H:%M:%S"), json.dumps(m), flush=True)


bus.on("*", show)
bus.run_forever()
