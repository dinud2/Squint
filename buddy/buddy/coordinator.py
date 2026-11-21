"""The coordinator: who is here + today's schedule + which bottle was picked up
-> what the Tab5 face shows, what the Nest says, and the dose log the iOS app reads.

Tab5 commands use Kathy's line format (tab5-face/README.md): `<reaction> [title][|detail][|clip]`.
The Tab5 fetches them with GET /tab5/commands and passes each line to handleCommand().

Flow (medicine-buddy design):
  people arrive          -> Tab5 `presence`/`greet`/`remind`; Nest: "Hi Dinu, you take Tylenol and
                            Metformin. Kathy, you take Omega 3-6-9."
  right bottle picked    -> pending dose; Tab5 asks "Did you take it?". Intake confidence
                            >= 0.90 auto-confirms after 2 s (Tab5 shows the check); otherwise
                            the person answers on the Tab5 (POST /doses/confirm).
  someone else's bottle  -> Tab5 `wrong`; Nest warns (owner not at the counter)
  high-risk, taken today -> Tab5 `stop`; Nest: "Stop, you already took ... at 8:02"
  unknown bottle         -> ignored here (bottle_service never names it)
  everybody leaves       -> Tab5 `away`
"""
import json
import threading
import time
import urllib.request

AUTO_CONFIRM = 0.90
UNSURE_AFTER_S = 60       # a bottle picked up but never confirmed within this long counts as "unsure"
AUTO_DELAY_S = 2.0
GREET_COOLDOWN_S = 120    # people step in and out at a counter: say hello at most once per 2 min


def join_names(xs):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


class Tab5Queue:
    """Command lines for the Tab5, numbered so a polling client never misses or repeats one."""

    def __init__(self, keep=200):
        self.cond = threading.Condition()
        self.lines = []          # (seq, line)
        self.seq = 0
        self.keep = keep

    def push(self, line):
        with self.cond:
            self.seq += 1
            self.lines = (self.lines + [(self.seq, line)])[-self.keep:]
            self.cond.notify_all()
        print("[tab5]", line, flush=True)

    def after(self, seq, wait=0.0):
        """-> (latest seq, [lines with seq > given]); waits up to `wait` s for something new."""
        with self.cond:
            if wait > 0:
                self.cond.wait_for(lambda: self.seq > seq, timeout=wait)
            return self.seq, [ln for s, ln in self.lines if s > seq]


class Coordinator:
    def __init__(self, hub, store, announce_url=None, journal=None):
        self.hub, self.store = hub, store
        self.journal = journal                  # routine tracking (journal.py); None = don't log
        self.announce_url = announce_url        # e.g. http://<laptop>:8765/announce (home/server.py)
        self.tab5 = Tab5Queue()
        self.present = []
        self.pending = None                     # {"med", "for", "t"} waiting for "did you take it?"
        self.last_greet = {}                    # person -> time of the last spoken greeting
        self.arrived_at = {}                    # person -> when this visit started
        self.due_at_arrival = {}                # person -> med ids that were due when they arrived
        self.took_this_visit = set()            # people who confirmed a dose during this visit
        self.lock = threading.Lock()
        hub.listeners.append(self.on_event)

    # ------------------------------------------------------------ outputs
    def say(self, text):
        self.hub.publish({"type": "say", "text": text})
        if not self.announce_url:
            return
        def go():
            try:
                req = urllib.request.Request(self.announce_url, data=json.dumps({"text": text}).encode(),
                                             headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=10).read()
            except Exception as e:
                print("[say] announce failed:", e, flush=True)
        threading.Thread(target=go, daemon=True).start()

    def show(self, line):
        self.tab5.push(line)

    def log(self, type_, who, **fields):
        if self.journal is not None:
            try:
                self.journal.record(type_, who, **fields)
            except OSError as e:                # a full disk must not stop the buddy
                print("[journal]", e, flush=True)

    def due_now(self, pid):
        """Med ids this person should be taking right now (due time passed, not taken yet)."""
        now_m = int(time.strftime("%H")) * 60 + int(time.strftime("%M"))
        return [d["med"] for d in self.store.open_doses(pid)
                if int(d["due"][:2]) * 60 + int(d["due"][3:]) <= now_m]

    # ------------------------------------------------------------ inputs
    def on_event(self, ev):
        try:
            t = ev.get("type")
            if t == "people_present":
                self.on_people(ev["people"])
            elif t in ("bottle_picked", "bottle_shown"):
                self.on_bottle(ev["bottle"])
            elif t == "intake":
                self.on_intake(ev.get("person"), ev.get("confidence", 0.0))
        except Exception as e:                  # a bad event must never stop the service
            print("[coordinator] error:", repr(e), flush=True)

    def med_list(self, pid):
        names = []
        for d in self.store.open_doses(pid):
            m = self.store.med(d["med"])
            if m and m["name"] not in names:
                names.append(m["name"])
        return names

    def on_people(self, people):
        now = time.time()
        with self.lock:
            arrived = [p for p in people if p not in self.present]
            left = [p for p in self.present if p not in people]
            self.present = list(people)
        for pid in arrived:
            self.arrived_at[pid] = now
            self.due_at_arrival[pid] = self.due_now(pid)
            self.took_this_visit.discard(pid)
            self.log("arrive", pid)
        for pid in left:
            stayed = round(now - self.arrived_at.pop(pid, now))
            self.log("leave", pid, stayed_s=stayed)
            due = self.due_at_arrival.pop(pid, [])
            if due and pid not in self.took_this_visit and stayed >= 5:
                self.log("visit_no_dose", pid, due=due)
        if not people:
            self.show("away")
            return
        if not arrived:
            return
        first = self.store.name(arrived[0])
        self.show(f"presence {first}")          # the face always wakes up
        now = time.time()
        to_greet = [p for p in arrived if now - self.last_greet.get(p, -1e9) >= GREET_COOLDOWN_S]
        for p in to_greet:
            self.last_greet[p] = now
        if not to_greet:
            return
        arrived = to_greet
        parts = []
        for pid in arrived:
            name, meds = self.store.name(pid), self.med_list(pid)
            if meds:
                parts.append(f"{name}, today you take {join_names(meds)}.")
            else:
                parts.append(f"{name}, you're all done for today.")
        self.say("Hi " + " ".join(parts))
        todo = [(pid, self.med_list(pid)) for pid in arrived if self.med_list(pid)]
        if todo:   # Tab5: "Hi Dinu!" with the medicines to take underneath
            pid, meds = todo[0]
            self.show(f"remind Hi {self.store.name(pid)}!|{', '.join(meds)}")
        else:
            self.show(f"greet {first}")

    def on_bottle(self, bottle):
        m = self.store.med(bottle)
        if m is None:
            return
        owner, oname, mname = m["for"], self.store.name(m["for"]), m["name"]
        present = list(self.present)
        if present and owner not in present:
            self.log("wrong_bottle", present, med=bottle, owner=owner)
            who = join_names([self.store.name(p) for p in present])
            self.show(f"wrong {oname}'s pills|That's {oname}'s {mname}")
            self.say(f"Careful {who}, that's {oname}'s {mname}.")
            return
        taken = self.store.taken_today(bottle, owner)
        open_this = [d for d in self.store.open_doses(owner) if d["med"] == bottle]
        # high risk: never a second dose the same day; otherwise only if no dose of it is left today
        if taken and (m.get("risk") == "high" or not open_this):
            at = taken[-1]["at"]
            self.log("double_dose", owner, med=bottle, first_at=at)
            self.show(f"stop Already taken|{mname} at {at}")
            self.say(f"Stop, {oname}. You already took your {mname} at {at}.")
            return
        with self.lock:
            p = self.pending = {"med": bottle, "for": owner, "t": time.time()}
        self.log("bottle", owner, med=bottle)
        self.show(f"remind {mname}|Did you take it?")
        tm = threading.Timer(UNSURE_AFTER_S, self._never_answered, args=(p,))
        tm.daemon = True                        # never keeps the service from shutting down
        tm.start()

    def _never_answered(self, p):
        with self.lock:
            if self.pending is not p:
                return                          # answered, or another bottle since
            self.pending = None
        self.log("unsure", p["for"], med=p["med"], reason="no_answer")

    def on_intake(self, person, confidence):
        """From the counter camera's hand-to-mouth check."""
        with self.lock:
            p = self.pending
        if not p or (person and person != p["for"]):
            return
        if confidence >= AUTO_CONFIRM:
            self.show(f"happy Taken|{self.store.med(p['med'])['name']}")
            threading.Timer(AUTO_DELAY_S, self.confirm, args=(p["med"], p["for"], True, "auto")).start()

    def confirm(self, med, person, taken=True, how="tab5"):
        """POST /doses/confirm, or the auto-confirm timer."""
        with self.lock:
            p = self.pending
            if p and p["med"] == med and p["for"] == person:
                self.pending = None
        m = self.store.med(med)
        if m is None:
            return {"error": f"unknown medication {med}"}
        if not taken:
            self.log("unsure", person, med=med, reason="said_no")
            self.show("idle")
            return {"med": med, "for": person, "status": "due"}
        d = self.store.mark(med, person, "taken", reason=None if how != "auto" else None)
        if d is None:
            return {"error": f"no open dose of {med} for {person} today"}
        self.hub.publish({"type": "dose_taken", "med": med, "for": person, "at": d["at"], "how": how})
        now_m = int(d["at"][:2]) * 60 + int(d["at"][3:])
        arrived = self.arrived_at.get(person)
        self.took_this_visit.add(person)
        self.log("dose", person, med=med, due=d["due"], at=d["at"], how=how,
                 late_min=now_m - (int(d["due"][:2]) * 60 + int(d["due"][3:])),
                 since_arrival_s=round(time.time() - arrived) if arrived else None)
        if how != "auto":
            self.show(f"happy Well done!|{m['name']}")
        left = self.med_list(person)
        if not left:
            self.say(f"Well done, {self.store.name(person)}. That's everything for now.")
        return d
