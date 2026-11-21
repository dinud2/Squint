"""Speak Squint's announcements on this computer by following the Pi's event stream.

    cd home && .venv/bin/python server.py --local          # Ved's voice service, laptop speaker
    python tools/speak_events.py                            # this: Pi /events -> say -> /announce

The Pi could also call the voice service itself (buddy.service --announce), but that needs
an incoming connection to the laptop, which its firewall blocks. This connects out instead.
Also prints the Tab5 commands / bottle events as they happen, so the whole flow is visible.
"""
import argparse
import json
import time
import urllib.request


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pi", default="172.20.10.9")
    ap.add_argument("--voice", default="http://localhost:8765/announce")
    a = ap.parse_args()
    while True:
        try:
            with urllib.request.urlopen(f"http://{a.pi}:8081/events", timeout=60) as r:
                print(f"[speak] following http://{a.pi}:8081/events", flush=True)
                for raw in r:
                    line = raw.decode("utf-8", "ignore").strip()
                    if not line.startswith("data:"):
                        continue
                    ev = json.loads(line[5:])
                    t = ev.get("type")
                    if t == "say":
                        print(f"[say] {ev['text']}", flush=True)
                        req = urllib.request.Request(a.voice, data=json.dumps({"text": ev["text"]}).encode(),
                                                     headers={"Content-Type": "application/json"})
                        try:
                            urllib.request.urlopen(req, timeout=60).read()
                        except Exception as e:
                            print(f"[speak] voice service failed: {e}", flush=True)
                    elif t in ("people_present", "bottle_shown", "bottle_picked", "dose_taken"):
                        info = {k: v for k, v in ev.items() if k not in ("type", "time", "since", "seq")}
                        print(f"[{t}] {info}", flush=True)
        except Exception as e:
            print(f"[speak] lost the Pi ({e}); retrying in 3 s", flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
