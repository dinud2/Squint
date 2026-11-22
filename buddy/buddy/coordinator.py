"""The coordinator: who is here + today's schedule + which bottle was picked up
-> what the Tab5 face shows, what the Nest says, and the dose log the iOS app reads.

Tab5 commands use Kathy's line format (tab5-face/README.md): `<reaction> [title][|detail][|clip]`.
The Tab5 fetches them with GET /tab5/commands and passes each line to handleCommand().

Flow (medicine-buddy design):
  people arrive          -> Tab5 `presence`/`greet`/`remind`; Nest: "Hi Dinu, you take Tylenol and
                            Metformin. Kathy, you take Omega 3-6-9."
  right bottle picked    -> pending dose; Tab5 asks "Did you take it?". Intake confidence
                            >= 0.75 auto-confirms after 2 s (Tab5 shows the check); otherwise
                            the person answers on the Tab5 (POST /doses/confirm).
  someone else's bottle  -> Tab5 `wrong`; Nest warns (owner not at the counter)
  high-risk, taken today -> Tab5 `stop`; Nest: "Stop, you already took ... at 8:02"
  unknown bottle         -> ignored here (bottle_service never names it)
  everybody leaves       -> Tab5 `away`

Demo mode (Coordinator(demo=True), `python3 -m buddy.service --demo`): no clock at all. Arrivals
get "Hi Dinu"; a bottle is only checked against who is at the counter: their own -> Tab5
`happy That's yours|Tylenol` + "Yes Dinu, that's your Tylenol."; someone else's -> the `wrong`
warning; nobody recognised -> `concerned Who's there?`. No dose windows, no "not yet", no
"already taken", no "all done", no Did-you-take-it timers, and nothing is written to the dose log.
"""
import json
import threading
import time
import urllib.request

AUTO_CONFIRM = 0.75      # hand-to-mouth confidence that ticks Yes by itself (was 0.90: 1-2 frame detections only asked)
UNSURE_AFTER_S = 60       # a bottle picked up but never confirmed within this long counts as "unsure"
AUTO_DELAY_S = 2.0
# One camera: people are recognised walking up, then show the bottle at chest height with their
# face out of view. The last group recognised stays "at the counter" this long for bottles.
AT_COUNTER_S = 120
# Bottles the camera knows but the app may not list (bottle id -> how to say it).
KNOWN_BOTTLES = {"omega369": "Omega 3-6-9", "advil": "Advil", "motrin": "Motrin", "tylenol": "Tylenol",
                 "vitamind": "Vitamin D"}
GREET_COOLDOWN_S = 30     # people step in and out at a counter: say hello at most once per 30 s


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
    def __init__(self, hub, store, announce_url=None, journal=None, demo=False):
        self.hub, self.store = hub, store
        self.demo = demo                        # True: only "own medicine or someone else's?"
        self.journal = journal                  # routine tracking (journal.py); None = don't log
        self.announce_url = announce_url        # e.g. http://<laptop>:8765/announce (home/server.py)
        self.tab5 = Tab5Queue()
        self.present = []
        self.unknown_here = False               # a face nobody enrolled is in view now
        self.last_group, self.last_group_t = [], 0.0   # who was last recognised walking up, and when
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
                self.hub.diag.announced(True)
            except Exception as e:
                print("[say] announce failed:", e, flush=True)
                self.hub.diag.announced(False, e)
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
                self.on_people(ev["people"], ev.get("unknown", 0))
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

    def on_people(self, people, unknown=0):
        now = time.time()
        with self.lock:
            arrived = [p for p in people if p not in self.present]
            left = [p for p in self.present if p not in people]
            if self.present:                   # whoever was in view until now
                self.last_group_t = now
            if people:                         # a new face replaces whoever was here before
                self.last_group, self.last_group_t = list(people), now
            elif unknown:                      # ...and so does a stranger: never credit the last person
                self.last_group = []
            self.present = list(people)
            self.unknown_here = bool(unknown)
        for pid in arrived:
            self.arrived_at[pid] = now
            self.due_at_arrival[pid] = [] if self.demo else self.due_now(pid)
            self.took_this_visit.discard(pid)
            self.log("arrive", pid)
        for pid in left:
            stayed = round(now - self.arrived_at.pop(pid, now))
            self.log("leave", pid, stayed_s=stayed)
            due = self.due_at_arrival.pop(pid, [])
            if due and pid not in self.took_this_visit and stayed >= 5:
                self.log("visit_no_dose", pid, due=due)
        if not people:
            self.show("away")                  # a stranger is not greeted: the Tab5 just rests
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
        if self.demo:                           # no schedule: just hello
            self.say("Hi " + join_names([self.store.name(p) for p in arrived]) + ".")
            self.show(f"greet {first}")
            return
        parts = []
        for pid in arrived:
            name, meds = self.store.name(pid), self.med_list(pid)
            if meds:
                timed = []
                for d in self.store.open_doses(pid):
                    s = f"{self.store.med(d['med'])['name']} at {d['due']}"
                    if s not in timed:
                        timed.append(s)
                parts.append(f"{name}, take your {join_names(timed)}.")
            elif self.store.upcoming(pid):
                nxt = self.store.upcoming(pid)[0]
                parts.append(f"{name}, nothing right now. Your next medicine is {self.store.med(nxt['med'])['name']} at {nxt['due']}.")
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
        if m is None:                           # a bottle we recognise, but nobody takes it here
            name = KNOWN_BOTTLES.get(bottle, bottle.capitalize())
            self.log("bottle_not_registered", list(self.present), med=bottle)
            self.show(f"concerned Not registered|{name} isn't in the app")
            self.say(f"That's {name}. That medication isn't registered in the app.")
            return
        owner, oname, mname = m["for"], self.store.name(m["for"]), m["name"]
        now = time.time()
        present = list(self.present) or (list(self.last_group) if now - self.last_group_t < AT_COUNTER_S else [])
        if not present and self.unknown_here:
            # Someone not enrolled holds it: say so, never guess whose turn it is.
            self.log("bottle_unknown_person", [], med=bottle)
            self.show(f"concerned Who's there?|I don't know you")
            self.say(f"I don't recognise you, so I can't check whose {mname} this is.")
            return
        if not present:
            # Nobody recognised: don't guess whose dose it is (it used to go to the bottle's owner).
            self.log("bottle_no_face", [], med=bottle)
            self.show("concerned Who's there?|Look at the camera")
            self.say(f"I can't see who you are. Please look at the camera, then show me the {mname} again.")
            return
        if owner not in present:
            self.log("wrong_bottle", present, med=bottle, owner=owner)
            who = join_names([self.store.name(p) for p in present])
            self.show(f"wrong {oname}'s pills|That's {oname}'s {mname}")
            self.say(f"Careful {who}, that's {oname}'s {mname}.")
            return
        if self.demo:                           # their own medicine: confirm, then ask (no dose times)
            self.log("right_bottle", owner, med=bottle)
            self.say(f"Yes {oname}, that's your {mname}.")
            self._ask(bottle, owner, mname)
            return
        taken = self.store.taken_today(bottle, owner)
        open_this = [d for d in self.store.open_doses(owner) if d["med"] == bottle]
        later = self.store.upcoming(owner, bottle)
        # Not time yet (doses open 1 h before): amber "not yet", not the red STOP. High-risk
        # medicines already taken today still get STOP below.
        if not open_this and later and not (taken and m.get("risk") == "high"):
            self.log("not_yet", owner, med=bottle, next=later[0]["due"])
            self.show(f"concerned Not yet|Next {mname} at {later[0]['due']}")
            self.say(f"Not yet, {oname}. Your next {mname} is at {later[0]['due']}.")
            return
        # high risk: never a second dose the same day; otherwise only if no dose of it is left today
        if taken and (m.get("risk") == "high" or not open_this):
            at = taken[-1]["at"]
            self.log("double_dose", owner, med=bottle, first_at=at)
            # the app (and its notification) only hear about it through /today
            self.store.flag(bottle, owner, f"{oname} picked up {mname} again at {time.strftime('%H:%M')}. "
                                           f"It was already taken at {at}, so Squint stopped it.")
            self.show(f"stop Already taken|{mname} at {at}")
            self.say(f"Stop, {oname}. You already took your {mname} at {at}.")
            return
        self.log("bottle", owner, med=bottle)
        self._ask(bottle, owner, mname)

    def _ask(self, bottle, owner, mname):
        with self.lock:
            p = self.pending = {"med": bottle, "for": owner, "t": time.time()}
        self.show(f"ask {mname}|Did you take it?")   # Tab5: Yes / No, waits for a tap
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
            # Tab5: Yes / No with Yes ticking itself after AUTO_DELAY_S; the Pi records it unless
            # the person taps No first (that clears pending, and the timer then does nothing).
            self.show(f"taken {self.store.med(p['med'])['name']}|I saw you take it!")
            threading.Timer(AUTO_DELAY_S, self._auto_confirm, args=(p,)).start()

    def _auto_confirm(self, p):
        with self.lock:
            still = self.pending is p
        if still:
            self.confirm(p["med"], p["for"], True, "auto")

    def confirm(self, med, person, taken=True, how="tab5"):
        """POST /doses/confirm, or the auto-confirm timer. med/person may be omitted: then the
        dose currently waiting for "Did you take it?" is meant (the Tab5's Yes / No buttons)."""
        with self.lock:
            p = self.pending
            if p and not med and not person:
                med, person = p["med"], p["for"]
            if p and p["med"] == med and p["for"] == person:
                self.pending = None
        if not med:
            return {"error": "no dose is waiting for an answer"}
        m = self.store.med(med)
        if m is None:
            return {"error": f"unknown medication {med}"}
        if not taken:
            self.log("unsure", person, med=med, reason="said_no")
            self.show("idle")
            return {"med": med, "for": person, "status": "due"}
        if self.demo:                           # demo: no dose log, no schedule, just praise
            self.log("dose_demo", person, med=med, how=how)
            self.hub.publish({"type": "dose_taken", "med": med, "for": person, "at": time.strftime("%H:%M"),
                              "how": how, "demo": True})
            if how != "auto":
                self.show(f"happy Well done!|{m['name']}")
            self.say(f"Well done, {self.store.name(person)}.")
            return {"med": med, "for": person, "status": "taken", "demo": True}
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
