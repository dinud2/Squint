# Live demo: 3 minutes, no slides

The projector shows the **x-ray view** (`buddy/tools/squint_view.py`): the Pi's camera, with the
numbers behind every decision next to it. Every line starts on a **cue**, something you see or
hear at the counter, so nobody watches the clock. After the demo there are 2 minutes of questions;
answers are at the end.

| Who | Where | Job |
|---|---|---|
| **Ved** | beside the counter, phone in hand | opens, tells the story, holds up each notification, closes |
| **Dinu** | at the counter (the person taking pills), then at the screen | acts; after the STOP explains the Pi |
| **Kathy** | at the screen, then at the counter | explains the numbers as they move; walks up for the mix-up |

## Before going on (15 min)

1. Phone hotspot on; Pi, Tab5, laptop and iPhone all on it. Addresses: `ipconfig getifaddr en0`
   (laptop), the SSH scan in the README (Pi).
2. Latest `buddy/` on the Pi: `scp -r buddy/buddy qnxuser@<pi>:/data/home/qnxuser/buddy/`.
3. Voice: `cd home && .venv/bin/python server.py --local`, Google Home paired, volume ~70%.
4. Station in **real mode** (the default `--demo` logs no doses, so no STOP and no notifications):
   `ssh qnxuser@<pi> 'SQUINT_DEMO= SQUINT_ARGS="--announce http://<laptop>:8765/announce" ./squint_start.sh'`
5. App: *Use demo data* off, station `http://<pi>:8081`. Dinu's Tylenol set to **the current time**
   and **High risk**. A new time is a fresh, untaken dose, so this also resets after a rehearsal.
   Notifications on, sound up, Focus off.
6. Projector: `cd buddy && .venv/bin/python tools/squint_view.py --pi <pi>`, then `f`.
7. `python3 buddy/tools/doctor.py`: no warnings. Tab5 asleep (blue eyes). Trends seeded
   (`tools/seed_history.py`, with the service stopped).
8. Camera aimed so faces sit mid-frame; even light; nothing red or orange near the bottles.

## The script

### 0:00 · Hook
*Cue: Tab5 asleep. The x-ray view says "Nobody at the counter".*

- **Ved:** Every year about a hundred thousand older Americans end up in hospital from their own
  medicine. Two in three are accidental overdoses, and usually it's just the second dose you don't
  remember taking.
- **Ved:** This is Squint. It's asleep, because nobody's at the counter. Dinu, it's morning.

### 0:20 · It knows who's there
*Cue: Dinu walks up → "Hi Dinu!" on the Tab5; the Google Home greets him.*

- **Dinu:** Morning, Squint.
- **Kathy** *(pointing at WHO IS HERE)*: That's Dinu's face against his forty enrolment photos:
  point seven. Mine is point three. It only names you if you clear that line and beat everyone else
  by point oh eight. Anyone else is just "unknown".

> No greeting in 3 s: Dinu steps closer and looks at the camera. Kathy: "it waits for two clear
> frames, so someone walking past doesn't count."

### 0:45 · The right bottle, taken
*Cue: Dinu holds up his Tylenol → green "Tylenol" box, then "Did you take it?" on the Tab5.*

- **Ved:** He hasn't pressed a thing.
- **Kathy** *(WHICH BOTTLE)*: Colour finds the red label. A network we trained looks at it and says
  Tylenol, point nine. Both have to agree, or it says "not sure". It never guesses.
- **Kathy** *(Dinu's hand goes to his mouth)*: Now it's watching his mouth with a palm detector. Two
  frames, point nine five: it ticks yes by itself.
- **Ved** *(gold star, "Well done, Dinu"; phone up)*: And his daughter just got this: Dinu took his
  Tylenol, at 8:02.

> Not named: turn the label to the camera. No auto-tick: Dinu taps Yes. Kathy: "when it isn't
> sure, it asks."

### 1:25 · The STOP
*Cue: "forty minutes later". Dinu picks the Tylenol up again → red eyes; "Stop, Dinu. You already
took your Tylenol…"*

- **Ved:** Forty minutes later, he doesn't remember. This is the moment that sends people to
  hospital.
- **Kathy** *(after the voice)*: Red eyes, a flashing frame, two big words. Nothing to read, no app
  for him to learn.
- **Ved** *(phone up)*: And this one comes with a sound: "Squint stepped in for Dinu."

> No STOP: Tylenol isn't High risk, or the station is in demo mode. Say what it would do and move on.

### 1:55 · The mix-up
*Cue: Dinu walks out of view to the screen. Count three. Kathy walks up → "Hi Kathy", picks up
Dinu's Tylenol → amber "Dinu's pills".*

- **Ved:** Couples keep their pills together. Same counter, same red labels.
- **Dinu** *(after "Careful Kathy, that's Dinu's Tylenol")*: It knows whose bottle that is, and that
  I'm not at the counter.
- **Dinu:** Everything you just saw runs on that Raspberry Pi, under QNX. Three models, one camera,
  no cloud. Our faces never leave the house: on the Pi we're 128 numbers each.

> No warning: Dinu was still in frame. He must be out of view for 3 s first.

### 2:25 · Weeks, not moments
*Cue: Ved opens Trends and holds the phone up.*

- **Ved:** Every moment you just saw is logged. Over weeks, Squint compares Dinu with Dinu: doses
  drifting later, more double-dose attempts. When something changes, it tells his daughter it's
  worth a chat. It never diagnoses.

### 2:45 · Close
*Cue: Kathy steps back beside Dinu. The Tab5 falls asleep.*

- **Dinu:** On recordings we held out, it named zero wrong bottles. When it isn't sure, it says so.
- **Ved:** Squint. So you don't have to be there to be there.

**If anything stalls:** say what Squint *should* do and why, give it 3 seconds, move on. Never
apologise twice.

## Questions (2 min)

One or two sentences, then stop. Model and accuracy questions → Dinu; the face and hardware →
Kathy; product and "who is it for" → Ved. Details: [models.md](models.md),
[architecture.md](architecture.md).

| Question | Answer |
|---|---|
| How accurate is it? | On whole recording sessions we held out: 0 wrong bottles in 339 photos; what it wasn't sure of came out as "not sure". Small dataset, so the claim is the design: two cues must agree, thresholds tuned for zero wrong answers. |
| What if it's wrong? | Being wrong mostly means "not sure", which costs a second. A green check for the wrong medicine is the error we design against, and the person can always tap No. |
| Can it tell they swallowed it? | No. It sees the hand reach the mouth right after the right bottle. Confident: it confirms. Not: it asks. The log says which. |
| Why train your own model, not a big vision model? | It runs on a Pi, offline, every frame. A 6 MB MobileNet on label crops does; a cloud model would send video of a kitchen off the device. |
| New medicine? | Today: photos and a retrain, minutes on a laptop. The app already reads pharmacy labels with on-device OCR; next is matching the bottle to that label. |
| Why QNX? | A real-time OS used in cars and medical devices. It cost us: no camera headers, no PyTorch, so a C camera streamer and every model through OpenCV's `cv2.dnn`. |
| Two people at the counter? | A bottle counts as its owner's if they're at the counter. Next: give it to the nearest hand, which is geometry on what we already detect. |
| Real-time notifications? | App open: seconds. Closed: iOS's background refresh. Instant needs Apple push and a small relay, which is next. |
| Surveillance? | No video is stored or uploaded. Faces are 128 numbers on the Pi. The caregiver sees doses and sentences, never a camera feed. |
| Diagnosing dementia? | No. It compares someone with their own usual and says "worth a chat". It never scores anyone's mind. |
| Why not a pill dispenser? | Dispensers mean reloading cartridges and a new routine. Squint watches the bottles they already use, and handles two people on one counter. |
| Who pays? | The adult child who worries. Later, home-care agencies and pharmacies. |
| What doesn't work yet? | New medicines need photos; hand-to-mouth is evidence, not proof; closed-app notifications aren't instant; the Pi's address is fixed in the Tab5's firmware. |
