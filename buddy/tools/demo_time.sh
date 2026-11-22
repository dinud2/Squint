#!/bin/sh
# "Demo time": everything for one live demo run, from the laptop.
#   1. wait for the Pi on the hotspot (it can drop off or reboot)
#   2. start Squint on it if it isn't running (real schedule, not --demo)
#   3. reset today: no doses taken, Tylenol (Dinu) + Vitamin D (Kathy) due in ~5 min
#   4. voice + announcements + the plain camera view (q in the window quits)
#   ./tools/demo_time.sh            # or: make demo (from the repo root)
#   PI=172.20.10.9 ./tools/demo_time.sh --fullscreen
PI=${PI:-172.20.10.9}
HERE=$(cd "$(dirname "$0")/.." && pwd)                 # buddy/
PY=$HERE/.venv/bin/python
SSH="ssh -o ConnectTimeout=10 qnxuser@$PI"

pi_up() { curl -s -m 2 "http://$PI:8081/health" | grep -q '"ok": true'; }

if ! pi_up; then
  printf "waiting for the Pi at %s (power on? hotspot screen open?) " "$PI"
  until ping -c1 -W1 "$PI" >/dev/null 2>&1; do printf "."; sleep 2; done
  echo " found"
  for i in $(seq 10); do pi_up && break; sleep 2; done
  if ! pi_up; then
    echo "Squint isn't running on the Pi: starting it"
    $SSH 'SQUINT_DEMO= ./squint_start.sh' 2>&1 | grep -iv "post-quantum\|store now\|upgraded\|pq.html"
    until pi_up; do sleep 2; done
  fi
fi
echo "Pi ok"
"$PY" "$HERE/tools/mock_schedule.py" --pi "$PI" || exit 1
PI=$PI exec "$HERE/tools/laptop_start.sh" --no-xray "$@"
