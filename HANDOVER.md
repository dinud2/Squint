# Squint v2 — Handover for the iOS front end

Read this file first. It gives the context from an earlier planning chat.

## 1. The project

- **Event:** Hack Western. Build runs from Sat 1:00am to the Devpost deadline at Sun 9:00am. Code freeze is Sun 2:00am.
- **Product:** Squint v2. It is a medication safety station for older adults who live alone.
  - A Raspberry Pi runs **QNX** (a real-time OS) with a camera, an LED ring, a buzzer, a speaker, an LCD, an NFC reader, a button and an ultrasonic sensor.
  - The station knows which pill bottle is in the hand (camera + AI, or NFC).
  - It detects a pill intake **before the hand reaches the mouth**. If the dose is a double dose, it shouts **STOP**.
  - Each verdict is a light colour (green / amber / red), a voice clip and a reason.
  - A dose ledger stores every dose. It survives a power cut.
- **Story for the demo:** Margaret (the patient) takes warfarin, a high-risk blood thinner. Sarah (her daughter, the caregiver) watches from the iOS app. Robert (Margaret's husband) has his own medications in the same home.

## 2. The team split

| Part | Owns |
|---|---|
| A — App & API (Ved) | Station REST/WebSocket API server on the Pi, live network client, label-scan parser |
| B — QNX platform | Pi bring-up, camera, Grove drivers, processes, heartbeats, alarm, latency + fault tools |
| C — AI | ONNX on QNX, bottle recognition + enrolment, pose, intake-anticipation model |
| D — Decision, hardware & demo | Decision engine, dose ledger + risk policy, voice clips, 3D prints, slides, Devpost |

**My role (the user of this session):** Part D, **plus the iOS front end** (all SwiftUI screens).
Confirm the exact split of iOS work with Ved. The default split: I build the screens and the mock client; Ved builds the API server (A4) and `LiveStationClient` (A6).

## 3. Interfaces that touch the app

Station API (interface 7), served by the Pi, used by the app:

- `GET /status` — light colour, process health, latency (p50 / p99 / worst)
- `GET /today` — today's doses and their status
- `GET /history` — past dose events with verdict + reason
- `GET /medications`, plus create / edit / delete
- `POST /enroll/{medId}` — start bottle enrolment; progress 0–100, then done
- `POST /nfc/{medId}` — link a bottle's NFC tag
- `GET /camera.jpg` — current station camera frame (poll for a preview)
- `WS /events` — live events (dose taken, verdict, STOP, fault, enrolment progress)

Verdict shape (from the decision engine): `{ light: green|amber|red, say: clipId, reason: String, stop: Bool }`.

## 4. Technical setup

- Mac with Xcode 16 or later. SwiftUI. iOS 17 minimum (use `@Observable`).
- A real iPhone is needed for the label scanner (VisionKit live text does not work in the simulator).
- Put the Xcode project in an `ios/` folder in this repository.

## 5. Architecture rules

- **Models:** `Medication`, `DoseEvent`, `StationStatus` (and small enums: `Light`, `DoseStatus`, `Risk`, `EventKind`).
- **`StationClient` protocol:** async functions for each endpoint, plus an `AsyncStream` of live events.
- **`MockStationClient`:** returns fake data and plays **Margaret's scripted morning** as timed events:
  1. 8:02 — warfarin taken → green, "Got it."
  2. 8:40 — second warfarin pick-up → red, "You took this at 8:02."
  3. Hand raised to the mouth → STOP.
  4. Unknown bottle → amber.
  5. Robert's bottle picked up by Margaret → "This is Robert's medication."
- **Screens only talk to the protocol.** Swapping mock → live needs no screen changes.
- **One shared store** (`@Observable`) holds state and listens to the event stream. All screens read from it.
- **Demo mode** (mock client) must always work. It is the fallback if the venue Wi-Fi fails.

## 6. What the user interface must include

User: Sarah, the caregiver. She must see fast: "Is Mom OK? Did she take her pills? Do I need to act?"

1. **Connect screen** — station IP field or "Find station"; "Use demo mode" switch; connection status with reason.
2. **Today tab (main)**
   - Hero card: "Margaret is on track" / "Needs attention" / "Station offline" — colour + icon + text.
   - Dose cards: drug + strength, scheduled time, status (taken with time / due / late / missed / stopped), risk badge.
   - Live event feed, newest first, each with a reason.
   - Health pill: "Station online / offline."
3. **Alerts (everywhere)** — red banner for STOP and "possible double dose"; amber for unknown bottle or fault; local notification when the app is closed; each with time, reason, "View details."
4. **Medications tab** — list (name, strength, times, risk badge, owner); "Add medication" button; detail screen (schedule, max per day, risk, enrolment status, NFC status, Edit, Delete).
5. **Add medication flow** — label scanner (live camera, capture) → review form (name, strength, directions, times, max/day, risk, owner; mark uncertain fields) → Save. Never save without review.
6. **Bottle enrolment flow** — instructions → station camera preview (poll `/camera.jpg`) → progress ring 0–100% → NFC tap step → Done or error with "Try again."
7. **History tab** — 7-day strip (one coloured dot per day); timeline by day (time, drug, verdict, reason); filter by medication.
8. **Station tab** — current light; process list with health dots (camera, vision, decision, alarm, sensors); latency p50 / p99 / worst in ms; last fault + time; "Change station."
9. **States on every screen** — loading; empty ("No medications yet. Scan a label to start."); offline ("Station offline — Margaret is still protected."); error with "Try again."
10. **Accessibility** — Dynamic Type; VoiceOver labels; never colour alone (always icon + word); tap targets at least 44 × 44 pt.

Optional cards, only if the team adds these features:
- Pills left + refill warning (weight sensor under the bottle shelf).
- Weekly trend: "Near-double-doses: 4 this week (1 last week)" (early cognitive-decline signal for the caregiver).
- Lock status: "Warfarin compartment locked until 8:00pm" (servo lock).
- Missed-dose guidance: "Still OK to take until 11:00."
- Drug interaction / timing warnings (for example warfarin + ibuprofen; levothyroxine vs calcium).

## 7. Build order

1. Models + `StationClient` protocol + `MockStationClient` + tab skeleton.
2. Today screen.
3. Alerts (banner + notification).
4. Medications list + detail.
5. History.
6. Station tab + Connect screen.
7. Add-medication flow (label scan + review form).
8. Enrolment flow.
9. Polish: accessibility, empty/error states, app icon.

Today + the STOP alert are the core of the demo. Do them first.

## 8. Key times

- Sat 1:30 — interfaces agreed (models + protocol with Ved).
- Sat 13:00 — Integration 1: app ↔ API on the Pi.
- Sat 18:00 — Integration 2: live client + WebSocket events; STOP alert on the phone.
- Sat 23:00 — full demo run ×2.
- Sun 2:00 — freeze; app footage + Devpost screenshots.

## 9. Instructions for the assistant

- The user prefers ASD-STE100 Simplified Technical English: short sentences, active voice, one instruction per sentence.
- Ask before you create files. The user asked to plan first and build when they say so.
