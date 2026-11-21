# Pi camera stream

Streams the Raspberry Pi 5 camera (QNX 8) as MJPEG over HTTP. The camera in use is a
**Logitech C270 USB webcam** (camera unit 5), not a Camera Module.

## Build and run (on the Pi)

```sh
gcc -O2 -Wall -o camstream camstream.c -lcamapi -l:libturbojpeg.so.0 -lsocket
nohup ./camstream 5 8080 > camstream.log 2>&1 &
# args: [unit=5] [port=8080] [quality=75] [width=960] [height=544] [fps=20]
```

Camera unit 5 is the USB webcam; unit 1 is the built-in simulator. Units 3 and 4 are the
Camera Module (imx708) ports, empty right now.
Stop it with `slay ./camstream` (QNX names it with the `./`) or `kill <pid>`. Only one
process can hold the camera.

## Endpoints

- `/` – viewer page
- `/stream` – MJPEG (`cv2.VideoCapture("http://<pi-ip>:8080/stream")`, `ffplay`)
- `/snapshot.jpg` – single frame

## Notes

- No camera or turbojpeg headers ship on the device, so `camstream.c` declares
  the few functions it uses. The `camera_buffer_t` offsets it relies on were
  read off a live frame with `probe.c` (`gcc -o probe probe.c -lcamapi && ./probe 5`).
- Default output is 960×544 YCbYCr at 20 fps. Uncompressed over USB 2 the C270 does
  640×480 @ 30, 864×480 @ 24, 960×544 @ 20, 800×600 @ 15 and 1280×720 only @ 10
  (too slow for intake, which wants ≥ 12 fps). The QNX driver doesn't offer the
  C270's compressed MJPEG mode, so higher sizes at full speed aren't available.
- The viewfinder property ids (0 format, 1 width, 2 height, 3 framerate) were read
  back from the device. The frame rate must be lowered before the size is raised,
  otherwise the size is rejected.

## Running it

- **Run it at a fixed, high priority** so the camera can't be starved by recognition work:
  `on -p 20 ./camstream 5 8080 > camstream.log 2>&1 &`
- **Port 8080 belongs to the camera.** Recognition reads `http://localhost:8080/stream` on the
  Pi, or `http://<pi-ip>:8080/stream` from a laptop.
- **If the camera stalls, the stream goes quiet.** Consumers should treat no frames for a few
  seconds as "camera down", never reuse an old frame.

## Framing (counter-top device)

The device sits on a counter with the camera tilted up at people standing in front of it.
The C270 is fairly narrow (~55° diagonal), so people need to be roughly 0.6–1.2 m away for the
face and the hand holding a bottle to both be in view.
