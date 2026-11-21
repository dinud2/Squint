# Tab5 ↔ Pi (Squint)

Everything goes over Wi-Fi to the Pi's service, `http://<pi>:8081` (`buddy/`, run with
`python3 -m buddy.service --announce http://<laptop>:8765/announce`). On the phone hotspot the Pi has
been `172.20.10.9`.

## 1. Face commands: poll the Pi, call `handleCommand()`

The Pi queues lines in the same format the sketch already takes over serial
(`<reaction> [title][|detail][|clipId]`, see `tab5-face/README.md`).

```
GET /tab5/commands?after=<last seq>&wait=20
-> {"seq": 12, "lines": ["presence Dinu", "remind Metformin|Dinu: Metformin and Tylenol"]}
```

- Start with `after=0`. Keep the returned `seq` and send it as `after` next time.
- `wait=20` holds the request open up to 20 s until there is something new, so lines arrive at once
  without polling hard. A plain loop is enough:

```cpp
// in loop(), on its own task or every ~0.5 s
static long seq = 0;
HTTPClient http;
http.begin(String("http://") + PI_HOST + ":8081/tab5/commands?after=" + seq + "&wait=20");
http.setTimeout(25000);
if (http.GET() == 200) {
  JsonDocument doc; deserializeJson(doc, http.getString());
  seq = doc["seq"];
  for (const char* line : doc["lines"].as<JsonArray>()) handleCommand(String(line));
}
http.end();
```

Lines the Pi sends:

| Line | When |
|---|---|
| `presence Dinu` | Someone recognised arrives (wakes the face) |
| `remind Metformin\|Dinu: Metformin and Tylenol` | They have doses to take now |
| `greet Kathy` | They arrived with nothing to take |
| `ask Tylenol\|Did you take it?` | The right bottle was picked up: **Yes / No buttons**, wait for a tap |
| `taken Motrin\|Did you take it?` | Hand-to-mouth was ≥ 90% sure: same screen, **Yes ticks itself after 2 s** (the Pi records it; the Tab5 only sends a No tapped within the 2 s) |
| `happy Well done!\|Metformin` | After a "Yes" |
| `wrong Dinu's pills\|That's Dinu's Tylenol` | Someone picked up another person's medicine |
| `stop Already taken\|Metformin at 10:55` | A high-risk medicine (or one with no dose left today) was already taken |
| `away` | Everyone left |

## 2. "Did you take it?" answer

```
POST /doses/confirm   {"taken": true}        (Yes)      {"taken": false}   (No)
```

No ids needed: the Pi answers the dose that is waiting (`GET /doses/pending` shows it). `med` / `for`
may still be given. After Yes the Pi sends `happy Well done!|<Med>`, after No `idle`. The Tab5 sends
it from a background task (`piLink::confirm()`, `tab5-face/PiLink.h`); the screen is `Ask.h` /
`AskPanel.h`.

## 3. Camera: send frames for bottle recognition

```
POST /tab5/frame          Content-Type: image/jpeg     (JPEG, ~640x480, about 2 per second)
-> {"bottles": [{"name": "tylenol", "score": 0.9, "box": [x1,y1,x2,y2]}],
    "on_counter": ["omega369", "tylenol"], "events": [...]}
```

The Pi works out which bottle was picked up and sends the matching face command above, so the Tab5
does not have to act on this reply.

**Enrolling bottles** (an "add bottle" screen, or a quick setup mode):

```
POST /bottles/enroll?name=tylenol    JPEG with the bottle up close in front of the camera; send 10-20, turning it
POST /bottles/enroll?name=_other     cups, water bottles, hands, the empty counter (so they are never a medicine)
GET  /bottles                        what is enrolled
POST /bottles/reset?name=tylenol     forget one
```

Bottle names must match the medication ids (`GET /medications`).

## 4. Other endpoints

| | |
|---|---|
| `GET /state` | `{"people": ["dinu", "kathy"], ...}` who is at the counter |
| `GET /events` | Server-sent events: `people_present`, `bottle_picked`, `say`, `dose_taken`, ... |
| `GET /people`, `/medications`, `/today` | The iOS app's API (`docs/api-contract.md`) |
