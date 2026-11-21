#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#include <unistd.h>
typedef int32_t camera_handle_t;
extern int camera_open(int unit, uint32_t mode, camera_handle_t *h);
extern int camera_close(camera_handle_t h);
extern int camera_start_viewfinder(camera_handle_t h, void (*cb)(camera_handle_t, void *, void *), void (*st)(camera_handle_t, int, uint16_t, void *), void *arg);
extern int camera_stop_viewfinder(camera_handle_t h);
extern int camera_get_supported_vf_frame_types(camera_handle_t h, uint32_t n, uint32_t *ns, int *types);
static int count;
static void cb(camera_handle_t h, void *b, void *a) {
    if (count++ != 5) return;
    uint32_t *w = b;
    for (int i = 0; i < 40; i++) printf("%2d @%3d: %u (0x%x)\n", i, i * 4, w[i], w[i]);
    fflush(stdout);
}
int main(int argc, char **argv) {
    camera_handle_t h;
    int unit = argc > 1 ? atoi(argv[1]) : 5;
    int e = camera_open(unit, 0xF, &h);
    if (e) { e = camera_open(unit, 0x5, &h); }
    printf("open %d\n", e);
    int types[32]; uint32_t ns = 0;
    e = camera_get_supported_vf_frame_types(h, 32, &ns, types);
    printf("types err %d n %u:", e, ns); for (uint32_t i = 0; i < ns; i++) printf(" %d", types[i]); printf("\n");
    e = camera_start_viewfinder(h, cb, NULL, NULL); printf("start %d\n", e); fflush(stdout);
    sleep(2);
    camera_stop_viewfinder(h); camera_close(h);
    return 0;
}
