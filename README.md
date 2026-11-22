# Squint

Squint is a small face that sits on the kitchen counter next to the pill bottles. It knows who
walked up, which bottle they picked up, and whether their hand went to their mouth. It greets
them, reminds them what to take, says **STOP** before a second dose of a dangerous drug, and
tells their family when something needs attention.

We built it at Hack Western 13 for older couples who keep their medicine together, and for the
son or daughter who worries about them from an hour away.

## Why

About one Canadian senior in every two hundred is hospitalized each year because of a reaction
to their own medicine, and blood thinners are the most common cause (CIHI). The mistakes behind
those numbers are usually simple. Someone takes their blood thinner at eight, forgets, and takes
it again at nine. Or they pick up their partner's bottle, which has the same red label and sits on
the same counter.

Pill organisers and smart dispensers ask people to change a routine they've had for forty years.
Squint doesn't. It watches the bottles they already use.

## What it does

At the counter:

- **Recognises who walked up** and greets them by name on a Google Home, then tells them what
  they take today.
- **Names the bottle they're holding** and checks that it's theirs, that it's due, and that they
  haven't already taken it today.
- **Watches for the hand going to the mouth** and logs the dose by itself. If it isn't sure, it
  asks "Did you take it?" on the screen.
- **Stops a double dose** of a high-risk medicine with red eyes and a spoken warning: "Stop, Dinu.
  You already took your Tylenol at 8:02."
- **Warns about mix-ups** when someone picks up their partner's medicine.
- **Stays quiet with strangers.** Anyone it doesn't know is "unknown", and it won't guess.

For the family, on iPhone:

- Today's doses on a timeline, and a live copy of Squint's face.
- A notification when a dose is taken (quiet) or missed or stopped (with sound).
- Siri ("Has Dinu taken his pills in Squint?") and a home and lock screen widget.
- **Trends:** each person compared with their own usual over the last week: doses drifting later,
  more double-dose attempts, more mix-ups. It suggests a chat with their doctor when something
  changes. It doesn't diagnose anything.

## How it works

```
 THE COUNTER                                                     THE FAMILY
 ┌──────────────────────────────────────────────────────────┐
 │  USB webcam ──▶ Raspberry Pi 5 running QNX 8             │
 │                 ├─ camstream (C)        camera, :8080    │
 │                 └─ Squint service (Python)  API, :8081 ──┼──▶ iPhone app, widget, Siri,
 │                      faces · bottles · hand to mouth     │    notifications
 │                      decisions · dose log · trends       │
 │                     │                    │               │
 │                     ▼                    ▼               │
 │        Tab5 screen (the face)    laptop voice ──▶ Google Home
 └──────────────────────────────────────────────────────────┘
```

One camera answers three questions, and every model runs on the Pi. Nothing goes to the cloud.

| Question | How |
|---|---|
| Who is here? | YuNet finds faces; SFace compares each face with that person's ~40 enrolment photos |
| Which bottle? | The label colour finds candidates; a MobileNetV3 we trained on label crops confirms or rejects them |
| Did they take it? | A MediaPipe palm detector watches the area around the mouth |

The rule behind all three is that Squint would rather say "not sure" than be wrong. A face has to
clearly beat everyone else to be named, and colour and classifier have to agree on a bottle. On
recording sessions we held out of training, it named **zero wrong bottles**.

Routine tracking is plain statistics, not a model: each person against their own last four weeks.

More detail: [how it works](docs/architecture.md) · [the models](docs/models.md) ·
[the API](docs/api-contract.md) · [routine tracking](docs/decline-tracking.md)

## Built on QNX

The whole station runs on a Raspberry Pi 5 under QNX 8, the real-time OS used in cars and medical
devices.

- **The camera** is our own C program, `pi/camstream.c`, written against QNX's native camera API.
  The camera headers weren't on the device, so we declared the functions ourselves and worked out
  the frame layout from a live frame with `pi/probe.c`.
- **It runs at real-time priority** (`on -p 20`), so the camera keeps up however hard the
  recognition is working. Slow models skip frames; capture never stalls.
- **The camera driver is its own process**, QNX's sensor service. We pinned it to our webcam's USB
  ID, and `pi/squint_start.sh` restarts it and waits for the device if it ever drops.
- **No PyTorch on the device.** Every model is ONNX, run through OpenCV, and the HTTP server is
  Python's standard library, so it all works on QNX.

## The repo

| Folder | What's in it |
|---|---|
| [`buddy/`](buddy/README.md) | The Squint service on the Pi: recognition, decisions, the dose log, routine tracking, the API, plus tools for enrolment, training and diagnostics |
| [`pi/`](pi/README.md) | The QNX camera stream and the start script |
| [`tab5-face/`](tab5-face/README.md) | Firmware for the M5Stack Tab5: Squint's eyes, its words, and the Yes/No buttons |
| [`ios/`](ios/README.md) | The family's iPhone app, widget and Siri shortcuts (SwiftUI) |
| [`home/`](home/README.md) | Squint's voice: offline text-to-speech played on a Google Home |
| [`docs/`](docs/) | Architecture, models, API, routine tracking, troubleshooting, and the [live demo script](docs/live-demo.md) |

## Running it

You need the Pi with QNX and the webcam, the Tab5, a laptop, and an iPhone, all on one network.
A phone hotspot works.

```bash
git clone https://github.com/dinud2/hackwestern.git && cd hackwestern

# laptop: the voice
cd home && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && ./get_voices.sh
.venv/bin/python server.py --local

# laptop: copy the service to the Pi, then start the camera and the service there
scp -r buddy/buddy qnxuser@<pi>:/data/home/qnxuser/buddy/
ssh qnxuser@<pi> 'SQUINT_DEMO= SQUINT_ARGS="--announce http://<laptop>:8765/announce" ./squint_start.sh'
```

Then:

- **Tab5:** copy `tab5-face/secrets.example.h` to `secrets.h`, add the Wi-Fi and the Pi's address,
  and flash it.
- **iPhone:** open `ios/Squint.xcodeproj` and run it. In Settings, turn off *Use demo data* and
  set the station to `http://<pi>:8081`.
- **Check everything:** `python3 buddy/tools/doctor.py` finds the Pi and lists anything wrong.
- **Watch what Squint sees:** `cd buddy && .venv/bin/python tools/squint_view.py --pi <pi>` shows
  the camera with the face scores, bottle verdicts and hand-to-mouth readings beside it.

Faces and bottle photos are personal, so they aren't in git. Enrol people with
`buddy/tools/enroll_face.py`. The app runs without any hardware in demo mode, with made-up data.

Leaving out `SQUINT_DEMO=` starts the station in demo mode, which checks whose bottle it is at any
time of day but logs nothing. That's handy on a stage; it means no doses, STOPs or notifications.

## What's next

- **Two people at the counter.** Give the bottle to the nearest hand, not just to whoever is
  there. It's geometry on what we already detect.
- **Any medicine.** Match the bottle to the pharmacy label the app already reads, instead of
  training on photos of each one.
- **Instant notifications** to a closed app, through Apple push and a small relay.
- **Use it away from home,** with a secure tunnel from the Pi.
- **Set up from the phone:** enrol faces from the app, and let the Tab5 find the Pi on its own.
- **More QNX:** move recognition into separate processes with their own priorities, talking over
  QNX message passing.

## Limits

- It sees the hand reach the mouth, not the pill being swallowed. That's why it asks when it isn't
  sure.
- Bottles are recognised by their labels, so each new medicine needs photos for now.
- With the app closed, notifications arrive at iOS's next background check, not instantly.

## Team

Ved, Kathy, Dinu and Kamal, at Hack Western 13, November 2026.

An earlier version that tried to predict the pill reaching the mouth from body pose is kept on the
`archive/old-idea` tag.
