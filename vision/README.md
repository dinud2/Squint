# Part C — Squint vision (AI)

Which bottle is in her hand, and is a pill about to go into her mouth? Everything runs on the
station, in Python + ONNX (ONNX Runtime **or** OpenCV DNN, so it works on QNX either way).
Evaluation numbers and plots are in `reports/`.

## Setup (laptop)

```bash
cd vision
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python tools/export_models.py          # MobileNetV3 embedder + MoveNet -> models/
.venv/bin/python tools/train_bottle_embed.py     # bottle embedder (≈4 min on an M-series Mac)
```

On the Pi you only need `numpy`, `opencv` and (ideally) `onnxruntime`, plus the `models/` folder.

## Run it

| What | Command |
|---|---|
| Fake messages for other parts (C1) | `python fake_vision.py [--scenario morning/correct/double/robert/unknown]` |
| Watch the bus | `python tools/bus_monitor.py` |
| Live, laptop webcam | `python vision_main.py --source 0 --show` |
| Live, on the Pi | `python vision_main.py --source qnx --bottle-every 2` |
| No camera, full pipeline | `python vision_main.py --sim double` (also `correct`, `robert`, `unknown`, `scratch`, `read`) |
| Enrol the empty hand once per setup | `python vision_main.py --source 0 --enroll-empty` |
| Tests | `python tests/test_part_c.py` |
| Speed per stage | `python tools/speed_test.py` |

## Cameras: test first, then plug in

Dinu's `pi/camstream.c` (branch `pi-camera-stream`) owns the QNX camera and serves MJPEG at
`http://<pi>:8080/stream`. Vision reads that stream (only one process can hold the camera).

```bash
# 1. no Pi needed: a stand-in camstream on the laptop (webcam, clip, or test pattern)
python tools/fake_camstream.py --source 0
python tools/camera_check.py --source http://localhost:8080/stream --show

# 2. the real Pi, from the laptop (same Wi-Fi / phone hotspot)
python tools/camera_check.py --source http://<pi-ip>:8080/stream --show
python vision_main.py --source http://<pi-ip>:8080/stream --show

# 3. on the Pi itself (needs python3 + numpy + opencv, ideally onnxruntime: task C3)
python3 vision_main.py --source http://localhost:8080/stream --bottle-every 2
```

`camera_check` must show **nose ≥ 80%** and a wrist visible when you raise a hand to your mouth.
The station camera is the standard Camera Module 3 (~66°): Margaret should be about 0.9–1.4 m away.
If the face or hands are cut off, move the camera back or tilt it. The intake model is trained for this framing.

## What Part C puts on the bus

| Message | Fields | Notes |
|---|---|---|
| `bottle_seen` | `med`, `confidence`, `frame_time` | `med` is an enrolled id, `"unknown"` or **`"none"`** (hand empty / bottle put down). Sent only when the stable answer changes (4 of the last 5 frames). *`"none"` is an addition to the contract. D: treat it as "no bottle in hand".* |
| `intake_start` | `confidence`, `lead_ms`, `med`, `frame_time` | Fired only while a bottle is (or was in the last 8 s) in her hand. `lead_ms` = predicted time until the hand reaches the mouth. |
| `intake_done` | `med` | Hand reached the mouth and left again after an `intake_start`. |
| `enroll_progress` | `med`, `percent` | 15 photos over ~6 s after `enroll_start`. |

Listens for `enroll_start {med}` and `meds_changed`. Writes `data/camera.jpg` (atomic, ~2 Hz) for the API's `GET /camera.jpg`.

`bus.py` here is a **stand-in** that follows B's contract (UDP multicast on localhost, automatic `alive`). Delete it when B's library lands.

## Retraining with real clips (Sat 11:00 session)

```bash
python tools/record_clips.py --who ved           # keys 1-8 pick the movement, SPACE records
python tools/extract_pose.py                     # clips -> pose sequences, auto-labelled
python tools/train_intake.py --clips data/clips_pose --sim
python tools/intake_report.py                    # numbers + plot for Devpost
python tools/bottle_eval.py                      # bottle thresholds + numbers
```

## Layout

```
bus.py                 stand-in bus (B owns the real one)
fake_vision.py         C1 scripted messages
vision_main.py         the real program
squint_vision/         pose, bottles (open-set gallery), intake (features, model, detector), camera, backend
sim/                   pose simulator (3D arm IK + MoveNet noise), bottle renderer, scoring
tools/                 export, train, evaluate, record, speed
models/                *.onnx (regenerate), intake_model.json, bottle_thresholds.json
reports/               numbers and plots
```
