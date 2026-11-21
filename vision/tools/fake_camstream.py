"""A laptop stand-in for Dinu's pi/camstream.c: same endpoints, same MJPEG format.

    python tools/fake_camstream.py --source 0          # your webcam
    python tools/fake_camstream.py --source clip.mp4   # a recorded clip, looped
    python tools/fake_camstream.py --source pattern    # moving test pattern, no camera

Then point anything at http://localhost:8080/stream, exactly as you would at the Pi.
"""
import argparse
import http.server
import socketserver
import threading
import time

import cv2
import numpy as np

latest = {"jpg": None}
cond = threading.Condition()


def producer(source, fps, quality):
    cap = None
    is_webcam = source.isdigit()
    if source != "pattern":
        cap = cv2.VideoCapture(int(source) if is_webcam else source)
        if not cap.isOpened():
            print(f"!! could not open {source}. On macOS: System Settings > Privacy & Security > Camera "
                  f"> allow your terminal app, then restart the terminal.", flush=True)
    i, fails = 0, 0
    while True:
        t0 = time.time()
        if cap is not None and is_webcam:
            ok, f = cap.read()
            if not ok:
                fails += 1
                if fails in (20, 200):
                    print(f"!! webcam {source} opened but returns no frames ({fails} tries). Usually the camera "
                          "permission for your terminal app (System Settings > Privacy & Security > Camera), "
                          "or another app (Zoom, FaceTime, Photo Booth) is using it.", flush=True)
                time.sleep(0.05)
                continue
            if fails:
                print("webcam frames OK", flush=True)
                fails = 0
            f = cv2.resize(f, (640, 480))
        elif cap is None:
            f = np.full((480, 640, 3), 40, np.uint8)
            x = int(320 + 250 * np.sin(i / 15))
            cv2.circle(f, (x, 240), 40, (0, 200, 255), -1)
            cv2.putText(f, f"fake camstream {i}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        else:
            ok, f = cap.read()
            if not ok:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            f = cv2.resize(f, (640, 480))
        jpg = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, quality])[1].tobytes()
        with cond:
            latest["jpg"] = jpg
            cond.notify_all()
        i += 1
        time.sleep(max(0, 1 / fps - (time.time() - t0)))


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/stream"):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            last = None
            try:
                while True:
                    with cond:
                        cond.wait_for(lambda: latest["jpg"] is not last)
                        jpg = last = latest["jpg"]
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpg))
                    self.wfile.write(jpg + b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                return
        elif self.path.startswith("/snapshot.jpg"):
            with cond:
                cond.wait_for(lambda: latest["jpg"] is not None)
                jpg = latest["jpg"]
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(jpg)))
            self.end_headers()
            self.wfile.write(jpg)
        else:
            body = b"<img src='/stream'>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="pattern")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--fps", type=float, default=20)
    ap.add_argument("--quality", type=int, default=75)
    a = ap.parse_args()
    threading.Thread(target=producer, args=(a.source, a.fps, a.quality), daemon=True).start()
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("0.0.0.0", a.port), Handler) as s:
        s.daemon_threads = True
        print(f"fake camstream on http://localhost:{a.port}/stream  (source={a.source})")
        s.serve_forever()


if __name__ == "__main__":
    main()
