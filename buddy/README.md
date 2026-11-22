# buddy: the Squint backend

This runs on the Raspberry Pi (QNX), or on a laptop for testing. It reads one camera (a C270 facing
the person), works out **who** is at the counter and **which bottle** they picked up, decides what should happen, and
serves everything over HTTP on port **8081**.

It is pure Python + OpenCV + NumPy. The HTTP server is the standard library's, so it runs on QNX.

**On a laptop**, install into a venv. Use OpenCV 4: OpenCV 5 crashes in face alignment.

```bash
cd buddy && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m buddy.service --bottle-source 0 --face-source 0     # 0 = the laptop webcam
```

A source can also be a video file (it loops), handy for testing without a camera.

## Run

```bash
# on the Pi, the usual way: starts the camera stream and this service
./squint_start.sh                       # see pi/squint_start.sh

# by hand
python3 -m buddy.service --bottle-source http://localhost:8080/stream \
                         --face-source  http://localhost:8080/stream \
                         --announce     http://<laptop>:8765/announce
```

| Flag | Default | Meaning |
|---|---|---|
| `--bottle-source` | `http://localhost:8080/stream` | MJPEG stream the bottles are recognised in |
| `--face-source` | off | MJPEG stream the faces are recognised in. On the Pi both are the same C270 stream |
| `--bottle-mode` | `color` | `color`: the bottle anywhere in view, by label colour + the label classifier; `show`: held up in the centre box; `counter`: picked up off the counter |
| `--demo` | off (on in `squint_start.sh`) | only check whose medicine it is: own → "Yes Dinu, that's your Tylenol", someone else's → warning. No dose times, "not yet", "already taken" or dose log |
| `--announce` | off | the voice service (`home/server.py`); without it, Squint stays silent |
| `--bottle-fps` / `--det-scale` | 4 / 0.5 | lower these if the Pi can't keep up |
| `--verbose` | | print every frame's result |

## Files

```
buddy/
  service.py         entry point: camera loops → events → coordinator → API
  api.py             the HTTP API (endpoints in docs/api-contract.md) and the event hub
  coordinator.py     the decisions: greet, remind, wrong bottle, STOP, auto-confirm,
                     and the Tab5 command queue
  store.py           people, medicines, today's doses and the dose log per day
                     (data/store.json); /history reads past days from it
  journal.py         append-only log of everything that happened at the counter
                     (data/journal.jsonl): arrivals, mix-ups, double-dose attempts, unsure moments
  insights.py        routine tracking: each person's last week against their own usual
                     (docs/decline-tracking.md), served as /insights
  faces.py           face detection (YuNet) + recognition (SFace)
  colors.py          which bottle: label colour finds it, the label classifier confirms (docs/models.md)
  intake.py          hand to mouth: MediaPipe palm detector near the mouth, while a dose waits
  palmdet.py         the palm detector's pre/post-processing (OpenCV model zoo)
  presence.py        smooths per-frame faces into "who is at the counter"
  bottles.py         bottle recognition by embedding similarity
  bottle_service.py  / bottle_tracker.py   steady bottle decisions from the live camera
  detector.py, camera.py   object detection, and reading an MJPEG stream (newest frame only)
  diag.py            what each part last did, and plain-English warnings, for GET /health
models/              the ONNX models the Pi runs (committed: the Pi can't regenerate them)
tools/               enrolment and live-check scripts (below), seed_history.py, and doctor.py
data/                personal data, git-ignored: faces, bottle photos, store.json, journal.jsonl
```

## Is it working?

Run this on the laptop while the Pi is on the same network. It finds the Pi on the phone hotspot:

```bash
python3 tools/doctor.py                  # or: --pi 172.20.10.3
```

It checks the following, then lists what to fix:
- the camera stream
- what the face and bottle loops last saw, and where the face was in the picture
- whether announcements reach the laptop, and whether that's really this laptop's address
- whether the Tab5 and the app are asking the Pi for commands

The same facts are in `GET /health` under `warnings`. Its typical findings:

| Warning | Usually means |
|---|---|
| The Tab5 has never asked for commands | `SQUINT_PI_HOST` in `tab5-face/secrets.h` is an old address: reflash |
| The face is at the edge of the picture | aim the camera so faces sit in the middle |
| No face seen for over 60 s | the camera points above or beside where people stand |
| Someone is in view but not recognised | only enrolled people are greeted, by design |
| No `_other` bottle class | heads and hands can score close to a bottle: enrol `_other` |
| The last announcement failed | `home/server.py` isn't running, or the laptop's address changed |

To watch every frame's decision, start the service with `--verbose` (on the Pi:
`SQUINT_ARGS="--verbose --announce ..." ./squint_start.sh`, then `tail -f ~/buddy/service.log`).
Greetings are spoken at most once per person every 2 minutes, so a quick second walk-up only wakes
the face.

## Bottle recognition (colour + label classifier)

`buddy/colors.py`: blue label = Advil, orange = Motrin, red = Tylenol or Vitamin D. Loose colour
ranges find candidate label patches anywhere in the frame; a classifier on a tight crop around each
patch may only veto it (not a bottle), split red into Tylenol / Vitamin D, or say "not sure" when
it sees a medicine of another colour. It never overrules the colour with a guess.

```bash
# record varied full frames: one session per person / room / light / distance (laptop, Pi on the hotspot)
python tools/capture_frames.py advil  --tag kathy-kitchen-dim --out <data>/frames
python tools/capture_frames.py _other --tag red-shirt         --out <data>/frames
# honest check: whole sessions held out + real Pi frames (a folder with truth.json), wrong vs not sure
python tools/train_label_classifier.py --data <data> --real <dir with truth.json>
# then train on everything and write models/bottle_classifier.onnx + bottle_classes.json
python tools/train_label_classifier.py --data <data> --all
```

## Enrol people and bottles

```bash
python tools/enroll_face.py   --name dinu    --source http://<pi>:8080/stream   # ~40 photos, guided poses
python tools/enroll_bottle.py --name tylenol --reset                            # name = medication id
python tools/enroll_bottle.py --name _other     # things that are NOT medicine (hands, cups...)
python tools/face_live.py     --source http://<pi>:8080/stream                  # who does it see?
```

**Never commit `data/`.** It holds people's faces and medicines.

## How a dose goes

1. **People arrive.** The Tab5 gets `presence`, then `remind ...`, and the Nest says hello and what to
   take. Each person is greeted at most once every 2 minutes.
2. **The right bottle is picked up.** The dose is pending. If hand-to-mouth confidence is ≥ 0.75 it
   auto-confirms after 2 s; otherwise the person answers on the Tab5 (`POST /doses/confirm`).
3. **Someone else's bottle** shows `wrong` on the Tab5 and the Nest warns.
4. **A high-risk medicine that was already taken today** shows `stop`, and the Nest says *"Stop, you
   already took it at 8:02"*.
5. **Everybody leaves**, and the Tab5 gets `away` and falls asleep.

Every outcome is written to the dose log (`store.py`), and every moment along the way (arrived,
left without taking anything, wrong bottle, double-dose attempt, didn't answer "Did you take it?")
to the journal (`journal.py`). The app's Today tab reads the dose log; its Trends tab reads
`/insights`, which compares the last week of both against the four weeks before.

## Routine tracking

`insights.py` turns the dose log and journal into eight signals per person (doses taken, timing,
regularity, double-dose attempts, mix-ups, unsure moments, visits with nothing taken, time to
finish), each compared with that person's own usual. Why these and what the thresholds are:
[docs/decline-tracking.md](../docs/decline-tracking.md). It needs a week of usual before it says
anything, so for a demo, seed some history:

```bash
# stop buddy.service first: it keeps store.json in memory and would overwrite the seeded days
python3 tools/seed_history.py                   # 35 days; the first elder's routine slips lately
python3 tools/seed_history.py --decline kathy   # choose who slips ("" = nobody)
python3 tools/seed_history.py --clear           # remove everything it wrote (it's all marked synthetic)
```

## Testing without the cameras

```bash
curl localhost:8081/today
curl 'localhost:8081/insights?days=30'                                           # routine tracking
curl -X POST localhost:8081/tab5/send -d '{"line": "happy Well done!|Tylenol"}'   # drive the Tab5 face
curl -X POST localhost:8081/intake    -d '{"person": "dinu", "confidence": 0.95}' # inject a hand-to-mouth reading
curl -N localhost:8081/events                                                     # watch events live
```
