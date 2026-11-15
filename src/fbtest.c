/* Test: eigenes Bild über HiFB (EXTEND-Modus) anzeigen.
 *   fbtest [orientierung 0|1]
 * Zeichenfläche: hinterer Teil des fb0-Speichers (smem_start + 2 MiB), ARGB4444.
 * Anzeige per FBIO_REFRESH (0x4040467c, HIFB_BUFFER_S, Aufbau aus HIGO_ADP_SetLayerSurface):
 *   +8 u64 Phys-Adresse, +24 Breite, +28 Höhe, +32 Zeilenlänge, +36 Format (5 = ARGB4444),
 *   +48 Rechteck x, y, w, h
 */
#include <fcntl.h>
#include <linux/fb.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#define FBIO_REFRESH 0x4040467c
#define CANVAS_OFF   0x200000

int main(int argc, char **argv)
{
    int land = argc > 1 ? atoi(argv[1]) : 1;
    int W = land ? 320 : 240, H = land ? 240 : 320;
    int fd = open("/dev/fb0", O_RDWR);
    if (fd < 0) { perror("fb0"); return 1; }
    struct fb_fix_screeninfo fix;
    if (ioctl(fd, FBIOGET_FSCREENINFO, &fix)) { perror("FSCREENINFO"); return 1; }
    printf("smem_start %#lx len %u line %u\n", (unsigned long)fix.smem_start, fix.smem_len, fix.line_length);
    uint8_t *m = mmap(0, fix.smem_len, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (m == MAP_FAILED) { perror("mmap"); return 1; }
    uint16_t *c = (uint16_t *)(m + CANVAS_OFF);
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            uint16_t v = 0xF000;                                   /* schwarz */
            if (y < 40) v = 0xF0AF;                                /* blau: oben */
            else if (x < 20) v = 0xFF00;                           /* rot: links */
            else if ((x / 20 + y / 20) & 1) v = 0xF333;            /* Schachbrett */
            if (x > W - 30 && y > H - 30) v = 0xF0F0;              /* grün: unten rechts */
            c[y * W + x] = v;
        }
    uint8_t b[64];
    memset(b, 0, sizeof b);
    uint64_t phys = fix.smem_start + CANVAS_OFF;
    memcpy(b + 8, &phys, 8);
    uint32_t v[] = {W, H, W * 2, 5};
    memcpy(b + 24, v, sizeof v);
    uint32_t r[] = {0, 0, W, H};
    memcpy(b + 48, r, sizeof r);
    int ret = ioctl(fd, FBIO_REFRESH, b);
    printf("refresh %dx%d -> %d\n", W, H, ret);
    return ret ? 1 : 0;
}
