# Squint for iOS (the caregiver app)

The app for the people who worry: an elder's children. They set Squint up once (who takes what,
and when), then see the day at a glance:
- what Squint is showing at home right now
- every dose on a timeline
- only the things that need them

SwiftUI, iOS 17+, no dependencies.

## Build and run

- **Simulator:** open `Squint.xcodeproj` and press Run.
- **Your iPhone (free Apple ID):**
  1. In Xcode → Settings → Accounts, add your Apple ID.
  2. On the phone, turn on **Developer Mode** (Settings → Privacy & Security).
  3. Plug the phone in. Under target **Squint** → **Signing & Capabilities**, tick *Automatically
     manage signing* and choose your *Personal Team*. Then press Run.
  4. The first time, trust yourself on the phone: Settings → General → VPN & Device Management.
     This needs internet.
  5. Free installs expire after 7 days; reinstall when that happens. **Don't commit your
     `DEVELOPMENT_TEAM`.** It would make everyone else sign with your account.

## Demo mode and live mode

| | Demo (default) | Live |
|---|---|---|
| Data | Margaret and Robert, made up in `MockAPI` | the station's `/people`, `/medications`, `/today` |
| Squint card | mood worked out from the doses, plus *Watch Squint's morning* | mirrors the Tab5 by long-polling `/tab5/commands` |
| Switch | Settings → *Use demo data* | turn it off, set the station to `http://<pi>:8081` |

The phone must be on the same network as the Pi. Allow *Local Network* when iOS asks.

## Files

```
Squint/
  SquintApp.swift        app entry, the floating tab bar, starts live following
  AppStore.swift         all state (@Observable): data, settings, Squint's state, demo playback
  API.swift              SquintAPI protocol, MockAPI (demo), LiveAPI (station), HomeSpeaker (voice)
  Models.swift           Person, Medication, Dose, ClockTime: same JSON as docs/api-contract.md
  LabelParser.swift      reads a pharmacy label photo (Vision OCR) into a medication
  Views/
    SquintFace.swift     Squint's 8 moods drawn live, plus the card and badge, and a parser for
                         Tab5 command lines
    Components.swift     the design system: paper/ink colours, the pill glyph, buttons, cards
    TodayView.swift      greeting, live Squint, day strip, alerts, per-person doses
    MedicationsView.swift, AddMedicationView.swift   list and add/edit (scan a label)
    OnboardingView.swift, SettingsView.swift
```

**Design rule:** the only colours are Squint's own: sage = taken, amber = check, red = STOP. If you add
a screen, build it from `Theme`, `PillGlyph`, `paperCard()` and `InkButtonStyle`.
