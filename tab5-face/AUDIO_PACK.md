# Audio pack contract (for the Gemini voice clips)

The face plays one WAV file per clip.
If a clip is missing, the face still works, without sound.

## File format

- WAV, 16-bit PCM, **mono**.
- 24 kHz is fine. Gemini TTS returns raw 24 kHz 16-bit mono PCM, so **add a WAV header** before you save the file.
- Keep each clip under 6 s. Shorter is better.
- File name: `<clipId>.wav`. Use lowercase letters, digits and `_` only.
- Put the files in `tab5-face/data/voice/`. They are uploaded to LittleFS as `/voice/<clipId>.wav`.

## Voice style

- Use a warm, calm, **lower-pitched** voice. Older adults lose high frequencies first.
- Speak slowly. Leave a short pause between sentences.
- Say the person's name first. Then say the action.
- STOP is the only urgent clip. Make it firm, not scary.
- Example style prompt: *"Say slowly, warmly and clearly, like a kind nurse:"*

## Clips the face asks for

The screen shows only the key words. The voice says the full sentence.

### Default clips (used when no clip is named)

| clipId | Reaction | Words to say |
|---|---|---|
| `greet` | greet | "Hello! It's good to see you." |
| `remind` | remind | "It's time for your pill." |
| `happy` | happy | "Got it. Well done!" |
| `concerned` | concerned | "I don't know this bottle. Please show me the label." |
| `stop` | stop | "Stop. You already took this one today." |
| `wrong` | wrong | "Wait. These are not your pills." |

### Demo clips (Margaret's scripted morning)

| clipId | Reaction | Words to say |
|---|---|---|
| `greet_margaret` | greet | "Good morning, Margaret!" |
| `remind_warfarin` | remind | "Margaret, it's time for your warfarin. One small pink pill." |
| `happy_taken` | happy | "Got it. Well done, Margaret!" |
| `stop_double` | stop | "Stop, Margaret. You already took your warfarin at 8:02." |
| `concerned_unknown` | concerned | "I don't know this bottle. Please show me the label." |
| `wrong_robert` | wrong | "Wait. This is Robert's medicine. Yours is the pink bottle." |

## How the Pi picks a clip

The Pi sends one line over serial. The third part is the clipId:

```text
stop STOP|Taken at 8:02|stop_double
```

`say <clipId>` plays a clip without changing the face.
