"""Is Squint working, and if not, why? Run it from the laptop while the Pi is on.

    python3 tools/doctor.py                 # finds the Pi on a phone hotspot (172.20.10.x)
    python3 tools/doctor.py --pi 172.20.10.3

Checks the camera stream, the service, what each camera last saw, the voice server, and
whether the Tab5 and the app are talking to the Pi, then says what to fix. Standard library
only, so it runs anywhere.
"""
import argparse
import json
import socket
import subprocess
import urllib.error
import urllib.request

OK, WARN, BAD = "  ok ", "  !! ", "  XX "
FIX = []                     # what this script found wrong itself, added to the Pi's own warnings


def bad(text, fix):
    print(BAD + text)
    FIX.append(fix)


def get(url, timeout=3, raw=False):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read(2048) if raw else json.loads(r.read())


def port_open(host, port, timeout=0.6):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def laptop_ip():
    for iface in ("en0", "en1"):
        try:
            ip = subprocess.run(["ipconfig", "getifaddr", iface], capture_output=True, text=True).stdout.strip()
            if ip:
                return ip
        except OSError:
            pass
    try:                                           # not a Mac: the address used to reach the hotspot
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("172.20.10.1", 9))
            return s.getsockname()[0]
    except OSError:
        return None


def find_pi():
    for i in range(2, 15):
        host = f"172.20.10.{i}"
        if port_open(host, 8081):
            return host
    return None


def ago(s):
    return "never" if s is None else f"{s:.0f} s ago" if s >= 1 else "just now"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pi", help="the Pi's address (default: look on the phone hotspot)")
    ap.add_argument("--voice", default="http://localhost:8765", help="the voice server (home/server.py)")
    a = ap.parse_args()

    me = laptop_ip()
    print(f"laptop  {me or '?'}")
    pi = a.pi or find_pi()
    if not pi:
        print(BAD + "No Pi answering on :8081 on 172.20.10.2-14. Is it on the hotspot, and was "
                    "squint_start.sh run? (pass --pi <address> if it's on another network)")
        return
    print(f"pi      {pi}\n")

    # camera stream
    if port_open(pi, 8080):
        try:
            head = get(f"http://{pi}:8080/stream", raw=True)
            print((OK if b"\xff\xd8" in head else WARN) + f"camera stream  http://{pi}:8080"
                  + ("" if b"\xff\xd8" in head else " (answers, but sent no picture yet)"))
        except Exception as e:
            print(WARN + f"camera stream answers but failed: {e}")
    else:
        bad("camera stream :8080 is down", "Start the camera: ssh qnxuser@<pi> ./squint_start.sh "
            "(if it was unplugged, the script restarts the camera service).")

    # the service and what it saw
    try:
        h = get(f"http://{pi}:8081/health")
    except Exception as e:
        bad(f"service :8081 didn't answer /health: {e}", "Restart it with ./squint_start.sh and read ~/buddy/service.log.")
        print("\nWhat to fix:\n  - " + "\n  - ".join(FIX))
        return
    if "warnings" not in h:
        print(WARN + "this Pi runs an older buddy/ without diagnostics: copy buddy/buddy over and restart")
        print(f"       camera_age_s {h.get('camera_age_s')}")
        return
    f, b, v = h["faces"], h["bottles"], h["voice"]
    print(OK + f"service up {h['uptime_s']} s")
    print((OK if f.get("last_frame_age_s") is not None and f["last_frame_age_s"] < 5 else BAD)
          + f"faces    {f['frames']} frames, last {ago(f.get('last_frame_age_s'))}; enrolled {f['enrolled'] or 'nobody'}")
    print("         last face " + ago(f.get("last_face_age_s"))
          + (f", last named {f['last_names']} {ago(f.get('last_named_age_s'))}" if f["last_names"] else "")
          + (f", box (x,y,w,h as fractions) {f['last_box']}" if f["last_box"] else ""))
    if b.get("source"):
        print((OK if b.get("last_frame_age_s") is not None and b["last_frame_age_s"] < 5 else BAD)
              + f"bottles  {b['frames']} frames, last {ago(b.get('last_frame_age_s'))}; enrolled {b['enrolled'] or 'none'}")
        print(f"         now {b['last']}, last named {ago(b.get('last_named_age_s'))}")

    # voice: from the Pi's side, and from here
    if v["url"]:
        print((OK if v["last_ok"] is not False else BAD) + f"voice    Pi announces to {v['url']}: "
              f"{v['sent']} sent, {v['failed']} failed" + (f" (last: {v['last_error']})" if v["last_error"] else ""))
        host = v["url"].split("//")[-1].split(":")[0]
        if me and host not in (me, "localhost", "127.0.0.1"):
            bad(f"         ...but this laptop is {me}",
                f"The Pi sends speech to {host}, not this laptop: restart it with "
                f"SQUINT_ARGS=\"--announce http://{me}:8765/announce\" ./squint_start.sh")
    try:
        get(a.voice.rstrip("/") + "/", timeout=2, raw=True)
        print(OK + f"voice server answering at {a.voice}")
    except urllib.error.HTTPError:
        print(OK + f"voice server answering at {a.voice}")
    except Exception:
        bad(f"voice server not running at {a.voice}",
            "Start the voice: cd home && .venv/bin/python server.py --local")

    # who is listening to the Pi
    kinds = {c["kind"]: c for c in h["clients"]}
    for kind, label in (("tab5", "Tab5"), ("app", "iOS app")):
        c = kinds.get(kind)
        print((OK if c and c["age_s"] < 30 else WARN) + f"{label:8s} " +
              (f"{c['ip']}, last asked {ago(c['age_s'])}" if c else "has not asked for commands"))

    print()
    todo = FIX + [w for w in h["warnings"] if not (FIX and "announcement failed" in w)]
    if todo:
        print("What to fix:")
        for w in todo:
            print("  - " + w)
    else:
        print("No problems found. Walk up to the camera: Squint should greet you within a second.")


if __name__ == "__main__":
    main()
