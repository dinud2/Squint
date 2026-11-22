# The AI in Squint

Squint answers three questions at the counter, all from **one camera** (a Logitech C270 on the Pi):

1. **Who is here?** Face detection + face recognition.
2. **Which medicine is in their hand?** Label colour + a trained label classifier.
3. **Did they take it?** Hand-to-mouth: a palm detector watching the mouth.

Then, over weeks: **is their routine changing?** That part is statistics, not a model.

Every model runs on the Raspberry Pi 5 under QNX with OpenCV's `cv2.dnn`. The same code runs on a
laptop. Nothing is sent to the cloud. The `.onnx` files are in [`buddy/models/`](../buddy/models).

## The rule behind all of them: "unknown", never a guess

Every model is used **open-set**: it can say *I don't know*. A face that doesn't clearly match
one person is `unknown`, and Squint ignores it. A bottle that colour and classifier don't agree on
is `not sure`, and Squint asks to see the label. A green check for the wrong person or the wrong
medicine is the one mistake Squint must never make, so every threshold below leans toward
"unknown". A false "I'm not sure" costs a second; a false "yes, that's yours" could cost a double
dose of a blood thinner.

## At a glance

| Job | Model | Source | Size | Runs | Speed on the Pi |
|---|---|---|---|---|---|
| Find faces | **YuNet** (2023mar) | OpenCV model zoo | 0.2 MB | every face frame, on a half-size frame | real time |
| Who is it | **SFace** (2021dec), 128-d embeddings | OpenCV model zoo | 39 MB | each face found | real time |
| Which bottle | colour finder + **MobileNetV3-Small** label classifier | trained by us (`tools/train_label_classifier.py`) | 6 MB | 4 frames/s | real time |
| Hand at mouth | **MediaPipe palm detector** (2023feb) | OpenCV model zoo | 3.9 MB | only while a dose waits for "Did you take it?" | ~200 ms/frame |
| Routine change | per-person statistics | `buddy/insights.py` | none | on request (`/insights`) | instant |
| *(other bottle modes)* | NanoDet-Plus + MobileNetV3 bottle embedder | zoo + our v1 project | 3.8 + 4.3 MB | `--bottle-mode show/counter` only | |

## 1. Who is here: YuNet + SFace (`buddy/faces.py`, `buddy/presence.py`)

- **YuNet** finds faces and 5 landmarks (eyes, nose, mouth corners). Faces under **60 px** or
  scoring under **0.8** are dropped. Only the **main face** counts: the largest one that's big
  enough (people walking past in the background are never greeted).
- **SFace** turns each aligned face into a 128-number embedding. Each person is enrolled with
  ~40 photos (`tools/enroll_face.py`, guided poses).
- **Matching:** a person's score is the mean of the **5 best** matches against their photos. The
  best person must score **≥ 0.50** (stricter for anyone a visitor resembles) and beat the runner-up
  by **0.08**. Otherwise: `unknown`.
- **Steadiness (`presence.py`):** a person "arrives" after **2 frames in a row** (0.2 s) and
  "leaves" only after **3 s** unseen, so turning your head doesn't trigger a second hello.

## 2. Which medicine: colour + label classifier (`buddy/colors.py`)

The default bottle mode (`--bottle-mode color`). It finds the bottle **anywhere in the picture**,
held at any height, in two stages:

1. **Colour finds candidates.** Saturated, label-sized patches of blue, orange or red that have
   some white (the bottle) around them. Advil is blue, Motrin is orange, and Tylenol and Vitamin D
   are red. The ranges are deliberately loose so dim rooms and far bottles still count. That lets
   skin, shirts and lanyards through too, which is what stage 2 is for.
2. **A classifier judges each candidate.** A **MobileNetV3-Small** (ImageNet weights, fine-tuned
   by us, 224 px input) looks at a tight crop around the patch and outputs `_other`, `advil`,
   `motrin`, `omega369`, `tylenol` or `vitamind`.

**They must agree** (`colors.judge`):

| Classifier says | Result |
|---|---|
| `_other` ≥ 0.50 | not a bottle (skin, a shirt): try the next patch |
| a medicine of **another** colour ≥ 0.35 | **not sure**: Squint asks to see the label |
| same colour family, but < 0.70 | not a bottle |
| two of one colour (Tylenol vs Vitamin D) closer than 0.20 | **not sure** |
| same colour, ≥ 0.70, clear winner | **named** |

The classifier can veto colour, or split one colour into two medicines. It can never overrule
colour with a guess.

**Training** (`tools/train_label_classifier.py`, PyTorch on a laptop, exported to ONNX):
- Photos from many sessions: different people, rooms, light and distances.
- **Background replaced** in ~65 % of samples (GrabCut cut-outs pasted onto other rooms and
  textures), plus jitter, scale down to 20 px, rotation, blur, noise and JPEG artefacts. There is
  **no hue jitter**, because colour is the signal.
- **Negatives:** every colour patch found in photos with no medicine (skin, shirts, lanyards,
  windows, water bottles, faces).
- **Honest evaluation:** whole recording sessions are held out, and the full pipeline (colour plus
  classifier, the code the Pi runs) is scored per photo as right, **wrong bottle**, not sure or
  missed. The number that matters is wrong bottles, and the thresholds were set so held-out photos
  gave **0 wrong bottles**.
- Loose colour recall on the training photos: Advil 83 %, Motrin 94 %, Tylenol 83 %, Vitamin D 81 %.
  The strict ranges managed only 30–55 %.

## 3. Did they take it: hand-to-mouth (`buddy/intake.py`)

It runs only while a dose is waiting for "Did you take it?", so it costs nothing the rest of the
time.

- **Mouth:** the midpoint of YuNet's two mouth-corner landmarks. A hand over the mouth often hides
  the face, so the last mouth position is kept for 2.5 s.
- **Hand:** the **MediaPipe palm detector**, run on a crop 4 face-widths wide around the mouth,
  so the hand is big enough for its 192 px input. On the whole frame a hand was only ~15 px.
- **At mouth:** a palm box within 0.45 face-widths of the mouth point.
- **Decision**, once per waiting dose:
  - **0.95 confidence:** 2+ at-mouth frames with one confident palm (≥ 0.70), or 3+ at-mouth
    frames, or one very confident palm (≥ 0.85).
  - **0.75 confidence:** one frame, or only unsure palms.
- **What happens next:** at ≥ 0.75 the coordinator auto-confirms after 2 s, and the Tab5 shows
  the check ticking itself. Below that, the person taps Yes or No on the Tab5. A "No", or no
  answer within 60 s, is logged as an **unsure moment**.

The Pi checks about 2 frames/s while a dose waits, so a ~1 s hand-to-mouth gives about 2 frames.
The rules were tuned on live tests (see the comments in `intake.py`).

## 4. Is the routine changing: statistics (`buddy/insights.py`)

This is not a trained model, on purpose. Every person is compared **only with themselves**:
**this week** (the last 7 days) against **their usual** (the 28 days before that). It needs
**7 days** of usual before it says anything.

| Signal | Watch at | Talk at |
|---|---|---|
| Doses taken | 10 points lower | 20 lower |
| Timing (median min late) | +20 min | +45 min |
| Regularity (spread of lateness) | +15 min | +30 min |
| Double-dose attempts | 2 a week | 3 a week |
| Mix-ups (partner's bottle) | 2 a week | 3 a week |
| Unsure moments | 2 a week | 4 a week |
| Visits with nothing taken | 2 a week | 3 a week |
| Time to finish | +30 s | +60 s |

**Steadiness** is 100 minus 8 for each `watch` signal and 20 for each `talk`. The app shows plain
sentences, never a score of someone's mind, and always says it can't diagnose anything. The
reasons behind each signal are in [decline-tracking.md](decline-tracking.md).

## 5. Other bottle modes (kept, not used in the demo)

- `--bottle-mode show`: the bottle is held up in a centre box. A **MobileNetV3 bottle embedder**
  (trained for v1, `archive/old-idea`) compares it with enrolled photos (`bottles.py`: accept at
  0.60, beat the runner-up by 0.07). The `_other` class stands for hands, faces and cups.
- `--bottle-mode counter`: **NanoDet-Plus** (COCO "bottle", "cup", "vase") finds bottles standing
  on the counter, and `bottle_tracker.py` reports which one was lifted.

## Known limits

- **Bottles are recognised by their label**, so two brands with the same label colour need the
  classifier to split them, and a new medicine needs photos and retraining (or the `show` mode's
  few-shot enrolment).
- **Faces need enrolment** from the Pi's own camera and light. Photos from a phone match less well.
- **Hand-to-mouth** confirms that a hand reached the mouth, not that a pill was swallowed.
  That's why a low-confidence reading asks the person instead of deciding.
- **The C270 on QNX** gives 960×544 at 20 fps uncompressed (USB 2), which is enough for faces and
  bottles but not much more.
- Debugging a quiet Squint: `buddy/tools/doctor.py` and `GET /health` (see [buddy/README.md](../buddy/README.md)).
