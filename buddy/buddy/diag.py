"""What each part of Squint last did, so "it's not doing anything" can be answered from outside.

Every loop writes a few facts here as it runs (cheap: a dict update per frame). GET /health turns
them into a report and plain-English warnings, e.g. "the Tab5 hasn't asked for commands in 40 s:
check SQUINT_PI_HOST in tab5-face/secrets.h". tools/doctor.py prints the same for a person.

Nothing here changes what Squint does; it only watches.
"""
import threading
import time

FACE_EDGE = 0.04          # a face box this close to the frame edge is probably cut off
QUIET_S = 60              # no face for this long while the camera runs: say so (info, not a fault)
STALE_S = 5               # a camera loop with no frame for this long has stopped
TAB5_LOST_S = 30          # the Tab5 long-polls every ~20 s; longer than this means it can't reach us


class Diag:
    def __init__(self):
        self.lock = threading.Lock()
        self.started = time.time()
        self.faces = {"source": None, "enrolled": [], "frames": 0, "last_frame_t": 0.0,
                      "last_face_t": 0.0, "last_named_t": 0.0, "last_names": [], "last_unknown": 0,
                      "too_small": 0, "at_edge": 0, "last_box": None, "errors": 0, "last_error": None}
        self.bottles = {"source": None, "mode": None, "enrolled": [], "frames": 0, "last_frame_t": 0.0,
                        "last_named_t": 0.0, "last": None, "errors": 0, "last_error": None}
        self.voice = {"url": None, "sent": 0, "failed": 0, "last_t": 0.0, "last_ok": None, "last_error": None}
        self.pollers = {}        # (ip, kind) -> last time it asked for /tab5/commands

    # ------------------------------------------------------------ written by the loops
    def face_frame(self, t, shape, raw, kept, seen):
        """raw: faces YuNet found; kept: those big enough; seen: [(row, name, score, scores)]."""
        h, w = shape[:2]
        with self.lock:
            f = self.faces
            f["frames"] += 1
            f["last_frame_t"] = t
            f["too_small"] = max(0, raw - kept)
            if seen:
                f["last_face_t"] = t
                names = [n for _, n, _, _ in seen if n != "unknown"]
                f["last_unknown"] = sum(n == "unknown" for _, n, _, _ in seen)
                if names:
                    f["last_names"], f["last_named_t"] = names, t
                x, y, bw, bh = (float(v) for v in seen[0][0][:4])
                f["last_box"] = [round(x / w, 2), round(y / h, 2), round(bw / w, 2), round(bh / h, 2)]
                edge = (x < FACE_EDGE * w or y < FACE_EDGE * h or
                        x + bw > (1 - FACE_EDGE) * w or y + bh > (1 - FACE_EDGE) * h)
                f["at_edge"] = f["at_edge"] + 1 if edge else 0

    def bottle_frame(self, t, result):
        with self.lock:
            b = self.bottles
            b["frames"] += 1
            b["last_frame_t"] = t
            top = (result.get("bottles") or [{}])[0]
            b["last"] = {"name": top.get("name"), "score": top.get("score")}
            if any(x.get("name") not in (None, "unknown") for x in result.get("bottles") or []):
                b["last_named_t"] = t

    def error(self, part, e):
        with self.lock:
            d = self.faces if part == "face" else self.bottles
            d["errors"] += 1
            d["last_error"] = f"{type(e).__name__}: {e}"[:200]

    def announced(self, ok, error=None):
        with self.lock:
            v = self.voice
            v["last_t"] = time.time()
            v["last_ok"] = ok
            if ok:
                v["sent"] += 1
            else:
                v["failed"] += 1
                v["last_error"] = str(error)[:200]

    def polled(self, ip, agent):
        a = (agent or "").lower()
        kind = "tab5" if "esp32" in a or "arduino" in a else "app" if ("squint" in a or "cfnetwork" in a) else "other"
        with self.lock:
            self.pollers[(ip, kind)] = time.time()

    # ------------------------------------------------------------ read by /health
    def report(self):
        now = time.time()
        age = lambda t: round(now - t, 1) if t else None        # noqa: E731
        with self.lock:
            f, b, v = dict(self.faces), dict(self.bottles), dict(self.voice)
            pollers = dict(self.pollers)
        warn = []

        # faces
        if f["source"] is None:
            warn.append("Face camera is off (--face-source is empty): Squint can't see who is there.")
        else:
            if not f["enrolled"]:
                warn.append("Nobody is enrolled: every face will be 'unknown' and Squint stays quiet. "
                            "Run tools/enroll_face.py.")
            fa = age(f["last_frame_t"])
            if fa is None or fa > STALE_S:
                warn.append(f"Face camera has sent no frame for {fa if fa is not None else 'ever'} s: "
                            "is camstream running (pi/squint_start.sh)?")
            elif f["at_edge"] >= 3:
                warn.append("The face is at the edge of the picture: aim the camera so faces are in the middle.")
            elif f["too_small"]:
                warn.append("A face is too small or far away to recognise (< 60 px): come closer.")
            elif f["last_face_t"] and now - f["last_face_t"] < STALE_S and f["last_unknown"] \
                    and f["last_named_t"] < f["last_face_t"]:
                warn.append("Someone is in view but not recognised: only enrolled people are greeted.")
            elif now - self.started > QUIET_S and (not f["last_face_t"] or age(f["last_face_t"]) > QUIET_S):
                warn.append(f"No face seen for over {QUIET_S} s while the camera runs: is the camera "
                            "pointing at where people stand?")
            if f["errors"]:
                warn.append(f"{f['errors']} face frames failed; last: {f['last_error']}")

        # bottles
        if b["source"] is not None:
            ba = age(b["last_frame_t"])
            if ba is None or ba > STALE_S:
                warn.append(f"Bottle camera has sent no frame for {ba if ba is not None else 'ever'} s.")
            if not [n for n in b["enrolled"] if n != "_other"]:
                warn.append("No bottles are enrolled: run tools/enroll_bottle.py.")
            elif "_other" not in b["enrolled"] and b["mode"] == "show":
                warn.append("No '_other' bottle class: faces and hands can score close to a bottle. "
                            "Run tools/enroll_bottle.py --name _other.")
            if b["errors"]:
                warn.append(f"{b['errors']} bottle frames failed; last: {b['last_error']}")

        # voice
        if not v["url"]:
            warn.append("No --announce URL: the Google Home won't speak.")
        elif v["last_ok"] is False:
            warn.append(f"The last announcement failed ({v['last_error']}): is home/server.py running "
                        f"and reachable at {v['url']}?")

        # Tab5
        tab5 = [(ip, t) for (ip, k), t in pollers.items() if k == "tab5"]
        if not tab5:
            if now - self.started > TAB5_LOST_S:
                warn.append("The Tab5 has never asked for commands: check SQUINT_PI_HOST and the Wi-Fi "
                            "in tab5-face/secrets.h, then reflash.")
        elif min(now - t for _, t in tab5) > TAB5_LOST_S:
            warn.append(f"The Tab5 stopped asking for commands {round(min(now - t for _, t in tab5))} s ago: "
                        "is it on the same network?")

        def ages(d, keys):           # timestamps -> "seconds ago", which is what a person reads
            return {**{k: v for k, v in d.items() if k not in keys},
                    **{k[:-2] + "_age_s": age(d[k]) for k in keys}}

        return {
            "faces": ages(f, ("last_frame_t", "last_face_t", "last_named_t")),
            "bottles": ages(b, ("last_frame_t", "last_named_t")),
            "voice": ages(v, ("last_t",)),
            "clients": [{"ip": ip, "kind": k, "age_s": round(now - t, 1)} for (ip, k), t in
                        sorted(pollers.items(), key=lambda kv: -kv[1])],
            "uptime_s": round(now - self.started),
            "warnings": warn,
        }
