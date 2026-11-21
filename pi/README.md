# Pi camera stream

Streams the Raspberry Pi 5 camera (QNX 8, Camera Module 3 / imx708) as MJPEG over HTTP.

## Build and run (on the Pi)

```sh
gcc -O2 -Wall -o camstream camstream.c -lcamapi -l:libturbojpeg.so.0 -lsocket
nohup ./camstream 5 8080 > camstream.log 2>&1 &   # args: [unit=5] [port=8080] [quality=75]
```

Camera unit 5 is the real camera; unit 1 is the built-in simulator.
Stop it with `slay camstream` (only one process can hold the camera).

## Endpoints

- `/` – viewer page
- `/stream` – MJPEG (`cv2.VideoCapture("http://<pi-ip>:8080/stream")`, `ffplay`)
- `/snapshot.jpg` – single frame

## Notes

- No camera or turbojpeg headers ship on the device, so `camstream.c` declares
  the few functions it uses. The `camera_buffer_t` offsets it relies on were
  read off a live frame with `probe.c` (`gcc -o probe probe.c -lcamapi && ./probe 5`).
- Default output is 640×480 YCbYCr at roughly 20 fps.

## Running it for Squint

- **Run it at a fixed, high priority** so the camera can't be starved by other work (the STOP path
  starts here). Part B sets the final priorities; for now:
  `on -p 20 ./camstream 5 8080 > camstream.log 2>&1 &`
- **Port 8080 belongs to the camera.** The station API (Part A) uses a different port.
- **Vision reads this stream**: `python3 vision_main.py --source http://localhost:8080/stream`
  on the Pi, or `--source http://<pi-ip>:8080/stream` from a laptop.
- **If the camera stalls, the stream simply goes quiet.** That is intended: vision gives up
  after 5 s, its `alive` heartbeat stops and the alarm turns amber. Never resend an old frame.

## Framing (standard Camera Module 3, ~66° field of view, not the Wide)

Squint needs Margaret's **face and hands** in view. With the standard lens that means about
**0.9–1.4 m** from the camera, lens roughly at chest-to-chin height, tilted slightly up.
Check with `python tools/camera_check.py --source http://<pi-ip>:8080/stream --show` (in `vision/`):
nose ≥ 80%, and a wrist visible when you raise a hand to your mouth.
