#!/bin/sh
# Squint: start both camera streams and the recognition/coordinator service.
# After a reboot:  ssh qnxuser@<pi> ./squint_start.sh
#   :8080  Logitech Brio 101 (camera unit 8), pointing DOWN at the counter -> bottles
#   :8082  Logitech C270     (camera unit 5), pointing UP at the person    -> faces
# Optional: SQUINT_ARGS="--announce http://<laptop>:8765/announce" ./squint_start.sh
H=/data/home/qnxuser
for p in $(pidin -F "%a %N" | awk "\$2==\"camstream\" || \$2==\"python3\" {print \$1}"); do kill $p; done
sleep 2
cd $H/stream
(on -p 20 ./camstream 8 8080 80 1280 720 5 > camstream_bottles.log 2>&1 &)
(on -p 20 ./camstream 5 8082 75 960 544 20 > camstream_faces.log 2>&1 &)
sleep 3
cd $H/buddy && (nohup python3 -u -m buddy.service --bottle-source http://localhost:8080/stream \
    --face-source http://localhost:8082/stream $SQUINT_ARGS > service.log 2>&1 &)
echo "started: bottles :8080 (Brio), faces :8082 (C270), service :8081; logs in ~/stream and ~/buddy"
