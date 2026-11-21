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
