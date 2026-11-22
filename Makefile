# Live demo shortcuts (run from the repo root). PI=<address> overrides the Pi's address.
SHELL := /bin/bash
PI ?= 172.20.10.9
.DEFAULT_GOAL := demo
SSH = ssh -o ConnectTimeout=10 qnxuser@$(PI)

.PHONY: demo reset view pi-start health logs restore qnx find-pi

find-pi:   ## which address the Pi (SSH :22) and Squint (:8081) are on, on this hotspot
	@net=$$(ip -4 -o addr show | awk '/172\.20\.10\./ {print $$4}' | cut -d/ -f1 | cut -d. -f1-3); \
	[ -n "$$net" ] || net=172.20.10; echo "scanning $$net.1-14 ..."; \
	for i in $$(seq 1 14); do ( a=$$net.$$i; \
	  curl -s -m 2 http://$$a:8081/health | grep -q '"ok"' && echo "$$a  Squint running  ->  make demo PI=$$a"; \
	  (echo > /dev/tcp/$$a/22) 2>/dev/null && echo "$$a  SSH open (the Pi?)" ) & done; wait

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
