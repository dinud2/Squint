// camstream: QNX (Raspberry Pi 5) camera -> MJPEG over HTTP.
//   build: gcc -O2 -o camstream camstream.c -lcamapi -lturbojpeg -lsocket
//   run:   ./camstream [unit=5] [port=8080] [quality=75]
//   view:  http://<pi-ip>:8080/          (page)
//          http://<pi-ip>:8080/stream    (raw MJPEG, works in OpenCV/ffplay)
//          http://<pi-ip>:8080/snapshot.jpg
//
// No camera/turbojpeg headers ship on the device, so the few declarations we
// need are written out here. camera_buffer_t layout was verified with probe.c:
//   +0  frametype (14 = YCbYCr / YUYV), +16 framebuf pointer,
//   +72 framedesc: height, width, stride (uint32 each).

#include <errno.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

typedef int32_t camera_handle_t;
extern int camera_open(int unit, uint32_t mode, camera_handle_t *h);
extern int camera_close(camera_handle_t h);
extern int camera_start_viewfinder(camera_handle_t h,
                                   void (*cb)(camera_handle_t, void *, void *),
                                   void (*st)(camera_handle_t, int, uint16_t, void *),
                                   void *arg);
extern int camera_stop_viewfinder(camera_handle_t h);

typedef void *tjhandle;
extern tjhandle tjInitCompress(void);
extern int tjCompressFromYUVPlanes(tjhandle h, const unsigned char **planes, int width,
                                   const int *strides, int height, int subsamp,
                                   unsigned char **jpeg, unsigned long *size, int qual,
                                   int flags);
extern void tjFree(unsigned char *buf);
extern char *tjGetErrorStr2(tjhandle h);
#define TJSAMP_422 1
#define FT_YCBYCR 14

static int quality = 75;

// Latest encoded frame, shared with client threads.
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t newframe = PTHREAD_COND_INITIALIZER;
static unsigned char *frame;
static size_t frame_len, frame_cap;
static uint64_t frame_seq;

static tjhandle tj;
static unsigned char *planes_buf;
static size_t planes_cap;

static void on_frame(camera_handle_t h, void *buf, void *arg) {
    (void)h; (void)arg;
    uint8_t *b = buf;
    int type = *(int32_t *)b;
    uint8_t *data = *(uint8_t **)(b + 16);
    uint32_t height = *(uint32_t *)(b + 72);
    uint32_t width = *(uint32_t *)(b + 76);
    uint32_t stride = *(uint32_t *)(b + 80);
    if (type != FT_YCBYCR || !data || !width || !height) {
        static int warned;
        if (!warned++) fprintf(stderr, "unsupported frame type %d (%ux%u)\n", type, width, height);
        return;
    }

    // YUYV packed -> 4:2:2 planar for turbojpeg.
    size_t ysz = (size_t)width * height, csz = ysz / 2;
    if (planes_cap < ysz + 2 * csz) {
        free(planes_buf);
        planes_cap = ysz + 2 * csz;
        planes_buf = malloc(planes_cap);
    }
    uint8_t *Y = planes_buf, *U = Y + ysz, *V = U + csz;
    for (uint32_t r = 0; r < height; r++) {
        const uint8_t *s = data + (size_t)r * stride;
        uint8_t *y = Y + (size_t)r * width, *u = U + (size_t)r * width / 2, *v = V + (size_t)r * width / 2;
        for (uint32_t c = 0; c < width / 2; c++) {
            y[2 * c] = s[4 * c];
            u[c] = s[4 * c + 1];
            y[2 * c + 1] = s[4 * c + 2];
            v[c] = s[4 * c + 3];
        }
    }

    const unsigned char *planes[3] = {Y, U, V};
    int strides[3] = {(int)width, (int)width / 2, (int)width / 2};
    unsigned char *jpeg = NULL;
    unsigned long jlen = 0;
    if (tjCompressFromYUVPlanes(tj, planes, width, strides, height, TJSAMP_422, &jpeg, &jlen,
                                quality, 0) != 0) {
        fprintf(stderr, "jpeg: %s\n", tjGetErrorStr2(tj));
        return;
    }

    pthread_mutex_lock(&lock);
    if (frame_cap < jlen) {
        free(frame);
        frame_cap = jlen * 2;
        frame = malloc(frame_cap);
    }
    memcpy(frame, jpeg, jlen);
    frame_len = jlen;
    frame_seq++;
    pthread_cond_broadcast(&newframe);
    pthread_mutex_unlock(&lock);
    tjFree(jpeg);
}

static int send_all(int fd, const void *p, size_t n) {
    const char *c = p;
    while (n) {
        ssize_t w = send(fd, c, n, 0);
        if (w <= 0) { if (w < 0 && errno == EINTR) continue; return -1; }
        c += w; n -= (size_t)w;
    }
    return 0;
}

// Copies the next frame newer than *seq into a private buffer.
static size_t wait_frame(uint64_t *seq, unsigned char **buf, size_t *cap) {
    pthread_mutex_lock(&lock);
    while (frame_seq == *seq) pthread_cond_wait(&newframe, &lock);
    if (*cap < frame_len) { free(*buf); *cap = frame_cap; *buf = malloc(*cap); }
    memcpy(*buf, frame, frame_len);
    size_t n = frame_len;
    *seq = frame_seq;
    pthread_mutex_unlock(&lock);
    return n;
}

static const char PAGE[] =
    "<!doctype html><html><head><meta name=viewport content='width=device-width'>"
    "<title>Pi camera</title><style>body{margin:0;background:#111;display:grid;"
    "place-items:center;min-height:100vh}img{max-width:100%;max-height:100vh}</style>"
    "</head><body><img src='/stream'></body></html>";

static void *client(void *arg) {
    int fd = (int)(intptr_t)arg;
    char req[1024];
    ssize_t n = recv(fd, req, sizeof req - 1, 0);
    if (n <= 0) goto done;
    req[n] = 0;
    char hdr[256];
    unsigned char *buf = NULL;
    size_t cap = 0;
    uint64_t seq = 0;

    if (!strncmp(req, "GET /stream", 11)) {
        const char *h = "HTTP/1.1 200 OK\r\nCache-Control: no-cache\r\nConnection: close\r\n"
                        "Access-Control-Allow-Origin: *\r\n"
                        "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n\r\n";
        if (send_all(fd, h, strlen(h))) goto done;
        for (;;) {
            size_t len = wait_frame(&seq, &buf, &cap);
            int hl = snprintf(hdr, sizeof hdr,
                              "--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %zu\r\n\r\n", len);
            if (send_all(fd, hdr, hl) || send_all(fd, buf, len) || send_all(fd, "\r\n", 2)) break;
        }
    } else if (!strncmp(req, "GET /snapshot", 13)) {
        size_t len = wait_frame(&seq, &buf, &cap);
        int hl = snprintf(hdr, sizeof hdr,
                          "HTTP/1.1 200 OK\r\nContent-Type: image/jpeg\r\nContent-Length: %zu\r\n"
                          "Access-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n", len);
        if (!send_all(fd, hdr, hl)) send_all(fd, buf, len);
    } else {
        int hl = snprintf(hdr, sizeof hdr,
                          "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: %zu\r\n"
                          "Connection: close\r\n\r\n", sizeof PAGE - 1);
        if (!send_all(fd, hdr, hl)) send_all(fd, PAGE, sizeof PAGE - 1);
    }
    free(buf);
done:
    close(fd);
    return NULL;
}

static volatile sig_atomic_t stop;
static void on_sig(int s) { (void)s; stop = 1; }

int main(int argc, char **argv) {
    int unit = argc > 1 ? atoi(argv[1]) : 5;
    int port = argc > 2 ? atoi(argv[2]) : 8080;
    if (argc > 3) quality = atoi(argv[3]);
    signal(SIGPIPE, SIG_IGN);
    signal(SIGINT, on_sig);
    signal(SIGTERM, on_sig);

    tj = tjInitCompress();
    if (!tj) { fprintf(stderr, "tjInitCompress failed\n"); return 1; }

    camera_handle_t cam;
    int e = camera_open(unit, 0xF, &cam);
    if (e) e = camera_open(unit, 0x5, &cam);
    if (e) { fprintf(stderr, "camera_open(unit %d) failed: %d\n", unit, e); return 1; }
    if ((e = camera_start_viewfinder(cam, on_frame, NULL, NULL))) {
        fprintf(stderr, "camera_start_viewfinder failed: %d\n", e);
        camera_close(cam);
        return 1;
    }

    int s = socket(AF_INET, SOCK_STREAM, 0);
    int one = 1;
    setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    struct sockaddr_in a = {.sin_family = AF_INET, .sin_port = htons(port), .sin_addr.s_addr = INADDR_ANY};
    if (bind(s, (struct sockaddr *)&a, sizeof a) || listen(s, 8)) {
        perror("bind/listen");
        return 1;
    }
    printf("camstream: unit %d, serving http://0.0.0.0:%d/\n", unit, port);
    fflush(stdout);

    while (!stop) {
        int c = accept(s, NULL, NULL);
        if (c < 0) { if (errno == EINTR) continue; perror("accept"); break; }
        setsockopt(c, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
        pthread_t t;
        if (pthread_create(&t, NULL, client, (void *)(intptr_t)c) == 0) pthread_detach(t);
        else close(c);
    }
    camera_stop_viewfinder(cam);
    camera_close(cam);
    return 0;
}
