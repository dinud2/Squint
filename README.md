# Squint

A counter-top medicine buddy for older couples who keep their medicines together.

Squint is a small 3D-printed figure with a face (an M5Stack Tab5). It sits by the pill bottles.

When someone walks up, it:
- recognises who it is
- greets them on a Google Home
- reminds them what to take
- checks with a camera that **the right person picks up the right bottle**

It stops a second dose of a high-risk drug, and warns when someone picks up their partner's
medicine. Their children set it up once in the iOS app, then see each day at a glance and get told
only when something needs them.

## How the pieces fit

```
          counter (the elder side)                                 caregiver side
 ┌─────────────────────────────────────────────┐
 │ Brio 101 (down, bottles) ─┐                 │
 │ C270 (up, faces) ─────────┤  pi/camstream   │
 │                           ▼  :8080 / :8082  │
 │                Raspberry Pi 5 (QNX)         │
 │                buddy/  service :8081 ───────┼──────▶ ios/  Squint app
 │                 faces · bottles · schedule  │   people, medicines, today's doses,
 │                 coordinator · dose log      │   live mirror of Squint's face
 │                    │               │        │
 │   GET /tab5/commands       POST /announce   │
 │                    ▼               ▼        │
 │   tab5-face/ (Tab5 face)   home/ (laptop :8765) ──▶ Google Nest (calm Piper voice)
 └─────────────────────────────────────────────┘
```

Everything talks plain HTTP + JSON on one local network. The endpoints are in
[docs/api-contract.md](docs/api-contract.md).

## What's in this repo

| Folder | What it is | Owner | State |
|---|---|---|---|
| [`buddy/`](buddy/README.md) | **The backend**, which runs on the Pi: face and bottle recognition, the coordinator, the schedule and dose log, and the HTTP API on `:8081` | Dinu | working |
| [`tab5-face/`](tab5-face/README.md) | Tab5 firmware (Arduino): Squint's eyes and big words, which fetches its commands from the Pi | Kathy | working on the Tab5 |
| [`pi/`](pi/README.md) | Camera streams for QNX (`camstream.c`) and `squint_start.sh` to start everything after a reboot | Dinu | working |
| [`ios/`](ios/README.md) | Caregiver app (SwiftUI): setup, today's doses, live Squint, label scanning | Ved | working (demo + live) |
| [`home/`](home/README.md) | The voice: offline Piper text-to-speech, cast to a Google Nest (or played on the laptop) | Ved | working |
| [`rig/`](rig/README.md) | Blender scene of the counter and an STL mount for the C270 | Ved | done |
| [`docs/`](docs/) | [API contract](docs/api-contract.md), [Tab5 ↔ Pi link](docs/tab5-pi.md) | all | |

## Run the demo

1. **Pi** (after a reboot): `ssh qnxuser@<pi> ./squint_start.sh`
   - This starts both cameras and the service on `:8081`.
   - Add `SQUINT_ARGS="--announce http://<laptop>:8765/announce"` to make the Nest speak.
   - Check it at `http://<pi>:8081/cams` (both camera views) and `http://<pi>:8081/today`.
2. **Voice** (laptop): `cd home && .venv/bin/python server.py`
   - Add `--local` to play through the laptop speakers or a Bluetooth speaker instead of the Nest.
3. **Tab5:** put the Wi-Fi details and the Pi's address in `tab5-face/secrets.h`, then flash it. It
   polls the Pi on its own.
4. **App:** open the app, go to Settings, turn off *Use demo data*, and set the station to `http://<pi>:8081`.

All of these must be on the same network. On the phone hotspot the Pi has been `172.20.10.9`.

## What's next

- **Backend.** The store already keeps a dose log per day in `buddy/data/store.json`, but the API
  only serves today. Still to do:
  - a history endpoint
  - pushing events to the app instead of it polling
  - uploading photos from the app (faces, bottles) so enrolment doesn't need a laptop
- **Cognitive decline tracking.** Squint sees the same routine every day, so it can notice slow
  changes no single check-up would catch, and show the caregiver a trend. Signals the station can
  already measure or almost can:
  - doses taken later and later, or missed
  - picking up the wrong bottle, or the partner's
  - repeated attempts at a dose already taken (the STOP events)
  - hesitating at the counter, or asking "did I take it?"

  The design (which signals, the baselines, what the caregiver sees) is still to be written up.
- **Stress testing:** more training for the face and bottle models, and long runs on the Tab5.

## History

Earlier ideas are kept as tags, not branches:
- `archive/old-idea` has Squint v1, which anticipated the pill reaching the mouth from body pose.

```bash
git checkout archive/old-idea
```
