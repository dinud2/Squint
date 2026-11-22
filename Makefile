# Live demo shortcuts (run from the repo root). PI=<address> overrides the Pi's address.
PI ?= 172.20.10.9
SSH = ssh -o ConnectTimeout=10 qnxuser@$(PI)

.PHONY: demo reset view pi-start health logs restore qnx

demo:      ## reset today and launch everything (waits for the Pi, starts Squint if needed)
	PI=$(PI) buddy/tools/demo_time.sh

reset:     ## only reset today's doses + set the mock times
	buddy/.venv/bin/python buddy/tools/mock_schedule.py --pi $(PI)

view:      ## only the laptop side (voice, announcements, camera view), no reset
	PI=$(PI) buddy/tools/laptop_start.sh --no-xray

pi-start:  ## restart Squint on the Pi (real schedule, not --demo)
	$(SSH) 'SQUINT_DEMO= ./squint_start.sh'

health:    ## is the Pi up?
	@curl -s -m 3 http://$(PI):8081/health | head -c 200; echo

logs:      ## what was said, and the voice service
	@tail -n 20 /tmp/squint/speak.log /tmp/squint/voice.log

restore:   ## after the demo: put the real medicine times back
	buddy/.venv/bin/python buddy/tools/mock_schedule.py --pi $(PI) --restore

qnx:       ## for the QNX judge: camera at real-time priority 20, AI at 10
	$(SSH) 'pidin -F "%a %b %N %p" | grep -E "camstream|python3"'
