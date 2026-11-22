#!/bin/sh
# Laptop side of the demo: voice (laptop speaker), speaking the Pi's announcements, and the live
# camera view. Ctrl-C (or q in the camera window) stops all three.
#   ./tools/laptop_start.sh            # Pi at 172.20.10.9
#   PI=172.20.10.9 ./tools/laptop_start.sh --fullscreen
PI=${PI:-172.20.10.9}
HERE=$(cd "$(dirname "$0")/.." && pwd)                 # buddy/
REPO=$(dirname "$HERE")
VENV=${VENV:-$HERE/.venv/bin/python}
[ -x "$VENV" ] || VENV=/home/dinu/Documents/hackwestern/buddy/.venv/bin/python
HOMEDIR=${HOMEDIR:-$REPO/home}                           # Ved's voice service (needs home/voices)
[ -d "$HOMEDIR/voices" ] || HOMEDIR=/home/dinu/Documents/hackwestern/home
HOMEPY=$HOMEDIR/.venv/bin/python
mkdir -p /tmp/squint
(cd "$HOMEDIR" && exec "$HOMEPY" -u server.py --local) > /tmp/squint/voice.log 2>&1 &
VOICE=$!
# The Pi re-sends its last line ("Hi Dinu.") on connect: wait for the voice service so it isn't lost.
for i in $(seq 60); do grep -q listening /tmp/squint/voice.log 2>/dev/null && break; sleep 0.5; done
"$VENV" -u "$HERE/tools/speak_events.py" --pi "$PI" > /tmp/squint/speak.log 2>&1 &
SPEAK=$!
trap 'kill $VOICE $SPEAK 2>/dev/null' EXIT INT TERM
echo "voice + announcements running (logs in /tmp/squint); opening the camera view (q quits)"
QT_QPA_PLATFORM=${QT_QPA_PLATFORM:-xcb} "$VENV" "$HERE/tools/squint_view.py" --pi "$PI" "$@"
