# Squint API contract (iOS app ↔ backend)

The iOS app is built against this. Until the backend exists, the app runs on a mock with the same
shapes (Settings → "Use demo data"). Change this file first if anything here changes.

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

## Endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/people` | | `[Person]` |
| POST | `/people` | `Person` (no `id`) | `Person` with its new `id` |
| GET | `/medications` | | `[Medication]` |
| POST | `/medications` | `Medication` (no `id`) | `Medication` with its new `id` |
| PUT | `/medications/{id}` | `Medication` | `Medication` |
| DELETE | `/medications/{id}` | | `204` |
| GET | `/today` | | `[Dose]`, every scheduled dose today, oldest first |

Errors: a non-2xx status with `{ "error": "human readable message" }`.

Photos (elder faces for face recognition, bottle photos for pill detection) are not in v1: the app
keeps them on the phone for now. Next step is `POST /people/{id}/photo` and
`POST /medications/{id}/photos` as `multipart/form-data`.

## Other services the app talks to

- **Home speaker** (`home/server.py`, port 8765): `POST /announce {"text": "..."}`, which says it on the Google Nest.
