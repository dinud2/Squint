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
only when something needs them. They can also just ask Siri (*"Has Dinu taken his pills in Squint?"*)
or look at a widget on their home or lock screen. Over weeks, Squint also notices when someone's
routine starts to change (doses later and later, more double-dose attempts, more mix-ups) and says
so gently. It never claims to diagnose anything.

## Where it stands (21 Nov 2026)

The whole loop runs on the real hardware on one phone hotspot:
- The camera on the Pi recognises a person.
- The Pi tells the Tab5 what face to show, and sends a greeting to the laptop, which speaks it on
  the Google Home.
- The iOS app, its widget and Siri read the same Pi.

What is not done yet is listed under [What's next](#whats-next). The physical setup (where the
camera and screen sit) has changed; its docs are being redone, so `rig/` was removed for now.

## How the pieces fit

```
          counter (the elder side)                                 caregiver side
 ┌─────────────────────────────────────────────┐
 │ C270 (faces + bottles) ───┐  pi/camstream   │
 │                           ▼  :8080          │
 │                Raspberry Pi 5 (QNX)         │
 │                buddy/  service :8081 ───────┼──────▶ ios/  Squint app, widget, Siri
 │                 faces · bottles · schedule  │   people, medicines, today's doses,
 │                 coordinator · dose log      │   live mirror of Squint's face,
 │                 journal · insights          │   routine trends (/insights)
 │                    │               │        │
 │   GET /tab5/commands       POST /announce   │
 │                    ▼               ▼        │
 │   tab5-face/ (Tab5 face)   home/ (laptop :8765) ──▶ Google Home (Cast, or Bluetooth
 └─────────────────────────────────────────────┘                     to the laptop)
```

Everything talks plain HTTP + JSON on one local network. The endpoints are in
[docs/api-contract.md](docs/api-contract.md).

## What's in this repo

| Folder | What it is | Owner | State |
|---|---|---|---|
| [`buddy/`](buddy/README.md) | **The backend**, which runs on the Pi: face and bottle recognition, the coordinator, the schedule and dose log, routine tracking, and the HTTP API on `:8081` | Dinu | working, tested live on the Pi |
| [`tab5-face/`](tab5-face/README.md) | Tab5 firmware (Arduino): Squint's eyes and big words, which fetches its commands from the Pi | Kathy | working on the Tab5 |
| [`pi/`](pi/README.md) | Camera stream for QNX (`camstream.c`) and `squint_start.sh` to start everything after a reboot | Dinu | working |
| [`ios/`](ios/README.md) | Caregiver app (SwiftUI): setup, today's doses, live Squint, routine trends, label scanning, Siri and Shortcuts, home and lock screen widget | Ved | working, demo and live |
| [`home/`](home/README.md) | The voice: offline Piper text-to-speech, cast to a Google Nest, or played on the laptop (e.g. to a Google Home paired over Bluetooth) | Ved | working |
| [`docs/`](docs/) | [API contract](docs/api-contract.md), [Tab5 ↔ Pi link](docs/tab5-pi.md), [routine tracking](docs/decline-tracking.md) | all | |

**The models.** All four run with OpenCV's `cv2.dnn`, so the same code runs on QNX and a laptop:

| Model | Job |
|---|---|
| YuNet | finds faces |
| SFace | tells enrolled people apart (each person against their own ~40 photos) |
| NanoDet | finds bottle-shaped things |
| bottle embedder (MobileNetV3, trained in v1) | tells enrolled bottles apart |

Anything that doesn't match well enough is "unknown", never a guess.

**Routine tracking is statistics, not a trained model.** Each person is compared with their own
usual, per signal, in `buddy/buddy/insights.py`. See [docs/decline-tracking.md](docs/decline-tracking.md).

## First time on a new laptop

```bash
git clone https://github.com/dinud2/hackwestern.git && cd hackwestern
```

| Part | Setup |
|---|---|
| Backend (to run or enrol on a laptop) | `cd buddy && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`. This pins **OpenCV 4**: OpenCV 5 crashes in face alignment. |
| Faces and bottles | Not in git (personal data). Enrol them with `buddy/tools/enroll_face.py` and `enroll_bottle.py`, or copy `buddy/data/` from the Pi. |
| Voice | `cd home`, make a venv, `pip install -r requirements.txt`, then `./get_voices.sh` (the voices are not in git). |
| Tab5 | Copy `tab5-face/secrets.example.h` to `secrets.h`, fill in the Wi-Fi and the Pi's address, and flash it. |
| iOS | Open `ios/Squint.xcodeproj`. For your own iPhone, set your team on both targets (Squint and SquintWidget) and **don't commit it**. |
| SSH to the Pi | `ssh-copy-id qnxuser@<pi>` once. If your key has a passphrase, `ssh-add --apple-use-keychain ~/.ssh/id_ed25519` so you're not asked every time. |

## Run the demo

Put everything on **one network**. A phone hotspot works: the phone, the Pi, the Tab5 and the
laptop all join it.

**0. Find the addresses.** The hotspot can hand out different ones each time (the Pi has been
`.9` and `.3`).

```bash
ipconfig getifaddr en0                                                  # the laptop
for i in $(seq 2 14); do nc -z -G1 172.20.10.$i 22 && echo "Pi? 172.20.10.$i"; done   # SSH open = the Pi
```

**1. Voice (laptop).** Leave it running.

```bash
cd home && .venv/bin/python server.py --local    # --local: laptop audio, e.g. a Google Home over Bluetooth
```

Without `--local`, it casts to a Nest on the same Wi-Fi.

**2. Pi.** If `buddy/` changed, copy it over first, then start the camera and the service with the
laptop's address for the voice:

```bash
scp -r buddy/buddy qnxuser@<pi>:/data/home/qnxuser/buddy/
ssh qnxuser@<pi> 'SQUINT_ARGS="--announce http://<laptop>:8765/announce" ./squint_start.sh'
```

Check it:
- `http://<pi>:8080`: the live camera.
- `http://<pi>:8081/cams`: the same, with the box to hold a bottle in.
- `http://<pi>:8081/state`: who it sees right now.
- `http://<pi>:8081/today`: today's doses.

**3. Tab5.** `secrets.h` must have the Pi's address from step 0. If the address changed, reflash.
It then polls the Pi on its own.

**4. App.** Settings, turn off *Use demo data*, then set:
- Station: `http://<pi>:8081`
- Speaker: `http://<laptop>:8765`

*Test voice* should speak on the Google Home. The widget and Siri follow the app's settings.

**5. Walk up to the camera.** Squint's face changes on the Tab5 and in the app, and the Google Home
greets you by name.

For the Trends tab to have something to show on a fresh station, stop the service and seed a few
weeks of made-up history first: `cd buddy && python3 tools/seed_history.py` (`--clear` removes it).

## What's next

- **Physical setup docs:** where the camera and the Tab5 sit, now that the setup has changed.
- **Fixed addresses:** give the Pi a fixed address (or let the Tab5 and app find it), so a new
  hotspot session doesn't mean reflashing the Tab5.
- **Model tweaks for routine tracking** (the order and why are in
  [docs/decline-tracking.md](docs/decline-tracking.md#do-the-models-need-to-change)):
  1. Give the bottle to the nearest face in the same frame, so two people at the counter don't
     get mixed up. This is geometry only, no retraining.
  2. Real hand-to-mouth detection, so "taken" doesn't rely on the Tab5 answer (MoveNet, from
     `archive/old-idea`).
  3. Log a bottle put back with nothing confirmed as an unsure moment.
- **Stress testing:** more training for the face and bottle models (and the `_other` class), check
  bottle detection on real C270 frames, and long runs on the Tab5.
- **Backend:** push events to the app instead of polling, and upload enrolment photos from the
  app so a laptop isn't needed.
- **Live mode away from home:** a tunnel (e.g. `cloudflared`) from the Pi, so the app works off
  the home network.
- **HealthKit:** only useful from an app on the elder's own phone. Medication logs and walking
  steadiness are read-only for other apps.

## History

Earlier ideas are kept as tags, not branches:
- `archive/old-idea` has Squint v1, which anticipated the pill reaching the mouth from body pose.

```bash
git checkout archive/old-idea
```
