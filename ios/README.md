# Squint for iOS (the caregiver app)

The app for the people who worry: an elder's children. They set Squint up once (who takes what,
and when), then see the day at a glance:
- what Squint is showing at home right now
- every dose on a timeline
- only the things that need them
- whether their routine is changing, week against their own usual (the **Trends** tab)
- a **notification** when a dose is taken, missed, or Squint steps in

And without opening the app at all:
- **Siri / Spotlight / Shortcuts:** *"Has Dinu taken his pills in Squint?"* answers in a sentence
  (taken, what's next, anything missed) with a small card. *"How is everyone doing in Squint?"* does
  everyone at once. Spotlight lists one shortcut per person.
- **Widget:** home screen (small, medium) and lock screen (round gauge, a line per person, inline).
  Squint's face in the current mood, pills per person, and the one thing that needs you.

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
  6. Set the team on the **SquintWidget** target too. Both targets share the App Group
     `group.com.hackwestern.squint`; if your team can't create it, the app still works, but the
     widget and Siri can't see the app's settings and fall back to demo data.

## Demo mode and live mode

| | Demo (default) | Live |
|---|---|---|
| Data | Margaret and Robert, made up in `MockAPI` | the station's `/people`, `/medications`, `/today`, `/insights` |
| Trends | 30 seeded days: Margaret's mornings slip lately, Robert is steady | `/insights`. A new station shows "learning" until it has a week of usual; seed history with `buddy/tools/seed_history.py` |
| Squint card | mood worked out from the doses, plus *Watch Squint's morning* | mirrors the Tab5 by long-polling `/tab5/commands` |
| Switch | Settings → *Use demo data* | turn it off, set the station to `http://<pi>:8081` |

The phone must be on the same network as the Pi. Allow *Local Network* when iOS asks.

To try live mode without the Pi, run the backend on the Mac with no camera (in `buddy/`:
`python3 -m buddy.service --bottle-source ""`), and set the station to `http://localhost:8081` in the simulator. If an older
station has no `/insights`, Today still works and Trends says it couldn't load.

## Notifications

`Notifier.swift` compares each `/today` with the last one it saw and sends one local notification
per change. There is no push server and nothing to set up beyond allowing notifications.

| Change | Notification | Level |
|---|---|---|
| taken | "Dinu took Tylenol": "At 8:02 AM. Squint saw it." | passive (list only, no sound); Settings → *Every dose taken* turns it off |
| missed | "Dinu missed Tylenol" + Squint's reason | time sensitive, sound |
| flagged | "Squint stepped in for Dinu" + Squint's reason | time sensitive, sound |

- The first look each day only records what's there, so opening the app doesn't replay the morning.
- **Open app:** every new Tab5 line and every 30 s. **Closed app:** a background app refresh
  (`com.hackwestern.squint.refresh`), whenever iOS allows, ~15 min at best. To test: Xcode → Debug →
  *Simulate Background Fetch*.
- **Demo:** *Play* on Today sends the two Maya would get ("took Warfarin", then "stepped in").
- The station's `--demo` mode logs no doses, so live notifications need the station started without
  it (`SQUINT_DEMO= ./squint_start.sh`).

## Siri and the widget

Both are built on `Glance` (`Shared/Glance.swift`): today boiled down to, per person, taken/total,
what's due now, what's next and what went wrong, plus one mood. Siri says it in words, the widget
draws it, so they always agree.

- The widget asks the station itself (it runs without the app), every 15 minutes or right when the
  next dose is due. When the app sees something change, it tells the widget to redraw at once.
- Settings live in the App Group, not plain `UserDefaults`, so the widget and Siri read the same
  demo/live switch and station address as the app.
- Siri learns the people's names from `PersonQuery`; the app refreshes them when someone is added.

## Files

```
Shared/                  used by the app and the widget
  Models.swift, API.swift, Insights.swift
  Settings.swift         settings in the App Group (demo/live, station, speaker)
  Glance.swift           today in one look, and how Siri says it
  Theme.swift            Squint's colours and fonts
SquintWidget/
  SquintWidget.swift     the widget: timeline, every size, Squint's eyes drawn in shapes
tools/make-icon.swift    draws the app icon (swift tools/make-icon.swift, from ios/)
Squint/
  SquintApp.swift        app entry, the floating tab bar, starts live following
  AppStore.swift         all state (@Observable): data, settings, Squint's state, demo playback
  Notifier.swift         dose notifications: diffs /today, sends taken / missed / flagged
  Intents.swift          Siri and Shortcuts: check one person, or everyone; the answer card
  LabelParser.swift      reads a pharmacy label photo (Vision OCR) into a medication
  Views/
    SquintFace.swift     Squint's 8 moods drawn live, plus the card and badge, and a parser for
                         Tab5 command lines
    Components.swift     the design system: the pill glyph, buttons, cards (colours in Shared/Theme)
    TodayView.swift      greeting, live Squint, day strip, alerts, a routine nudge, per-person doses
    TrendsView.swift     each person's steadiness ring, how-late chart against usual, and signals
    MedicationsView.swift, AddMedicationView.swift   list and add/edit (scan a label)
    OnboardingView.swift, SettingsView.swift
```

**Design rule:** the only colours are Squint's own: sage = taken, amber = check, red = STOP. If you add
a screen, build it from `Theme`, `PillGlyph`, `paperCard()` and `InkButtonStyle`.
