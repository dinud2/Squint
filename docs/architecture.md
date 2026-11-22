# How Squint works

One page on how the parts fit, what happens in one dose, and why it's built this way. The parts:
- [models.md](models.md): the models.
- [api-contract.md](api-contract.md): the endpoints.
- [decline-tracking.md](decline-tracking.md): routine tracking.

## The parts

```
                 THE COUNTER (the elder's kitchen)                         ANYWHERE (the caregiver)
 ┌──────────────────────────────────────────────────────────────┐
 │  Logitech C270 ──USB──▶ Raspberry Pi 5, QNX 8                 │
 │                         ├─ pi/camstream.c   MJPEG :8080       │
 │                         └─ buddy/ service   HTTP  :8081 ──────┼──▶ ios/ Squint app
 │                              │ face loop    (YuNet, SFace,    │       Today · Trends · Settings
 │                              │              palm detector)    │       widget · Siri · notifications
 │                              │ bottle loop  (colour +         │
 │                              │              label classifier) │
 │                              │ coordinator → store, journal   │
 │                              │                                │
 │           GET /tab5/commands │ POST /announce                 │
 │                    ▼         ▼                                │
 │  M5Stack Tab5 face      home/server.py :8765 (laptop)         │
 │  tab5-face/ (Arduino)   Piper TTS → Google Home / Nest        │
 └──────────────────────────────────────────────────────────────┘
```

| Part | Hardware | Language | Job |
|---|---|---|---|
| `pi/camstream.c` | Pi 5 + C270 | C (QNX camera API, libturbojpeg) | the camera as MJPEG; keeps only the newest frame |
| `buddy/` | Pi 5 (QNX) | Python, OpenCV, NumPy, stdlib HTTP | sees, decides, remembers, serves |
| `tab5-face/` | M5Stack Tab5 (ESP32-P4, 720×1280) | Arduino C++ | Squint's eyes and big words; Yes/No for "Did you take it?" |
| `home/` | laptop | Python, Piper TTS, pychromecast | Squint's voice, on a Google Home |
| `ios/` | iPhone | SwiftUI, WidgetKit, App Intents | the caregiver's view |

Everything is plain HTTP + JSON on one local network (a phone hotspot at the demo). No cloud.

## Inside the Pi: three threads and a coordinator

`python3 -m buddy.service` starts:

1. **Face loop** (`service.face_loop`), on every frame it can get:
   - YuNet + SFace give *who* (`faces.py`). Only faces ≥ 100 px wide count as "at the counter".
   - `presence.py` smooths that into `people_present` events: arrive after 2 frames, leave after 3 s.
   - While a dose waits for an answer, the **hand-to-mouth** detector (`intake.py`) runs on the same
     frames.
2. **Bottle loop** (`service.bottle_loop`), at 4 frames/s: colour finder + label classifier
   (`colors.py`) give `bottle_shown`.
3. **HTTP server** (`api.py`), one thread per request: the app, the Tab5, `/events`, `/health`.

All events go through the **Hub** (`api.py`) to the **Coordinator** (`coordinator.py`). The
Coordinator is the only place that decides anything. It:
- pushes a line onto the **Tab5 queue** (numbered, so a client never misses or repeats one)
- POSTs a sentence to the **voice**
- writes the **dose log** (`store.py`, `data/store.json`) and the **journal** (`journal.py`,
  `data/journal.jsonl`)

`diag.py` watches all of it for `GET /health` and `tools/doctor.py`.

## One dose, end to end

Dinu, with Tylenol due at 8:00 (marked high risk). The sentences are the ones in `coordinator.py`.

| t | What happens | Who decides | Seen / heard |
|---|---|---|---|
| 0.0 s | Dinu walks up; YuNet finds a face ≥ 100 px, SFace matches it to his ~40 photos | `faces.py` | |
| 0.2 s | 2 frames in a row → `people_present [dinu]` | `presence.py` | |
| | Coordinator: he has Tylenol due | `coordinator.on_people` | Tab5 `presence Dinu`, `remind Hi Dinu!\|Tylenol`; Nest: *"Hi Dinu, today you take Tylenol."* |
| ~3 s | He holds the bottle up: a red patch with white around it; the classifier says `tylenol` ≥ 0.70, clearly ahead of `vitamind` | `colors.py` | |
| | His medicine, due, not taken → a **pending dose** | `coordinator.on_bottle` | Tab5 `ask Tylenol\|Did you take it?` (Yes / No) |
| ~5 s | His hand comes up to his mouth: 2 palm frames near the mouth → confidence 0.95 | `intake.py` | |
| ~5 s | ≥ 0.75 | `coordinator.on_intake` | Tab5 `taken Tylenol\|I saw you take it!`, Yes ticks itself |
| ~7 s | 2 s later, no "No" tapped → logged `taken`, `how: auto` | `coordinator.confirm` | Tab5 `happy Well done!` (gold star); Nest: *"Well done, Dinu."* |
| ≤ 30 s | The app's next refresh sees `taken` | `Notifier.swift` | caregiver's phone: *"Dinu took Tylenol"* |

**The variations:**

| Situation | Tab5 | Nest says | Logged |
|---|---|---|---|
| Kathy (alone) holds Dinu's Tylenol | `wrong Dinu's pills` (amber) | *"Careful Kathy, that's Dinu's Tylenol."* | `wrong_bottle` |
| Dinu holds his Tylenol again, same day | `stop Already taken\|Tylenol at 8:02` (red) | *"Stop, Dinu. You already took your Tylenol at 8:02."* | `double_dose`; caregiver gets *"Squint stepped in"* |
| Too early (doses open 1 h before) | `concerned Not yet` | *"Not yet, Dinu. Your next Tylenol is at 20:00."* | `not_yet` |
| A known bottle nobody takes (Omega 3-6-9) | `concerned Not registered` | *"That's Omega 3-6-9. That medication isn't registered in the app."* | |
| A stranger holds a bottle | `concerned Who's there?` | *"I don't recognise you, so I can't check whose Tylenol this is."* | |
| No face seen at all | `concerned Who's there?` | *"Please look at the camera, then show me the Tylenol again."* | |
| Colour and classifier disagree | nothing named | nothing: it never guesses | |
| No hand-to-mouth, no tap in 60 s | stays on the question | | `unsure` |
| Nobody comes in the window | | | dose `missed`; caregiver gets *"Dinu missed Tylenol"* |
| Everyone leaves | `away`, sleeps after 10 s | | `leave` |

"Wrong" means the owner **isn't** among the people at the counter. If Dinu and Kathy stand there
together and Kathy holds Dinu's bottle, it counts as Dinu's (one camera can't yet tell whose hand
it is; that's on the roadmap).

**Demo mode** (`--demo`, on by default in `squint_start.sh`) drops the clock: own bottle →
*"Yes Dinu, that's your Tylenol"* + the Yes/No question; partner's bottle → the warning. No dose
windows, no "not yet", no STOP, and **nothing is written to the dose log**, so the app's Today
doesn't change and no notification is sent. To show those live, start without it:
`SQUINT_DEMO= ./squint_start.sh`.

## Over weeks: routine tracking

The journal records every moment, not only doses: arrived, left, mix-up, double-dose attempt,
unsure, visit with nothing taken. `insights.py` compares each person's last 7 days with their own
previous 28, on 8 signals, and the app's Trends tab shows the result as plain sentences. It's
statistics, so every number traces back to journal lines, and it never compares one person with
another. Thresholds and reasons: [decline-tracking.md](decline-tracking.md).

## How the caregiver hears about it

| Channel | How | How fast |
|---|---|---|
| App, open | long-poll `GET /tab5/commands` (live face mirror) + `/today` every 30 s | ~instant |
| Notifications | the app diffs `/today`; local `UNUserNotificationCenter` | instant while open; app closed: next background refresh (iOS decides, ~15 min at best) |
| Widget | WidgetKit timeline, reloaded when the app sees a change | minutes |
| Siri / Shortcuts | App Intents read `/today` on demand | on ask |

**Why there's no push server:** real push to a closed app needs APNs (a paid developer account, a
key, and something on the internet to send it). The Pi is on a home network with no public
address. The next step is a small relay, or `cloudflared` from the Pi.

## Design decisions (and why)

- **One camera for faces and bottles.** The C270 sits tilted up at the person: faces at
  head height, bottles held at chest height, all in one 960×544 stream. It's cheaper and simpler,
  and the "who is holding it" question is answered in the same frame.
- **Everything local, on QNX.** Faces and medicines are health data and never leave the house.
  QNX is a real-time OS used in cars and medical devices, which fits a safety device. The cost:
  no PyTorch or pip wheels for most things, so every model runs through OpenCV's `cv2.dnn` and the
  HTTP server is the standard library's.
- **Open-set everywhere.** "Unknown" and "not sure" are first-class answers. The thresholds are
  tuned so the measured wrong-bottle rate on held-out sessions is zero, accepting more "not sure".
- **Colour first, classifier second.** Label colour is robust and explainable. The classifier
  only vetoes, splits a colour family, or raises "not sure", and never overrules colour.
- **Hand-to-mouth asks when unsure.** A camera can't see a pill being swallowed. At ≥ 0.75 Squint
  confirms by itself. Below that, the person taps Yes or No. Either way, it's logged how it was
  confirmed (`how`).
- **The coordinator owns every decision.** Models only report what they see. One file holds the
  rules (greet, remind, wrong, STOP, auto-confirm), so the behaviour is easy to read and test.
- **Statistics, not a model, for routine change.** With weeks of data per person, nothing can be
  trained honestly. Comparing a person with their own baseline is explainable and can't stereotype.
- **Calm by default.** The Tab5 sleeps unless someone is there, greetings come at most once per
  2 min, a dose taken is a quiet notification, and only missed doses and STOPs make a sound.

## Ports and files at a glance

| Port | Service |
|---|---|
| 8080 | `camstream` on the Pi: `/stream` (MJPEG), `/snapshot.jpg` |
| 8081 | `buddy.service` on the Pi: the API |
| 8765 | `home/server.py` on the laptop: `POST /announce` |

| File (Pi) | What's in it | In git? |
|---|---|---|
| `buddy/models/*.onnx` | the models | yes |
| `buddy/data/faces/<name>.npy` | face embeddings | **no** |
| `buddy/data/store.json` | people, medicines, dose log | **no** |
| `buddy/data/journal.jsonl` | every moment at the counter | **no** |
| `buddy/service.log`, `stream/camstream.log` | logs | no |
