# Live demo: 3 minutes, no slides, four of us

The projector shows the **x-ray view** (`buddy/tools/squint_view.py`): the Pi's camera, with the
numbers behind every decision next to it. A second window is a terminal on the Pi. Every line
starts on a **cue**, something you see or hear at the counter, so nobody watches the clock.

## The two tracks we're pitching to

We say both out loud in the demo, not just in Q&A.

| Track | What its judges look for | Our answer in one line |
|---|---|---|
| **QNX** | Real use of QNX on embedded hardware: its APIs, its real-time scheduling, reliability, not "Linux with a different logo". | The whole product runs on a Raspberry Pi 5 under QNX 8. We wrote the camera driver client against QNX's native camera API, run it at real-time priority so AI work can't starve it, and the system restarts itself through QNX's own tools. |
| **Health hack** (Sun Life, see note) | Real health impact, a real user, something people would use. | Medication errors put older people in hospital every day. Squint stops the most dangerous one, the double dose, at the moment it happens, using the bottles they already have, and tells the family. |

> **Check the sponsor:** we couldn't open this year's Devpost prize page. At Hack Western 10 and 12
> the health prize was **Sun Life's "Best Health Hack"**; Canada Life's tracks have been mental
> well-being, investing and the workplace. Confirm on Devpost or at the opening and change the name
> here if it's different.

## Who does what

| Who | Where | Job on stage | Questions they take |
|---|---|---|---|
| **Ved** | beside the counter, phone in hand | opens, tells the story, shows each notification, makes the health case, closes | product, users, the app, Sun Life |
| **Dinu** | at the counter as the person taking pills, then the screen | acts the morning, then explains how the AI decides | models and accuracy |
| **Kathy** | at the screen, then at the counter | explains the numbers as they move; walks up for the mix-up | the face, the Tab5, design |
| **Kamal** | off to the side, then the counter, then the terminal | the stranger nobody enrolled; then shows QNX running live | QNX, the Pi, the camera |

## Before going on (15 min)

1. Phone hotspot on; Pi, Tab5, laptop and iPhone on it. Addresses: `ipconfig getifaddr en0`
   (laptop), the SSH scan in the README (Pi).
2. Latest `buddy/` on the Pi: `scp -r buddy/buddy qnxuser@<pi>:/data/home/qnxuser/buddy/`.
3. Voice: `cd home && .venv/bin/python server.py --local`, Google Home paired, volume ~70%.
4. Station in **real mode** (the default `--demo` logs no doses, so no STOP and no notifications):
   `ssh qnxuser@<pi> 'SQUINT_DEMO= SQUINT_ARGS="--announce http://<laptop>:8765/announce" ./squint_start.sh'`
5. App: *Use demo data* off, station `http://<pi>:8081`. Dinu's Tylenol set to **the current time**
   and **High risk**. A new time is a fresh, untaken dose, so this also resets after a rehearsal.
   Notifications on, sound up, Focus off.
6. Projector, left: `cd buddy && .venv/bin/python tools/squint_view.py --pi <pi>`.
   Right: a terminal already logged in, `ssh qnxuser@<pi>`, font large, with this typed and ready:
   `pidin | grep -E "camstream|python3|sensor"`. Run it once to check the `prio` column shows
   `20r` for camstream.
7. `python3 buddy/tools/doctor.py`: no warnings. Tab5 asleep (blue eyes). Trends seeded
   (`tools/seed_history.py`, with the service stopped).
8. Camera aimed so faces sit mid-frame; even light; nothing red or orange near the bottles. Kamal
   is **not** enrolled; check he shows as "unknown" in the x-ray view.

## The script

### 0:00 · Hook (health)
*Cue: Tab5 asleep. The x-ray view says "Nobody at the counter".*

- **Ved:** In Canada, about one senior in every two hundred ends up in hospital each year from a
  reaction to their own medicine, and blood thinners are the most common cause. Usually it isn't
  complicated. It's the second dose you don't remember taking.
- **Ved:** This is Squint. It sits on the counter where they already keep their pills. Right now
  it's asleep, because nobody's there. Dinu, it's eight o'clock.

### 0:20 · It knows who's there
*Cue: Dinu walks up → "Hi Dinu!" on the Tab5; the Google Home: "Hi Dinu, today you take Tylenol."*

- **Dinu:** Morning, Squint.
- **Kathy** *(pointing at WHO IS HERE)*: That bar is Dinu's face against his forty enrolment photos:
  point seven. Mine is point three. It only names you if you clear that line *and* beat everyone
  else by point oh eight.

> No greeting in 3 s: Dinu steps closer, looks at the camera. Kathy: "it waits for two clear
> frames, so someone walking past doesn't count."

### 0:40 · The right bottle, taken
*Cue: Dinu holds up his Tylenol → green "Tylenol" box, then "Did you take it?" on the Tab5.*

- **Ved:** He hasn't pressed a thing.
- **Kathy** *(WHICH BOTTLE)*: Colour finds the red label. A network we trained judges it: Tylenol,
  point nine. Both have to agree, or it says "not sure". It never guesses.
- **Kathy** *(Dinu's hand goes to his mouth)*: Now a palm detector is watching his mouth. Two
  frames, point nine five: it ticks yes by itself.
- **Ved** *(gold star, "Well done, Dinu"; phone up)*: And his daughter just got this. "Dinu took
  his Tylenol, at 8:02." No call needed.

> Not named: turn the label to the camera. No auto-tick: Dinu taps Yes. Kathy: "when it isn't
> sure, it asks."

### 1:10 · The STOP
*Cue: Ved: "forty minutes later". Dinu picks the Tylenol up again → red eyes; "Stop, Dinu. You
already took your Tylenol at 8:02."*

- **Ved:** Forty minutes later, he doesn't remember. This is the moment that sends people to
  hospital.
- **Kathy** *(after the voice)*: Red eyes, a flashing frame, two big words. Nothing to read and no
  app to learn.
- **Ved** *(phone up)*: And this one comes with a sound: "Squint stepped in for Dinu."

> No STOP: Tylenol isn't High risk, or the station is in demo mode. Say what it would do; move on.

### 1:30 · The mix-up
*Cue: Dinu walks out of view to the screen. Count three. Kathy walks up → "Hi Kathy", picks up
Dinu's Tylenol → amber "Dinu's pills"; "Careful Kathy, that's Dinu's Tylenol."*

- **Ved:** Couples keep their pills together. Same counter, same red labels.
- **Dinu** *(at the screen)*: It knows whose bottle that is, and that I'm not at the counter. Three
  models, one camera: faces, labels, and the hand at the mouth.

> No warning: Dinu was still in frame. He must be out of view for 3 s before she picks it up.

### 1:50 · The stranger
*Cue: Kathy steps out of view (3 s). Kamal walks up → no greeting, the x-ray says "unknown". He picks
up the Tylenol → amber "Who's there?"; "I don't recognise you, so I can't check whose Tylenol this is."*

- **Kamal:** I'm not enrolled. It didn't greet me, it doesn't guess who I am, and it won't tell me a
  pill is mine.
- **Dinu** *(pointing at the bars)*: Nobody clears the line, so it's "unknown". Saying "I'm not sure"
  is the safety feature.

### 2:05 · QNX, live
*Cue: Kamal goes to the terminal and runs the `pidin` line.*

- **Kamal:** All of this is running on that Raspberry Pi, under QNX 8. These are the live processes.
  Camstream is ours, in C, on QNX's native camera API. It runs at priority twenty, real-time, so
  however hard the AI is working, the camera never misses a frame.
- **Kamal:** The camera driver runs as its own process, QNX's sensor service. If it ever drops,
  our start script restarts it and waits for the device to come back. That's the kind of
  reliability you want from something guarding someone's medicine. No cloud, no internet: faces
  stay on the Pi as 128 numbers each.

> Terminal slow: skip running it and say the lines anyway; it was checked before going on.

### 2:30 · Weeks, not moments (health)
*Cue: Ved opens Trends and holds the phone up.*

- **Ved:** Every moment you just saw is logged. Over weeks, Squint compares Dinu with Dinu: doses
  drifting later, more double-dose attempts, more mix-ups. When that changes, it tells his family
  it's worth a chat with his doctor. It never diagnoses.
- **Ved:** That's what lets people keep living at home, and keeps a family caregiver from being on
  call all day.

### 2:50 · Close
*Cue: all four step together. The Tab5 falls asleep behind them.*

- **Dinu:** On recordings we held out, it named zero wrong bottles.
- **Kamal:** Real-time, on QNX, on a Raspberry Pi on the counter.
- **Ved:** Squint. So you don't have to be there to be there.

**If anything stalls:** say what Squint *should* do and why, give it 3 seconds, move on. Never
apologise twice.

## When a track judge comes by (60 seconds each)

Use these at the table instead of the full script, or right after it.

### QNX judge (Kamal leads, Dinu backs up)
1. **The stack on QNX:** QNX 8 on a Pi 5; `camstream.c` (C, `libcamapi` + libturbojpeg) serves
   MJPEG on :8080; the Python service (OpenCV `cv2.dnn`, NumPy, the standard library's HTTP server)
   on :8081. No PyTorch on the device: every model is ONNX through OpenCV.
2. **Native camera API, no headers:** QNX's camera headers weren't on the device, so we declared
   the few functions we need ourselves and read the `camera_buffer_t` layout off a live frame with
   `probe.c`.
3. **Real-time priority:** `on -p 20 ./camstream` runs the camera above the recognition work, so a
   slow model drops frames on *its* side (newest frame only) and never stalls capture. Frames are
   handed over with a `pthread` mutex and condition variable.
4. **Configuring QNX itself:** we pinned the sensor service's USB unit to the C270's vendor and
   product IDs in `sensor_rpi5.conf`.
5. **Self-healing start:** `squint_start.sh` uses `pidin` to find and stop old processes, restarts
   the `sensor` service if `/dev/sensor/camera5` is missing, and `waitfor`s the device before
   starting.
6. **Next on QNX:** move recognition into separate processes with their own priorities, and talk
   between them with QNX message passing instead of HTTP.

### Health judge (Ved leads, Dinu backs up)
1. **The user:** older couples who share a counter and take several medicines, and the adult child
   who worries. Nothing to wear, charge or learn for the elder.
2. **The harm we stop:** the double dose of a high-risk drug (blood thinners top Canada's list),
   the partner's bottle, and missed doses, at the moment they happen.
3. **The family:** a quiet notification when a dose is taken, a loud one only for a STOP or a
   missed dose; Siri and a widget for "has Dad taken his pills?".
4. **Over weeks:** routine tracking against the person's own usual, with eight signals. It never
   diagnoses; it suggests a chat with their doctor.
5. **Privacy:** no video leaves the house or is stored; faces are 128 numbers on the Pi.
6. **Who pays:** families first. Then insurers' and employers' benefits, for the employees who are
   their parents' caregivers, and home-care agencies and pharmacies, who all care about
   medication adherence.

## Questions (2 min)

One or two sentences, then stop. Pass to the owner: models → Dinu, the face and hardware → Kathy,
QNX and the Pi → Kamal, product and health → Ved. Details: [models.md](models.md),
[architecture.md](architecture.md).

| Question | Who | Answer |
|---|---|---|
| How accurate is it? | Dinu | On whole recording sessions we held out: 0 wrong bottles in 339 photos; what it wasn't sure of came out as "not sure". Small dataset, so the claim is the design: two cues must agree, thresholds tuned for zero wrong answers. |
| What if it's wrong? | Dinu | Being wrong mostly means "not sure", which costs a second. A green check for the wrong medicine is the error we design against, and the person can always tap No. |
| Can it tell they swallowed it? | Dinu | No. It sees the hand reach the mouth right after the right bottle. Confident: it confirms. Not: it asks. The log says which. |
| Why QNX and not Linux? | Kamal | A real-time microkernel used in cars and medical devices: drivers run as separate processes and priorities are strict, so the camera can't be starved and a crashed driver can be restarted without taking the system down. That's the bar for a safety device. |
| What was hard about QNX? | Kamal | No camera headers, no PyTorch, few Python wheels. We wrote the camera streamer in C against the native API and run every model through OpenCV. |
| Why train your own model? | Dinu | It runs on the Pi, offline, every frame. A 6 MB MobileNet on label crops does; a cloud model would send video of a kitchen off the device. |
| New medicine? | Dinu | Today: photos and a retrain, minutes on a laptop. The app already reads pharmacy labels with on-device OCR; next is matching the bottle to that label. |
| Two people at the counter? | Dinu | A bottle counts as its owner's if they're at the counter. Next: give it to the nearest hand, which is geometry on what we already detect. |
| Why a face? | Kathy | Older adults shouldn't need to learn an app. It sleeps until you walk up, uses a few big words, and the eye colour does the work: white fine, amber check, red stop. |
| Real-time notifications? | Ved | App open: seconds. Closed: iOS's background refresh. Instant needs Apple push and a small relay, which is next. |
| Surveillance? | Ved | No video is stored or uploaded. The family sees doses and sentences, never a camera feed. |
| Diagnosing dementia? | Ved | No. It compares someone with their own usual and says "worth a chat with their doctor". |
| Why not a pill dispenser? | Ved | Dispensers mean reloading cartridges and a new routine. Squint watches the bottles they already use, and handles two people on one counter. |
| Who pays? | Ved | The adult child first. Then benefits plans, for employees caring for a parent, and home-care agencies and pharmacies. |
| What doesn't work yet? | Ved | New medicines need photos; hand-to-mouth is evidence, not proof; closed-app notifications aren't instant; the Pi's address is fixed in the Tab5's firmware. |

Sources: Canadian figure: CIHI, *Adverse Drug Reaction–Related Hospitalizations Among Seniors,
2006 to 2011* (about 1 in 200 Canadians 65+ in 2010–2011; blood thinners the most common drug class,
12.6%). US figure, if asked: Budnitz et al., NEJM 2011.
