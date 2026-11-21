# Camera and models: why Squint stays quiet, and how to fix it

A handoff for whoever picks up the face and bottle recognition. It covers what we saw, how to
find the cause with the diagnostics now in `main` (PR #12), and where each setting lives.

## What we saw

On the live run on the Pi, Squint looked blank: no greeting, and the Tab5 kept sleeping. Nothing
from outside said why. When a face was fully in view, YuNet found it, so the models weren't
plainly broken. The likely causes:

1. The Tab5 was polling an old Pi address, so it never got the "wake up" command.
2. The C270 was aimed above people's faces, so faces were cut off at the top edge or missed.
3. Faces that weren't enrolled came back as "unknown", and Squint ignores those by design.

None of this has been confirmed on the Pi yet. The diagnostics are what will confirm or rule it out.

## Step 1: get the facts

With the laptop and the Pi on the same hotspot:

```bash
scp -r buddy/buddy qnxuser@<pi>:/data/home/qnxuser/buddy/     # the Pi needs the new diag.py
ssh qnxuser@<pi> 'SQUINT_ARGS="--verbose --announce http://<laptop>:8765/announce" ./squint_start.sh'
python3 buddy/tools/doctor.py                                  # or --pi <pi>
```

Then stand where a person would stand and run `doctor.py` again. Also useful:

- `http://<pi>:8081/health`: the raw report. `faces.last_box` is where the last face sat, as
  fractions `(x, y, w, h)` of the frame. `faces.too_small` and `faces.at_edge` count rejected faces.
- `http://<pi>:8080`: the live picture, to see what the camera actually sees.
- `ssh qnxuser@<pi> tail -f ~/buddy/service.log`: every frame's decision (with `--verbose`).
- `python3 buddy/tools/face_live.py --source http://<pi>:8080/stream`: runs the face models on the
  laptop against the Pi's stream, with boxes and scores drawn on screen.

## Step 2: match the warning to a fix

| `doctor.py` / `/health` says | Cause | Fix |
|---|---|---|
| Face camera has sent no frame | camstream isn't running, or the C270 was replugged | `./squint_start.sh` (it restarts the camera service if the unit is missing) |
| The face is at the edge of the picture | camera aim | tilt the C270 so faces sit in the middle; `last_box` shows how far off it is |
| A face is too small (< 60 px) | person too far away | come closer, or lower `MIN_FACE_PX` |
| No face seen for over 60 s | camera points beside or above people | re-aim it; check `:8080` |
| Someone is in view but not recognised | not enrolled, or enrolment photos don't match the C270's light and angle | re-enrol from the Pi's stream: `enroll_face.py --source http://<pi>:8080/stream` |
| Nobody is enrolled | `data/faces` is empty on the Pi | enrol, then copy `buddy/data/faces` over |
| N face/bottle frames failed; last: ... | an exception in the loop | the error text is in the warning; full trace in `service.log` |
| No bottles enrolled / no `_other` class | bottle gallery missing | `enroll_bottle.py --name <id>` and `--name _other` |
| The Tab5 has never asked for commands | old `SQUINT_PI_HOST` | fix `tab5-face/secrets.h`, reflash (not a model problem) |

If `doctor.py` says no problems but Squint still doesn't greet you, the problem is in the
recognition scores. Watch `service.log` with `--verbose` and look at the scores next to "unknown".

## Where the settings are

| Setting | File | Now | What it does |
|---|---|---|---|
| `MIN_FACE_PX` | `buddy/buddy/faces.py` | 60 | faces smaller than this are dropped |
| `DET_SCORE` | `buddy/buddy/faces.py` | 0.8 | YuNet confidence needed to count as a face |
| `ACCEPT` / `MARGIN` | `buddy/buddy/faces.py` | 0.40 / 0.08 | SFace: best person's score, and how far it must beat the next (model authors' threshold is 0.363) |
| `--det-scale` | `buddy/buddy/service.py` | 0.5 | faces are found on a half-size frame for speed; try 1.0 if far faces are missed |
| `ACCEPT` / `MARGIN` | `buddy/buddy/bottles.py` | 0.60 / 0.07 | the same for bottles |
| `CENTER` | `buddy/buddy/bottle_service.py` | (0.33, 0.10, 0.67, 0.90) | the box a held-up bottle must fill |
| `FACE_EDGE`, `QUIET_S` | `buddy/buddy/diag.py` | 0.04, 60 s | when the warnings fire (warnings only; recognition doesn't change) |

The laptop must use OpenCV 4 (`buddy/requirements.txt`). OpenCV 5 crashes in face alignment.

## Not done yet

- None of the diagnostics have run on the Pi.
- Bottle detection hasn't been checked on real C270 frames.
- The face and bottle galleries need more photos taken under the Pi camera's own light, plus a
  bigger `_other` class.
