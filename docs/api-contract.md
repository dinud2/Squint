# Squint API contract

The backend (`buddy/`, port **8081**) serves this; the iOS app and the Tab5 are built against it. The
app's demo mode (Settings → "Use demo data") uses a mock with the same shapes. Change this file first
if anything here changes, and keep it in step with `buddy/buddy/api.py`.

All JSON, `Content-Type: application/json`. Times of day are 24-hour `"HH:mm"` strings in the
home's local time. IDs are short lowercase strings (`"margaret"`, `"warfarin"`).

## Objects

```json
Person      { "id": "margaret", "name": "Margaret", "role": "elder", "photo_url": null }
Medication  { "id": "warfarin", "name": "Warfarin", "strength": "5 mg", "for": "margaret",
              "times": ["08:00"], "notes": "Blood thinner", "risk": "high" }
Dose        { "med": "warfarin", "for": "margaret", "due": "08:00",
              "status": "taken", "at": "08:02", "reason": null }
```

| Field | Values |
|---|---|
| `role` | `elder` (takes meds, talks to the avatar), `caregiver` |
| `risk` | `normal`, `high` (high = the avatar never allows a second dose that day) |
| `status` | `due` (not yet, or still inside its window), `taken`, `missed`, `flagged` (taken, but something worth telling the caregiver happened; `reason` explains) |

## App endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/people` | | `[Person]` |
| POST | `/people` | `Person` (no `id`) | `Person` with its new `id` |
| GET | `/medications` | | `[Medication]` |
| POST | `/medications` | `Medication` (no `id`) | `Medication` with its new `id` |
| PUT | `/medications/{id}` | `Medication` | `Medication` |
| DELETE | `/medications/{id}` | | `204` |
| GET | `/today` | | `[Dose]`, every scheduled dose today, oldest first |
| GET | `/history?days=30` | | `[{"date": "2026-11-20", "doses": [Dose]}]`, oldest first, today last (1–120 days). Past days: a dose never logged is `missed` |
| GET | `/insights?days=30` | | `Insights`, below: each person's routine this week against their own usual |

Errors: a non-2xx status with `{ "error": "human readable message" }`.

Photos (elder faces for face recognition, bottle photos for pill detection) are not in v1: the app
keeps them on the phone for now. Next step is `POST /people/{id}/photo` and
`POST /medications/{id}/photos` as `multipart/form-data`.

## Insights (routine tracking)

What the Trends tab shows. How the signals and levels are worked out is in
[decline-tracking.md](decline-tracking.md); the numbers come from `/today`'s dose log plus the
station's journal (`buddy/data/journal.jsonl`). `503` if the station has no journal.

```json
Insights      { "generated": "2026-11-21T15:03:00", "people": [PersonInsight] }
PersonInsight { "person": "dinu", "name": "Dinu", "days_of_data": 35, "learning": false,
                "steadiness": 68, "level": "watch",
                "headline": "Dinu's doses are coming about 40 min later than usual this week.",
                "signals": [Signal], "daily": [DayPoint] }
Signal        { "id": "late", "title": "Timing", "unit": "min late", "recent": 48.0, "usual": 8.0,
                "level": "watch", "worse_by": 40.0, "higher_is_worse": true }
DayPoint      { "date": "2026-11-20", "scheduled": 3, "taken": 3, "late_min": 52.0, "double_dose": 1,
                "wrong_bottle": 0, "unsure": 0, "visit_no_dose": 0, "finish_s": 81.0 }
```

| Field | Values |
|---|---|
| `level` | `steady`, `watch` (worth watching), `talk` (worth a chat), `learning` (under 7 days of usual yet; signals are all `steady`) |
| `steadiness` | 0–100, `null` while learning. 100 minus 8 per `watch` signal and 20 per `talk` |
| `signal.id` | `taken`, `late`, `regularity`, `double_dose`, `wrong_bottle`, `unsure`, `visit_no_dose`, `finish` |
| `signal.unit` | `%`, `min late`, `min spread`, `a week`, `s`; `recent` is the last 7 days, `usual` the 28 before |
| `late_min`, `finish_s` | medians for the day, `null` if nothing was taken |

## Station endpoints

| Method | Path | Body | Returns / does |
|---|---|---|---|
| GET | `/tab5/commands?after=<seq>&wait=20` | | `{"seq": n, "lines": [...]}`: Tab5 face commands (`<reaction> title\|detail\|clip`), long-polled. Used by the Tab5 and the app's live mirror. See [tab5-pi.md](tab5-pi.md) |
| POST | `/tab5/send` | `{"line": "happy Well done!\|Tylenol"}` | pushes a face command by hand (testing) |
| POST | `/doses/confirm` | `{"med", "for", "taken": true}` | the person answered "Did you take it?" on the Tab5 |
| POST | `/intake` | `{"person", "confidence"}` | fake a hand-to-mouth reading (testing, until it is built) |
| GET | `/state` | | who is at the counter now: `{"people": [...], "unknown": n, "since", "seq"}` |
| GET | `/events` | | Server-Sent Events, one `data: {json}` per event (`people_present`, `intake`, ...) |
| GET | `/health` | | `{"ok", "camera_age_s"}` |
| GET | `/cams` | | web page with the camera stream |
| GET | `/bottles` | | enrolled bottles |
| POST | `/bottles/enroll?name=`, `/bottles/reset?name=` | JPEG | enrol or clear a bottle (used by `tools/enroll_bottle.py`) |
| POST | `/tab5/frame` | JPEG | recognise the bottle in one frame |

## Other services the app talks to

- **Voice** (`home/server.py`, port 8765): `POST /announce {"text": "..."}` says it on the Google Nest, or
  on the laptop with `--local`. The backend calls it too (`--announce`).
- **Camera** (`pi/camstream`): one C270 as MJPEG at `:8080/stream`, used for both faces and bottles.
