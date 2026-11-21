"""Say one thing, right now, without running the server.

    .venv/bin/python speak.py "Good morning Margaret"                # on the Nest
    .venv/bin/python speak.py --local "Good morning Margaret"        # on the laptop
    .venv/bin/python speak.py --voice en_GB-jenny_dioco-medium --local "Hello"
"""
import argparse
import functools
import os
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import voice
from nest import Nests, my_ip
from server import PORT, TYPES


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="+")
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--voice", default=voice.DEFAULT_VOICE)
    ap.add_argument("--speaker", help="name in the Google Home app (default: the first one found)")
    a = ap.parse_args()

    path = voice.synth(" ".join(a.text), a.voice)
    secs = voice.duration(path)
    if a.local:
        voice.play_local(path)
        return
    # serve the cache folder so the Nest can download the file, then tell it to play
    handler = functools.partial(SimpleHTTPRequestHandler, directory=voice.CACHE)
    srv = ThreadingHTTPServer(("", PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    n = Nests()
    name = n.play(f"http://{my_ip()}:{PORT}/{os.path.basename(path)}", TYPES[os.path.splitext(path)[1]], a.speaker)
    print(f"playing on '{name}' ({secs:.1f} s)")
    time.sleep(secs + 2)          # keep serving until it has finished downloading
    n.close()
    srv.shutdown()


if __name__ == "__main__":
    main()
