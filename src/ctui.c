/* ctui - eigenes Einstellungsmenü der CT9500 (moderne Optik), läuft neben main_app.
 *
 * Ablauf (siehe src/menuhook.S, Abschnitt "Eigenes Menü"):
 *   - ctui legt die FIFO /dev/ct9500mod/ui.fifo an und wartet auf 4-Byte-Nachrichten.
 *   - Lang WLAN-Taste auf der Startseite: main_app schickt UI_OPEN. ctui merkt sich HiGVs
 *     Zeichenfläche (/proc/umap/hifb0), legt /dev/ct9500mod/ui_active an und zeichnet.
 *   - Solange ui_active existiert, unterdrückt main_app seine Bildaktualisierung und schickt
 *     alle Tasten als Tastencode in die FIFO.
 *   - Schließen: ui_active löschen, HiGVs Zeichenfläche wieder anzeigen (FBIO_REFRESH).
 * Einstellungen über die CGI-Schnittstelle von main_app (http://127.0.0.1/cgi-bin/hi3510/).
 *
 * Anzeige: Zeichenfläche im hinteren fb0-Speicher (+2 MiB), 320x240 ARGB4444, HiFB dreht sie.
 * Schrift: res/font/vector.ttf (Inter, tools/mkfont.py) per stb_truetype (Public Domain).
 * Icons: /app/hack/ui/<name>.rgba (u16 Breite, u16 Höhe, RGBA8), tools/mkicons.py.
 */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/fb.h>
#include <netinet/in.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <poll.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

#define STB_TRUETYPE_IMPLEMENTATION
#define STBTT_STATIC
#include "third_party/stb_truetype.h"

#define W 320
#define H 240
#define FBIO_REFRESH 0x4040467c
#define CANVAS_OFF 0x200000
#define RUN "/dev/ct9500mod"
#define FIFO RUN "/ui.fifo"
#define FLAG RUN "/ui_active"
#define SYSSET RUN "/ui_sysset"
#define FONT "/app/bin/res/font/vector.ttf"
#define ICONS "/app/hack/ui/"
#define UI_OPEN 0x55490001u

#define KEY_OK 0x1003a
#define KEY_DOWN 0x1003b
#define KEY_BACK 0x1003c
#define KEY_UP 0x1003d
#define KEY_WIFI_LONG 0x10039

/* ------------------------------------------------------------------ Farben (dunkles Design) */
typedef uint32_t rgb;                       /* 0xRRGGBB */
#define C_BG     0x000000
#define C_CELL   0x1C1C1E
#define C_SEP    0x38383A
#define C_TEXT   0xFFFFFF
#define C_SUB    0x8E8E93
#define C_ACCENT 0x0A84FF

static void logf_(const char *fmt, ...)
{
    FILE *f = fopen(RUN "/ctui.log", "a");
    if (!f) return;
    va_list ap;
    va_start(ap, fmt);
    vfprintf(f, fmt, ap);
    va_end(ap);
    fputc('\n', f);
    fclose(f);
}

/* ------------------------------------------------------------------ Zeichnen */
static uint8_t px[H][W][3];                 /* RGB-Arbeitspuffer */

static void fill(int x0, int y0, int x1, int y1, rgb c)
{
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 > W) x1 = W;
    if (y1 > H) y1 = H;
    for (int y = y0; y < y1; y++)
        for (int x = x0; x < x1; x++) {
            px[y][x][0] = c >> 16; px[y][x][1] = c >> 8; px[y][x][2] = c;
        }
}

static void blend(int x, int y, rgb c, int a)
{
    if (x < 0 || y < 0 || x >= W || y >= H || a <= 0) return;
    if (a > 255) a = 255;
    uint8_t *p = px[y][x];
    p[0] = (p[0] * (255 - a) + ((c >> 16) & 255) * a) / 255;
    p[1] = (p[1] * (255 - a) + ((c >> 8) & 255) * a) / 255;
    p[2] = (p[2] * (255 - a) + (c & 255) * a) / 255;
}

/* Abgerundetes Rechteck mit Kantenglättung (4x4 Überabtastung an den Ecken) */
static void rrect(int x0, int y0, int x1, int y1, int r, rgb c)
{
    for (int y = y0; y < y1; y++)
        for (int x = x0; x < x1; x++) {
            int dx = x < x0 + r ? x0 + r - x : (x >= x1 - r ? x - (x1 - r - 1) : 0);
            int dy = y < y0 + r ? y0 + r - y : (y >= y1 - r ? y - (y1 - r - 1) : 0);
            if (!dx || !dy) { blend(x, y, c, 255); continue; }
            int in = 0;
            for (int sy = 0; sy < 4; sy++)
                for (int sx = 0; sx < 4; sx++) {
                    float fx = dx - 0.5f + (sx + 0.5f) / 4 - 0.5f, fy = dy - 0.5f + (sy + 0.5f) / 4 - 0.5f;
                    if (fx * fx + fy * fy <= (float)r * r) in++;
                }
            blend(x, y, c, in * 255 / 16);
        }
}

/* ------------------------------------------------------------------ Schrift */
static stbtt_fontinfo font;
static unsigned char *fontdata;

static int load_font(void)
{
    FILE *f = fopen(FONT, "rb");
    if (!f) return -1;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    fontdata = malloc(n);
    if (fread(fontdata, 1, n, f) != (size_t)n) { fclose(f); return -1; }
    fclose(f);
    return stbtt_InitFont(&font, fontdata, 0) ? 0 : -1;
}

static int utf8(const char **s)
{
    const unsigned char *p = (const unsigned char *)*s;
    int c = *p++;
    if (c >= 0xF0) { c = (c & 7) << 18 | (p[0] & 63) << 12 | (p[1] & 63) << 6 | (p[2] & 63); p += 3; }
    else if (c >= 0xE0) { c = (c & 15) << 12 | (p[0] & 63) << 6 | (p[1] & 63); p += 2; }
    else if (c >= 0xC0) { c = (c & 31) << 6 | (p[0] & 63); p += 1; }
    *s = (const char *)p;
    return c;
}

static int text_w(const char *s, float size)
{
    float sc = stbtt_ScaleForPixelHeight(&font, size), x = 0;
    int prev = 0;
    while (*s) {
        int c = utf8(&s), adv, lsb;
        if (prev) x += sc * stbtt_GetCodepointKernAdvance(&font, prev, c);
        stbtt_GetCodepointHMetrics(&font, c, &adv, &lsb);
        x += adv * sc;
        prev = c;
    }
    return (int)(x + 0.5f);
}

/* Text mit Grundlinie bei y; bold = zweifach versetzt gezeichnet; maxw > 0 kürzt mit "…" */
static int text(int x, int y, const char *s, float size, rgb c, int bold, int maxw)
{
    char buf[128];
    if (maxw > 0 && text_w(s, size) > maxw) {
        int n = strlen(s);
        if (n > 120) n = 120;
        while (n > 0) {
            memcpy(buf, s, n); strcpy(buf + n, "\xe2\x80\xa6");
            if (text_w(buf, size) <= maxw) break;
            do n--; while (n > 0 && ((unsigned char)s[n] & 0xC0) == 0x80);
        }
        s = buf;
    }
    float sc = stbtt_ScaleForPixelHeight(&font, size), fx = x;
    int prev = 0;
    while (*s) {
        int cp = utf8(&s), adv, lsb, gw, gh, ox, oy;
        if (prev) fx += sc * stbtt_GetCodepointKernAdvance(&font, prev, cp);
        stbtt_GetCodepointHMetrics(&font, cp, &adv, &lsb);
        float sub = fx - (int)fx;
        unsigned char *bm = stbtt_GetCodepointBitmapSubpixel(&font, sc, sc, sub, 0, cp, &gw, &gh, &ox, &oy);
        if (bm) {
            for (int j = 0; j < gh; j++)
                for (int i = 0; i < gw; i++) {
                    int a = bm[j * gw + i];
                    blend((int)fx + ox + i, y + oy + j, c, a);
                    if (bold) blend((int)fx + ox + i + 1, y + oy + j, c, a * 2 / 3);
                }
            stbtt_FreeBitmap(bm, 0);
        }
        fx += adv * sc + (bold ? 0.6f : 0);
        prev = cp;
    }
    return (int)fx;
}

/* ------------------------------------------------------------------ Icons */
static void icon(int x, int y, const char *name, int size)
{
    char p[128];
    snprintf(p, sizeof p, ICONS "%s.rgba", name);
    FILE *f = fopen(p, "rb");
    if (!f) return;
    uint16_t wh[2];
    if (fread(wh, 2, 2, f) == 2) {
        int iw = wh[0], ih = wh[1];
        uint8_t *d = malloc(iw * ih * 4);
        if (d && fread(d, 4, iw * ih, f) == (size_t)(iw * ih))
            for (int j = 0; j < size; j++)            /* einfache Skalierung (nächster Nachbar) */
                for (int i = 0; i < size; i++) {
                    uint8_t *s = d + 4 * ((j * ih / size) * iw + i * iw / size);
                    blend(x + i, y + j, s[0] << 16 | s[1] << 8 | s[2], s[3]);
                }
        free(d);
    }
    fclose(f);
}

/* ------------------------------------------------------------------ Anzeige (HiFB) */
static int fbfd = -1;
static uint8_t *fbmem;
static unsigned long fbphys;
static uint32_t higv_addr, higv_w, higv_h, higv_pitch;

static int fb_init(void)
{
    struct fb_fix_screeninfo fix;
    fbfd = open("/dev/fb0", O_RDWR);
    if (fbfd < 0 || ioctl(fbfd, FBIOGET_FSCREENINFO, &fix)) return -1;
    fbmem = mmap(0, fix.smem_len, PROT_READ | PROT_WRITE, MAP_SHARED, fbfd, 0);
    if (fbmem == MAP_FAILED) return -1;
    fbphys = fix.smem_start;
    return 0;
}

static int refresh_surface(uint64_t phys, uint32_t w, uint32_t h, uint32_t pitch)
{
    uint8_t b[64];
    memset(b, 0, sizeof b);
    memcpy(b + 8, &phys, 8);
    uint32_t v[] = {w, h, pitch, 5};        /* 5 = ARGB4444 */
    memcpy(b + 24, v, sizeof v);
    uint32_t r[] = {0, 0, w, h};
    memcpy(b + 48, r, sizeof r);
    return ioctl(fbfd, FBIO_REFRESH, b);
}

/* HiGVs Zeichenfläche aus /proc/umap/hifb0 ("canavas updated addr", Breite, Höhe, Pitch) */
static void remember_higv(void)
{
    FILE *f = fopen("/proc/umap/hifb0", "r");
    char l[160];
    if (!f) return;
    while (fgets(l, sizeof l, f)) {
        char *c = strchr(l, ':');
        if (!c) continue;
        if (strstr(l, "canavas updated addr") || strstr(l, "canvas updated addr")) {
            uint32_t a = strtoul(c + 1, 0, 16);
            if (a != fbphys + CANVAS_OFF) higv_addr = a;
        } else if (strstr(l, "canvas width")) higv_w = atoi(c + 1);
        else if (strstr(l, "canvas height")) higv_h = atoi(c + 1);
        else if (strstr(l, "canvas pitch")) higv_pitch = atoi(c + 1);
    }
    fclose(f);
    logf_("HiGV-Zeichenfläche %#x %ux%u pitch %u", higv_addr, higv_w, higv_h, higv_pitch);
}

static void present(void)
{
    static const uint8_t bayer[4][4] = {{0, 8, 2, 10}, {12, 4, 14, 6}, {3, 11, 1, 9}, {15, 7, 13, 5}};
    uint16_t *c = (uint16_t *)(fbmem + CANVAS_OFF);
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            int d = bayer[y & 3][x & 3];
            int r = px[y][x][0] + d, g = px[y][x][1] + d, b = px[y][x][2] + d;
            r = r > 255 ? 255 : r; g = g > 255 ? 255 : g; b = b > 255 ? 255 : b;
            c[y * W + x] = 0xF000 | (r >> 4) << 8 | (g >> 4) << 4 | (b >> 4);
        }
    refresh_surface(fbphys + CANVAS_OFF, W, H, W * 2);
}

/* ------------------------------------------------------------------ CGI von main_app */
static char http_buf[8192];

static const char *cgi(const char *fmt, ...)
{
    char q[512], req[700];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(q, sizeof q, fmt, ap);
    va_end(ap);
    for (char *p = q; *p; p++) if (*p == ' ') *p = '+';
    http_buf[0] = 0;
    int s = socket(AF_INET, SOCK_STREAM, 0);
    struct sockaddr_in a = {.sin_family = AF_INET, .sin_port = htons(80)};
    a.sin_addr.s_addr = htonl(0x7f000001);
    struct timeval tv = {3, 0};
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
    if (connect(s, (void *)&a, sizeof a) == 0) {
        int n = snprintf(req, sizeof req, "GET /cgi-bin/hi3510/%s HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n", q);
        if (write(s, req, n) == n) {
            int got = 0, r;
            while (got < (int)sizeof http_buf - 1 && (r = read(s, http_buf + got, sizeof http_buf - 1 - got)) > 0) got += r;
            http_buf[got] = 0;
        }
    }
    close(s);
    char *body = strstr(http_buf, "\r\n\r\n");
    return body ? body + 4 : http_buf;
}

/* var name="wert"; aus einer CGI-Antwort */
static int cgi_var(const char *resp, const char *name, char *out, int n)
{
    char key[64];
    snprintf(key, sizeof key, "var %s=\"", name);
    const char *p = strstr(resp, key);
    if (!p) { out[0] = 0; return -1; }
    p += strlen(key);
    int i = 0;
    while (*p && *p != '"' && i < n - 1) out[i++] = *p++;
    out[i] = 0;
    return 0;
}

static int split(char *s, char **parts, int max)
{
    int n = 0;
    if (!*s) return 0;
    parts[n++] = s;
    for (; *s && n < max; s++)
        if (*s == ',') { *s = 0; parts[n++] = s + 1; }
    return n;
}

/* ------------------------------------------------------------------ Texte (Deutsch) */
static const char *de(const char *en)
{
    static const char *t[][2] = {
        {"NormalVideo", "Video"}, {"Loop Video", "Loop"}, {"VideoLapse", "Zeitraffer"}, {"SlowRec", "Zeitlupe"},
        {"NormalPhoto", "Foto"}, {"TimerPhoto", "Selbstauslöser"}, {"Burst", "Serienbild"},
        {"Resolution", "Auflösung"}, {"Lens Angle", "Bildwinkel"}, {"Record Mute", "Ton stumm"},
        {"Encode Mode", "Encoder"}, {"AWB", "Weißabgleich"}, {"Exposure Compensation", "Belichtung"},
        {"Data Stamp", "Datumsstempel"}, {"Scene", "Szene"}, {"DNG", "RAW (DNG)"}, {"Loop Time", "Loop-Dauer"},
        {"Lapse Interval", "Intervall"}, {"Timer", "Timer"}, {"Burst Type", "Serie"}, {"Slow Rate", "Zeitlupe"},
        {"ON", "An"}, {"OFF", "Aus"}, {"AUTO", "Auto"}, {"Auto", "Auto"}, {"Wide", "Weit"}, {"Medium", "Mittel"},
        {"Narrow", "Eng"}, {"Linear", "Linear"}, {"Daylight", "Tageslicht"}, {"Cloudy", "Bewölkt"},
        {"Tungsten", "Glühlampe"}, {"Fluorescent", "Leuchtstoff"}, {"Night", "Nacht"}, {"Portrait", "Porträt"},
        {"Landscape", "Landschaft"}, {"Water", "Wasser"}, {"Defog", "Entnebeln"},
    };
    for (unsigned i = 0; i < sizeof t / sizeof t[0]; i++)
        if (!strcmp(en, t[i][0])) return t[i][1];
    return en;
}

static const char *mode_icon(const char *wm)
{
    if (strstr(wm, "Loop")) return "loop";
    if (strstr(wm, "Lapse")) return "lapse";
    if (strstr(wm, "Slow")) return "slow";
    if (strstr(wm, "Timer")) return "timer";
    if (strstr(wm, "Burst")) return "burst";
    if (strstr(wm, "Photo")) return "photosize";
    return "resolution";
}

static const char *item_icon(const char *it)
{
    static const char *t[][2] = {
        {"Resolution", "resolution"}, {"Lens Angle", "fov"}, {"Record Mute", "audio_mute"}, {"Encode Mode", "encode"},
        {"AWB", "wb"}, {"Exposure Compensation", "expose"}, {"ISO", "iso"}, {"Data Stamp", "date_stamp"},
        {"Scene", "scene"}, {"DNG", "dng"}, {"Loop Time", "loop"}, {"Lapse Interval", "lapse"}, {"Timer", "timer"},
        {"Burst Type", "burst"}, {"Slow Rate", "slow"},
    };
    for (unsigned i = 0; i < sizeof t / sizeof t[0]; i++)
        if (!strcmp(it, t[i][0])) return t[i][1];
    return "vinfo";
}

/* ------------------------------------------------------------------ Seiten */
#define MAXROWS 24
struct rowd { char label[48], value[48], icon[24], key[48]; int chevron, toggle, check; };
struct page {
    int kind;                 /* P_MAIN, P_MODES, P_ITEMS, P_OPTIONS, P_CONN */
    char title[48], arg[48];
    int n, sel, top;
    struct rowd r[MAXROWS];
};
enum { P_MAIN, P_MODES, P_ITEMS, P_OPTIONS, P_CONN };

static struct page stack[6];
static int depth;
static char cur_mode[48];

static void load_page(struct page *p)
{
    char buf[1024], *parts[MAXROWS], *vals[MAXROWS];
    p->n = 0;
    if (p->kind == P_MAIN) {
        const char *r = cgi("getcurworkmode.cgi?-act=get");
        cgi_var(r, "workmode", cur_mode, sizeof cur_mode);
        struct { const char *l, *i; } m[] = {{"Modus", mode_icon(cur_mode)}, {"Aufnahme", "resolution"},
                                             {"Verbindungen", "wifi"}, {"System", "ldc"}};
        for (int i = 0; i < 4; i++) {
            struct rowd *d = &p->r[p->n++];
            memset(d, 0, sizeof *d);
            strcpy(d->label, m[i].l); strcpy(d->icon, m[i].i); d->chevron = 1;
        }
        snprintf(p->r[0].value, sizeof p->r[0].value, "%s", de(cur_mode));
        snprintf(p->r[1].value, sizeof p->r[1].value, "%s", de(cur_mode));
        snprintf(p->r[3].value, sizeof p->r[3].value, "Alle Einstellungen");
    } else if (p->kind == P_MODES) {
        char v[256], ph[256];
        const char *r = cgi("getallworkmode.cgi?-act=get");
        cgi_var(r, "video", v, sizeof v);
        cgi_var(r, "photo", ph, sizeof ph);
        snprintf(buf, sizeof buf, "%s%s%s", v, *ph ? "," : "", ph);
        int n = split(buf, parts, MAXROWS);
        for (int i = 0; i < n; i++) {
            struct rowd *d = &p->r[p->n++];
            memset(d, 0, sizeof *d);
            snprintf(d->label, sizeof d->label, "%s", de(parts[i]));
            snprintf(d->key, sizeof d->key, "%s", parts[i]);
            snprintf(d->icon, sizeof d->icon, "%s", mode_icon(parts[i]));
            if (!strcmp(parts[i], cur_mode)) { d->check = 1; p->sel = i; }
        }
    } else if (p->kind == P_ITEMS) {
        char it[512], cu[512];
        const char *r = cgi("getprimarymenuitem.cgi?-act=get&-workmode=%s", cur_mode);
        cgi_var(r, "item", it, sizeof it);
        cgi_var(r, "cur", cu, sizeof cu);
        int n = split(it, parts, MAXROWS), m = split(cu, vals, MAXROWS);
        for (int i = 0; i < n; i++) {
            struct rowd *d = &p->r[p->n++];
            memset(d, 0, sizeof *d);
            snprintf(d->label, sizeof d->label, "%s", de(parts[i]));
            snprintf(d->key, sizeof d->key, "%s", parts[i]);
            snprintf(d->value, sizeof d->value, "%s", i < m ? de(vals[i]) : "");
            snprintf(d->icon, sizeof d->icon, "%s", item_icon(parts[i]));
            d->chevron = 1;
        }
    } else if (p->kind == P_OPTIONS) {
        char it[512], cv[64];
        const char *r = cgi("getsecondmenuitem.cgi?-act=get&-workmode=%s&-name=%s", cur_mode, p->arg);
        cgi_var(r, "item", it, sizeof it);
        cgi_var(r, "value", cv, sizeof cv);
        int n = split(it, parts, MAXROWS);
        for (int i = 0; i < n; i++) {
            struct rowd *d = &p->r[p->n++];
            memset(d, 0, sizeof *d);
            snprintf(d->label, sizeof d->label, "%s", de(parts[i]));
            snprintf(d->key, sizeof d->key, "%s", parts[i]);
            if (!strcmp(parts[i], cv)) { d->check = 1; p->sel = i; }
        }
    } else if (p->kind == P_CONN) {
        static const char *l[] = {"WLAN-Autostart", "Heimnetz", "Telnet"};
        for (int i = 0; i < 3; i++) {
            char cmd[96];
            snprintf(cmd, sizeof cmd, "/app/hack/menu.sh get %d", i);
            int st = system(cmd);
            st = WIFEXITED(st) ? WEXITSTATUS(st) : 0;
            struct rowd *d = &p->r[p->n++];
            memset(d, 0, sizeof *d);
            strcpy(d->label, l[i]);
            strcpy(d->icon, i == 2 ? "md" : "wifi");
            d->toggle = 1 + (st == 1);         /* 1 = aus, 2 = an */
        }
    }
    if (p->sel >= p->n) p->sel = 0;
}

/* ------------------------------------------------------------------ Darstellung einer Seite */
#define HEAD 46
#define ROWH 38
#define VISIBLE 5

static void draw_toggle(int x, int y, int on)
{
    rrect(x, y, x + 40, y + 24, 12, on ? 0x30D158 : 0x39393D);
    rrect(on ? x + 18 : x + 2, y + 2, on ? x + 38 : x + 22, y + 22, 10, 0xFFFFFF);
}

/* Häkchen (✓ fehlt in der Schrift): zwei dicke, geglättete Linien */
static void line_aa(float x0, float y0, float x1, float y1, float w, rgb c)
{
    int minx = (int)(x0 < x1 ? x0 : x1) - 3, maxx = (int)(x0 > x1 ? x0 : x1) + 3;
    int miny = (int)(y0 < y1 ? y0 : y1) - 3, maxy = (int)(y0 > y1 ? y0 : y1) + 3;
    float dx = x1 - x0, dy = y1 - y0, l2 = dx * dx + dy * dy;
    for (int y = miny; y <= maxy; y++)
        for (int x = minx; x <= maxx; x++) {
            float t = ((x - x0) * dx + (y - y0) * dy) / l2;
            t = t < 0 ? 0 : t > 1 ? 1 : t;
            float ex = x0 + t * dx - x, ey = y0 + t * dy - y, d = ex * ex + ey * ey;
            float r = w / 2, a = (r + 0.5f - __builtin_sqrtf(d));
            if (a > 0) blend(x, y, c, a >= 1 ? 255 : (int)(a * 255));
        }
}

static void draw_check(int x, int y, rgb c)
{
    line_aa(x, y + 7, x + 5, y + 12, 2.4f, c);
    line_aa(x + 5, y + 12, x + 14, y + 1, 2.4f, c);
}

static void draw(void)
{
    struct page *p = &stack[depth];
    fill(0, 0, W, H, C_BG);
    /* Kopf: Zurück-Hinweis + großer Titel */
    if (depth > 0) text(10, 18, "\xe2\x80\xb9 Zur\xc3\xbc" "ck", 13, C_ACCENT, 0, 0);
    text(12, depth > 0 ? 40 : 34, p->title, depth > 0 ? 20 : 24, C_TEXT, 1, W - 24);
    if (p->sel < p->top) p->top = p->sel;
    if (p->sel >= p->top + VISIBLE) p->top = p->sel - VISIBLE + 1;
    int y0 = HEAD + 2;
    int shown = p->n - p->top < VISIBLE ? p->n - p->top : VISIBLE;
    rrect(8, y0, W - 8, y0 + shown * ROWH, 10, C_CELL);
    for (int k = 0; k < shown; k++) {
        int i = p->top + k, y = y0 + k * ROWH;
        struct rowd *d = &p->r[i];
        if (i == p->sel) rrect(8, y, W - 8, y + ROWH, 10, C_ACCENT);
        int x = 18;
        if (d->icon[0]) { icon(x - 2, y + 5, d->icon, 28); x += 34; }
        int right = W - 18;
        if (d->chevron) { text(right - 7, y + 25, "\xe2\x80\xba", 20, i == p->sel ? C_TEXT : C_SUB, 0, 0); right -= 14; }
        if (d->toggle) { draw_toggle(right - 40, y + 7, d->toggle == 2); right -= 46; }
        if (d->check) { draw_check(right - 14, y + 12, i == p->sel ? C_TEXT : C_ACCENT); right -= 22; }
        int vw = 0;
        if (d->value[0]) {
            vw = text_w(d->value, 15);
            if (vw > 120) vw = 120;
            text(right - vw, y + 25, d->value, 15, i == p->sel ? 0xE5F0FF : C_SUB, 0, 120);
        }
        text(x, y + 25, d->label, 16, C_TEXT, 0, right - vw - x - 8);
        if (k < shown - 1 && i != p->sel && i + 1 != p->sel) fill(x, y + ROWH - 1, W - 8, y + ROWH, C_SEP);
    }
    /* Bildlaufanzeige */
    if (p->n > VISIBLE) {
        int th = shown * ROWH, bh = th * VISIBLE / p->n, by = y0 + th * p->top / p->n;
        rrect(W - 5, by, W - 2, by + bh, 1, 0x636366);
    }
    present();
}

/* ------------------------------------------------------------------ Steuerung */
static int active;

static void push(int kind, const char *title, const char *arg)
{
    if (depth >= 5) return;
    struct page *p = &stack[++depth];
    memset(p, 0, sizeof *p);
    p->kind = kind;
    snprintf(p->title, sizeof p->title, "%s", title);
    snprintf(p->arg, sizeof p->arg, "%s", arg ? arg : "");
    load_page(p);
}

static void ui_close(void)
{
    active = 0;
    unlink(FLAG);
    if (higv_addr) refresh_surface(higv_addr, higv_w, higv_h, higv_pitch);
    logf_("geschlossen");
}

static void ui_open(void)
{
    remember_higv();
    int fd = open(FLAG, O_CREAT | O_WRONLY, 0644);
    if (fd >= 0) close(fd);
    active = 1;
    depth = 0;
    memset(&stack[0], 0, sizeof stack[0]);
    stack[0].kind = P_MAIN;
    strcpy(stack[0].title, "Einstellungen");
    load_page(&stack[0]);
    draw();
    logf_("geöffnet");
}

static void open_system_settings(void)
{
    ui_close();
    int fd = open(SYSSET, O_CREAT | O_WRONLY, 0644);
    if (fd >= 0) close(fd);
    usleep(100000);
    cgi("sendclickkey.cgi?-act=set&-type=L1");   /* main_app: hook_long_wifi -> Original-Liste */
}

static void on_ok(void)
{
    struct page *p = &stack[depth];
    struct rowd *d = &p->r[p->sel];
    switch (p->kind) {
    case P_MAIN:
        if (p->sel == 0) push(P_MODES, "Modus", 0);
        else if (p->sel == 1) push(P_ITEMS, de(cur_mode), 0);
        else if (p->sel == 2) push(P_CONN, "Verbindungen", 0);
        else { open_system_settings(); return; }
        break;
    case P_MODES:
        cgi("setcurworkmode.cgi?-act=set&-workmode=%s", d->key);
        snprintf(cur_mode, sizeof cur_mode, "%s", d->key);
        depth--;
        load_page(&stack[depth]);
        break;
    case P_ITEMS:
        push(P_OPTIONS, d->label, d->key);
        break;
    case P_OPTIONS:
        cgi("setcurparameter.cgi?-act=set&-workmode=%s&-name=%s&-value=%s", cur_mode, p->arg, d->key);
        depth--;
        load_page(&stack[depth]);
        break;
    case P_CONN: {
        char cmd[64];
        snprintf(cmd, sizeof cmd, "/app/hack/menu.sh toggle %d", p->sel);
        system(cmd);
        load_page(p);
        break;
    }
    }
    draw();
}

static void on_key(uint32_t k)
{
    struct page *p = &stack[depth];
    if (k == KEY_DOWN) { p->sel = (p->sel + 1) % (p->n ? p->n : 1); draw(); }
    else if (k == KEY_UP) { p->sel = (p->sel + (p->n ? p->n : 1) - 1) % (p->n ? p->n : 1); draw(); }
    else if (k == KEY_OK) on_ok();
    else if (k == KEY_BACK) {
        if (depth == 0) ui_close();
        else { depth--; load_page(&stack[depth]); draw(); }
    } else if (k == KEY_WIFI_LONG) ui_close();
}

int main(int argc, char **argv)
{
    if (argc > 1 && !strcmp(argv[1], "--demo")) {     /* Testbild ohne main_app-Anbindung */
        if (load_font() || fb_init()) return 1;
        ui_open();
        sleep(argc > 2 ? atoi(argv[2]) : 5);
        ui_close();
        return 0;
    }
    if (load_font()) { logf_("Schrift fehlt"); return 1; }
    if (fb_init()) { logf_("fb0 nicht verfügbar"); return 1; }
    unlink(FLAG);
    mkfifo(FIFO, 0600);
    int fd = open(FIFO, O_RDWR);                         /* O_RDWR: kein EOF ohne Schreiber */
    if (fd < 0) { logf_("FIFO: %s", strerror(errno)); return 1; }
    logf_("ctui bereit");
    time_t last = 0;
    for (;;) {
        struct pollfd pf = {.fd = fd, .events = POLLIN};
        if (poll(&pf, 1, 1000) <= 0) {
            /* Sicherheit: nach 60 s ohne Taste schließen (Tasten gehen sonst nur an ctui) */
            if (active && time(0) - last > 60) ui_close();
            continue;
        }
        uint32_t m;
        if (read(fd, &m, 4) != 4) continue;
        last = time(0);
        if (m == UI_OPEN) { if (!active) ui_open(); }
        else if (active) on_key(m);
    }
}
