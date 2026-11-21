# Squint home: a calm voice on the Google Nest

Lets the iOS app, the reminder logic and the agent make the house speak:
*"Good morning, Margaret. It's time for your morning pills."*

## Setup (once)

```bash
cd home
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
./get_voices.sh                       # free Piper voices, ~60-120 MB each, into voices/
```

## Run

```bash
.venv/bin/python speak.py --local "Good morning, Margaret"     # hear it on the laptop
.venv/bin/python nest.py                                        # which Google speakers can I see?
.venv/bin/python speak.py "Good morning, Margaret"              # say it on the Nest
.venv/bin/python server.py                                      # the service everything else calls
curl -X POST localhost:8765/announce -d '{"text": "Time for your pills, Margaret."}'
```

Pick the voice with `SQUINT_VOICE=en_GB-jenny_dioco-medium` (or `"voice"` in the request).

## What's actually happening

```
 iOS app / reminder / agent
        │  POST /announce {"text": "..."}
        ▼
 server.py on the laptop
   1. voice.py: Piper turns the text into speech (offline), adds a chime, saves cache/<id>.m4a
   2. nest.py:  finds the Nest on the Wi-Fi and says "play http://<laptop>:8765/audio/<id>.m4a"
        │                                   ▲
        ▼                                   │ 3. the Nest downloads the file from the laptop
 Google Nest speaker  ──────────────────────┘ 4. and plays it
```

- **The voice never comes from Google.** Piper makes the audio on the laptop. The Nest is just a
  speaker that plays a file we point it to, exactly like casting a song from Spotify.
- **Casting** is a public protocol. The Nest advertises itself on the Wi-Fi (mDNS, the same idea as
  AirPlay). `pychromecast` finds it, connects on port 8009 and sends "play this URL".
- **The Nest fetches the audio itself**, from our tiny web server. That's why both devices must be on
  the same network and why macOS asks to "accept incoming connections" (click Allow).
- **Nothing to log in to, no API key, no cost.** We don't use any Google account or API.

## Gotchas

- **Network:** Nest speakers can't join university or enterprise Wi-Fi (eduroam-style username login),
  and venue Wi-Fi often hides devices from each other. Use a phone hotspot: set the Nest up on it in the
  Google Home app, and put the laptop on it too. `nest.py` says "0 speakers" until they share a network.
- **The Nest's microphone is off-limits.** Google doesn't let our code listen through it, so
  conversation happens on the Tab5. The Nest only makes announcements.
- **It interrupts.** An announcement stops whatever the Nest was playing.

## Voices (all free, MIT/CC licensed, from the Piper project)

| Voice | Sounds like |
|---|---|
| `en_US-lessac-medium` (default) | clear, warm US female |
| `en_US-amy-medium` | softer, slower US female |
| `en_US-hfc_female-medium` | gentle US female |
| `en_GB-jenny_dioco-medium` | soft British female |
| `en_GB-cori-high` | calm British female, higher quality |
| `en_US-ryan-high` | calm US male |
