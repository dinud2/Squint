#!/bin/sh
# Squint: start the camera stream and the recognition/coordinator service.
# After a reboot (or a camera unplug/replug):  ssh qnxuser@<pi> ./squint_start.sh
#   :8080  Logitech C270 (camera unit 5) at the person: faces, and bottles held up to it
#   :8081  buddy.service (API, coordinator); /cams shows the camera
# Optional: SQUINT_ARGS="--announce http://<laptop>:8765/announce" ./squint_start.sh
H=/data/home/qnxuser
for p in $(pidin -F "%a %N" | awk '$2=="camstream" || $2=="python3" {print $1}'); do kill $p; done
sleep 2
# A camera that was unplugged and plugged back in does not come back by itself: QNX's
# camera service drops its unit. If it is missing, restart the camera service.
if [ ! -e /dev/sensor/camera5 ]; then
  echo "camera unit missing: restarting the camera service"
  SP=$(sudo pidin arg | awk '$2=="sensor" && $3=="-U" {print $1}')
  [ -n "$SP" ] && sudo kill $SP && sleep 2
  sudo sh -c "nohup sensor -U 521:521 -b external -r /data/share/sensor -c /etc/config/sensor/sensor_rpi5.conf > /dev/null 2>&1 < /dev/null &"
  waitfor /dev/sensor/camera5 10
fi
cd $H/stream
(on -p 20 ./camstream 5 8080 75 960 544 20 > camstream.log 2>&1 &)
sleep 3
# Dose times are local (Toronto); the Pi clock is UTC, so give the service the time zone.
export TZ="${SQUINT_TZ:-EST5EDT,M3.2.0,M11.1.0}"
cd $H/buddy && (nohup python3 -u -m buddy.service --bottle-source http://localhost:8080/stream \
    --face-source http://localhost:8080/stream $SQUINT_ARGS > service.log 2>&1 &)
echo "started: C270 :8080 (faces + bottles), service :8081 (/cams); logs in ~/stream and ~/buddy"
