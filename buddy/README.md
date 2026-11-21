# buddy: the Squint backend

This runs on the Raspberry Pi (QNX), or on a laptop for testing. It reads the two cameras, works out
**who** is at the counter and **which bottle** they picked up, decides what should happen, and
serves everything over HTTP on port **8081**.

It is pure Python + OpenCV + NumPy. The HTTP server is the standard library's, so it runs on QNX.

## Run

```bash
# on the Pi, the usual way: starts both camera streams and this service
./squint_start.sh                       # see pi/squint_start.sh

# by hand
python3 -m buddy.service --bottle-source http://localhost:8080/stream \
                         --face-source  http://localhost:8082/stream \
                         --announce     http://<laptop>:8765/announce
```

| Flag | Default | Meaning |
|---|---|---|
| `--bottle-source` | `http://localhost:8080/stream` | MJPEG stream from the camera pointing **down** at the bottles (Brio 101) |
| `--face-source` | off | MJPEG stream from the camera pointing **up** at the person (C270) |
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
                     (data/store.json)
  faces.py           face detection (YuNet) + recognition (SFace)
  presence.py        smooths per-frame faces into "who is at the counter"
  bottles.py         bottle recognition by embedding similarity
  bottle_service.py  / bottle_tracker.py   steady bottle decisions from the live camera
  detector.py, camera.py   object detection, and reading an MJPEG stream (newest frame only)
models/              the ONNX models the Pi runs (committed: the Pi can't regenerate them)
tools/               enrolment and live-check scripts (below)
data/                personal data, git-ignored: faces, bottle photos, store.json
```

## Enrol people and bottles

```bash
python tools/enroll_face.py   --name dinu    --source http://<pi>:8082/stream   # ~40 photos, guided poses
python tools/enroll_bottle.py --name tylenol --reset                            # name = medication id
python tools/enroll_bottle.py --name _other     # things that are NOT medicine (hands, cups...)
python tools/face_live.py     --source http://<pi>:8082/stream                  # who does it see?
```

**Never commit `data/`.** It holds people's faces and medicines.

## How a dose goes

1. **People arrive.** The Tab5 gets `presence`, then `remind ...`, and the Nest says hello and what to
   take. Each person is greeted at most once every 2 minutes.
2. **The right bottle is picked up.** The dose is pending. If intake confidence is ≥ 0.90 it
   auto-confirms after 2 s; otherwise the person answers on the Tab5 (`POST /doses/confirm`).
3. **Someone else's bottle** shows `wrong` on the Tab5 and the Nest warns.
4. **A high-risk medicine that was already taken today** shows `stop`, and the Nest says *"Stop, you
   already took it at 8:02"*.
5. **Everybody leaves**, and the Tab5 gets `away` and falls asleep.

Every outcome is written to the dose log (`store.py`). That log is what the iOS app reads, and
what cognitive-decline tracking will build on.

## Testing without the cameras

```bash
curl localhost:8081/today
curl -X POST localhost:8081/tab5/send -d '{"line": "happy Well done!|Tylenol"}'   # drive the Tab5 face
curl -X POST localhost:8081/intake    -d '{"person": "dinu", "confidence": 0.95}' # fake hand-to-mouth
curl -N localhost:8081/events                                                     # watch events live
```
