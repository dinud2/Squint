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
only when something needs them. Over weeks, Squint also notices when someone's routine starts to
change (doses later and later, more double-dose attempts, more mix-ups) and says so gently.
It never claims to diagnose anything.

## How the pieces fit

```
          counter (the elder side)                                 caregiver side
 ┌─────────────────────────────────────────────┐
 │ C270 (faces + bottles) ───┐  pi/camstream   │
 │                           ▼  :8080          │
 │                Raspberry Pi 5 (QNX)         │
 │                buddy/  service :8081 ───────┼──────▶ ios/  Squint app
 │                 faces · bottles · schedule  │   people, medicines, today's doses,
 │                 coordinator · dose log      │   live mirror of Squint's face,
 │                 journal · insights          │   routine trends (/insights)
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
| [`ios/`](ios/README.md) | Caregiver app (SwiftUI): setup, today's doses, live Squint, routine trends, label scanning | Ved | working (demo + live) |
| [`home/`](home/README.md) | The voice: offline Piper text-to-speech, cast to a Google Nest (or played on the laptop) | Ved | working |
| [`rig/`](rig/README.md) | Blender scene of the counter and an STL mount for the C270 | Ved | done |
| [`docs/`](docs/) | [API contract](docs/api-contract.md), [Tab5 ↔ Pi link](docs/tab5-pi.md), [decline tracking](docs/decline-tracking.md) | all | |

## Run the demo

1. **Pi** (after a reboot): `ssh qnxuser@<pi> ./squint_start.sh`
   - This starts the C270 stream and the service on `:8081`.
   - Add `SQUINT_ARGS="--announce http://<laptop>:8765/announce"` to make the Nest speak.
   - Check it at `http://<pi>:8081/cams` (the camera view) and `http://<pi>:8081/today`.
2. **Voice** (laptop): `cd home && .venv/bin/python server.py`
   - Add `--local` to play through the laptop speakers or a Bluetooth speaker instead of the Nest.
3. **Tab5:** put the Wi-Fi details and the Pi's address in `tab5-face/secrets.h`, then flash it. It
   polls the Pi on its own.
4. **App:** open the app, go to Settings, turn off *Use demo data*, and set the station to `http://<pi>:8081`.

All of these must be on the same network. On the phone hotspot the Pi has been `172.20.10.9`.

For the Trends tab to have something to show on a fresh station, stop the service and seed a few
weeks of made-up history first: `cd buddy && python3 tools/seed_history.py` (`--clear` removes it).

## What's next

- **Model tweaks for routine tracking** (the order and why are in
  [docs/decline-tracking.md](docs/decline-tracking.md#do-the-models-need-to-change)):
  1. Give the bottle to the nearest face in the same frame, so two people at the counter don't
     get mixed up. This is geometry only, no retraining.
  2. Real hand-to-mouth detection, so "taken" doesn't rely on the Tab5 answer (MoveNet, from
     `archive/old-idea`).
  3. Log a bottle put back with nothing confirmed as an unsure moment.
- **Stress testing:** more training for the face and bottle models (and the `_other` class), and
  long runs on the Tab5.
- **Backend:** push events to the app instead of polling, and upload enrolment photos from the
  app so a laptop isn't needed.
- **Live mode away from home:** a tunnel (e.g. `cloudflared`) from the Pi, so the app works off
  the home network.

## History

Earlier ideas are kept as tags, not branches:
- `archive/old-idea` has Squint v1, which anticipated the pill reaching the mouth from body pose.

```bash
git checkout archive/old-idea
```
