# Routine tracking: noticing cognitive change early

Squint watches the same small routine every day: walk up, pick up the right bottle, take it, leave.
Early cognitive decline often shows up first in routines like this, as more hesitation, more
mix-ups and less regular timing, long before it is obvious in conversation. A check-up once a year
misses that. Squint is there twice a day.

**What it is:**
- trends in someone's own routine, compared with their own normal
- shown to the caregiver as plain sentences, such as *"Margaret has taken her morning pills later
  each week, about 40 min later than her usual."*

**What it is not:** a diagnosis or a score of someone's mind. The app says so, and the advice is
always *"if it keeps up, mention it to their doctor."*

## Signals

Each signal is worked out per person, per day, from what the station already logs.

| Signal | How it's measured | Why it matters |
|---|---|---|
| **Doses taken** | taken ÷ scheduled | missed doses rise as memory for routine fades |
| **Timing** | minutes late against the scheduled time (median per day) | routines drift later and get less regular |
| **Regularity** | spread of that lateness over the week | irregular timing is an early marker, before outright misses |
| **Double-dose attempts** | picks up a medicine already taken today (the STOP) | forgetting having just done something: the clearest memory signal |
| **Mix-ups** | picks up their partner's bottle | confusion between similar objects |
| **Unsure moments** | answers "no" to "Did you take it?", or picks up a bottle and puts it back without taking it | hesitation and doubt |
| **Visits with nothing taken** | came to the counter while a dose was due, left without taking it | "why did I come in here?" |
| **Time to finish** | seconds from arriving to the dose confirmed | tasks slowing down |

## Personal baselines, not population norms

Everybody's routine is different. Squint compares each person **with themselves**:

- **Usual:** days 8–35 ago (up to 4 weeks). It needs at least 7 days before it says anything.
- **This week:** the last 7 days.
- Each signal gets a level:
  - `steady`: within the usual range
  - `watch`: noticeably different from usual
  - `talk`: clearly different for a week. The app suggests a conversation.
- The thresholds use the usual's own spread, plus a floor so tiny changes don't trigger
  (`buddy/buddy/insights.py`, `THRESHOLDS`).
- **Steadiness (0–100)** sums up how far this week is from usual across all signals. 100 means
  the routine is just like normal. It is a summary for the caregiver's glance, not a medical score.

## What the caregiver sees (iOS, Trends tab)

- One card per person:
  - their **steadiness** ring
  - a 30-day **timing** line (how late each day's doses were)
  - this week against usual for each signal
- At most **one sentence that matters**, in plain words, at the top. Nothing alarming when nothing
  changed. Squint only speaks up when there's something to say.
- A line saying it is not a diagnosis.

## Data

- **`buddy/data/journal.jsonl`** (new, git-ignored): one JSON line per thing that happened at the
  counter:
  - `arrive`, `leave` (with how long they stayed)
  - `bottle` (who, which, whose it is)
  - `wrong_bottle`, `double_dose`, `dose` (lateness, seconds since arrival, how it was confirmed),
    `unsure`, `visit_no_dose`

  It is append-only, so a power cut loses at most one line.
- **`store.json`** keeps the dose log it has today (taken per day). Days with no record count as
  missed.
- **API:**
  - `GET /history?days=30` returns every scheduled dose and its status
  - `GET /insights?days=30` returns per person: steadiness, the signals with this week against
    usual, and the daily series. Shapes are in [api-contract.md](api-contract.md).
- **Demo:** `tools/seed_history.py` writes 5 weeks of synthetic history, so the Trends tab has
  something to show at the hackathon. It is clearly synthetic, and `--clear` removes it.

## Do the models need to change?

Mostly no: the signals come from what the coordinator already decides. Three things would make
them better. In order of value:

1. **Who did it, when two people are at the counter.**
   - Today a bottle is matched to "whoever is present". With both partners there, a mix-up and a
     correct pick look the same.
   - Now that faces and bottles come from the **same C270 frame**, we can attribute the bottle to the
     **nearest face** (the bottle's box against each face's box). That's a geometry change in
     `service.py`, no retraining.
   - Until then, events with two people present are logged with `who: [both]` and left out of
     per-person signals.
2. **Actual intake (hand to mouth).**
   - `POST /intake` is still faked. "Picked up and confirmed on the Tab5" is a good proxy, but a
     real intake check separates *took it* from *said they took it*.
   - The pose model from v1 (MoveNet, in the `archive/old-idea` tag) can be brought back for this.
3. **Bottle put back without taking it.**
   - The bottle tracker already knows when a bottle leaves the view.
   - Logging "shown, then gone, with no confirmation within 60 s" as `unsure` needs no new model.

Things to keep training for: face recognition at the counter angle, which keeps attribution
right, and the `_other` class for bottles, so a cup isn't taken for medicine (a false mix-up would
pollute the signals).

## Privacy

Everything stays on the Pi:
- the journal holds names, medicines and times, no images
- face and bottle photos stay in `buddy/data/` (git-ignored) and never leave the house
- the caregiver's phone reads summaries over the home network
