/*
 * rtsp2h264 - holt einen H.264-RTSP-Stream (RTP über TCP, interleaved) und gibt
 * ihn als H.264-Elementarstrom (Annex B) auf stdout aus. Für die Live-Vorschau
 * der CT9500-Weboberfläche (busybox httpd CGI).
 *
 *   rtsp2h264 [-c] [host] [port] [pfad]
 *     -c   vorher CGI-Header ausgeben
 *   Standard: 127.0.0.1 554 /livestream/12
 *
 * Unterstützt RTP-Pakettypen Single NAL, STAP-A und FU-A (RFC 6184).
 * Beendet sich, sobald stdout nicht mehr beschreibbar ist (Browser weg).
 */
#include <arpa/inet.h>
#include <errno.h>
#include <netdb.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

static int sock = -1, cseq = 0;
static char session[128] = "";
static char url[256];

static void die(const char *msg) {
    fprintf(stderr, "rtsp2h264: %s\n", msg);
    exit(1);
}

static int write_all(int fd, const void *buf, size_t len) {
    const uint8_t *p = buf;
    while (len) {
        ssize_t n = write(fd, p, len);
        if (n < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        p += n; len -= (size_t)n;
    }
    return 0;
}

static int read_all(void *buf, size_t len) {
    uint8_t *p = buf;
    while (len) {
        ssize_t n = recv(sock, p, len, 0);
        if (n <= 0) {
            if (n < 0 && errno == EINTR) continue;
            return -1;
        }
        p += n; len -= (size_t)n;
    }
    return 0;
}

/* RTSP-Anfrage senden und Antwort (Header + Body) lesen */
static int rtsp(const char *method, const char *uri, const char *extra, char *resp, size_t rsize) {
    char req[1024];
    int n = snprintf(req, sizeof req, "%s %s RTSP/1.0\r\nCSeq: %d\r\nUser-Agent: ct9500mod\r\n%s%s%s%s\r\n",
                     method, uri, ++cseq, session[0] ? "Session: " : "", session, session[0] ? "\r\n" : "",
                     extra ? extra : "");
    if (write_all(sock, req, (size_t)n)) return -1;
    size_t len = 0;
    char *body;
    for (;;) {   /* bis Header-Ende lesen; eventuell vorab gelieferte RTP-Daten ignorieren wir nicht: PLAY kommt zuletzt */
        if (len + 1 >= rsize) return -1;
        ssize_t r = recv(sock, resp + len, 1, 0);
        if (r <= 0) return -1;
        len++;
        resp[len] = 0;
        if ((body = strstr(resp, "\r\n\r\n"))) break;
    }
    body += 4;
    char *cl = strcasestr(resp, "Content-Length:");
    if (cl) {
        size_t blen = (size_t)atoi(cl + 15);
        if ((size_t)(body - resp) + blen + 1 > rsize) return -1;
        if (read_all(body, blen)) return -1;
        body[blen] = 0;
    }
    char *s = strcasestr(resp, "Session:");
    if (s) {
        s += 8;
        while (*s == ' ') s++;
        size_t i = 0;
        while (s[i] && s[i] != ';' && s[i] != '\r' && i < sizeof session - 1) { session[i] = s[i]; i++; }
        session[i] = 0;
    }
    return strncmp(resp, "RTSP/1.0 200", 12) == 0 ? 0 : -1;
}

static int b64val(int c) {
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= 'a' && c <= 'z') return c - 'a' + 26;
    if (c >= '0' && c <= '9') return c - '0' + 52;
    if (c == '+') return 62;
    if (c == '/') return 63;
    return -1;
}

static size_t b64dec(const char *in, size_t inlen, uint8_t *out) {
    size_t o = 0; int bits = 0; uint32_t acc = 0;
    for (size_t i = 0; i < inlen; i++) {
        int v = b64val((unsigned char)in[i]);
        if (v < 0) continue;
        acc = (acc << 6) | (uint32_t)v; bits += 6;
        if (bits >= 8) { bits -= 8; out[o++] = (uint8_t)(acc >> bits); }
    }
    return o;
}

static const uint8_t SC[4] = {0, 0, 0, 1};

static void out_nal(const uint8_t *p, size_t len) {
    if (write_all(1, SC, 4) || write_all(1, p, len)) exit(0);   /* Browser hat Verbindung beendet */
}

int main(int argc, char **argv) {
    int cgi = 0, ai = 1;
    if (argc > 1 && !strcmp(argv[1], "-c")) { cgi = 1; ai++; }
    const char *host = argc > ai ? argv[ai] : "127.0.0.1";
    const char *port = argc > ai + 1 ? argv[ai + 1] : "554";
    const char *path = argc > ai + 2 ? argv[ai + 2] : "/livestream/12";
    signal(SIGPIPE, SIG_IGN);

    struct addrinfo hints = {0}, *ai_res;
    hints.ai_socktype = SOCK_STREAM;
    if (getaddrinfo(host, port, &hints, &ai_res)) die("Adresse ungültig");
    sock = socket(ai_res->ai_family, SOCK_STREAM, 0);
    if (sock < 0 || connect(sock, ai_res->ai_addr, ai_res->ai_addrlen)) die("keine Verbindung zum RTSP-Server");
    struct timeval tv = {10, 0};
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
    snprintf(url, sizeof url, "rtsp://%s:%s%s", host, port, path);

    static char resp[8192];
    if (rtsp("DESCRIBE", url, "Accept: application/sdp\r\n", resp, sizeof resp)) die("DESCRIBE fehlgeschlagen");

    /* SPS/PPS aus dem SDP */
    static uint8_t ps[2][512];
    size_t pslen[2] = {0, 0};
    char *sp = strstr(resp, "sprop-parameter-sets=");
    if (sp) {
        sp += 21;
        char *end = sp + strcspn(sp, ";\r\n ");
        char *comma = memchr(sp, ',', (size_t)(end - sp));
        if (comma) {
            pslen[0] = b64dec(sp, (size_t)(comma - sp), ps[0]);
            pslen[1] = b64dec(comma + 1, (size_t)(end - comma - 1), ps[1]);
        }
    }
    /* Track-URL */
    char track[256] = "trackID=0";
    char *ctl = strstr(resp, "m=video");
    if (ctl && (ctl = strstr(ctl, "a=control:"))) {
        ctl += 10;
        size_t l = strcspn(ctl, "\r\n");
        if (l < sizeof track) { memcpy(track, ctl, l); track[l] = 0; }
    }
    char turl[600];
    if (!strncmp(track, "rtsp://", 7)) snprintf(turl, sizeof turl, "%s", track);
    else snprintf(turl, sizeof turl, "%s/%s", url, track);

    if (rtsp("SETUP", turl, "Transport: RTP/AVP/TCP;unicast;interleaved=0-1\r\n", resp, sizeof resp)) die("SETUP fehlgeschlagen");
    if (rtsp("PLAY", url, "Range: npt=0.000-\r\n", resp, sizeof resp)) die("PLAY fehlgeschlagen");

    if (cgi) {
        const char *h = "Content-Type: video/h264\r\nCache-Control: no-store\r\n\r\n";
        if (write_all(1, h, strlen(h))) return 0;
    }
    if (pslen[0]) out_nal(ps[0], pslen[0]);
    if (pslen[1]) out_nal(ps[1], pslen[1]);

    static uint8_t pkt[65536 + 4], fu[2 * 1024 * 1024];
    size_t fulen = 0;
    time_t last_ka = time(NULL);
    for (;;) {
        uint8_t hdr[4];
        if (read_all(hdr, 1)) die("Verbindung verloren");
        if (hdr[0] != '$') continue;          /* RTSP-Antworten (z.B. auf GET_PARAMETER) überspringen */
        if (read_all(hdr + 1, 3)) die("Verbindung verloren");
        size_t len = ((size_t)hdr[2] << 8) | hdr[3];
        if (read_all(pkt, len)) die("Verbindung verloren");

        if (time(NULL) - last_ka > 20) {      /* Sitzung am Leben halten */
            char ka[256];
            int n = snprintf(ka, sizeof ka, "GET_PARAMETER %s RTSP/1.0\r\nCSeq: %d\r\nSession: %s\r\n\r\n", url, ++cseq, session);
            write_all(sock, ka, (size_t)n);
            last_ka = time(NULL);
        }
        if (hdr[1] != 0 || len < 12) continue;       /* nur RTP-Kanal 0 */

        size_t off = 12 + (size_t)(pkt[0] & 0x0f) * 4;
        if (pkt[0] & 0x10) {                          /* Header-Erweiterung */
            if (off + 4 > len) continue;
            off += 4 + (((size_t)pkt[off + 2] << 8) | pkt[off + 3]) * 4;
        }
        size_t end = len;
        if (pkt[0] & 0x20) end -= pkt[len - 1];       /* Padding */
        if (off >= end) continue;
        uint8_t *p = pkt + off;
        size_t pl = end - off;
        int type = p[0] & 0x1f;

        if (type >= 1 && type <= 23) {
            out_nal(p, pl);
        } else if (type == 24) {                      /* STAP-A */
            size_t i = 1;
            while (i + 2 <= pl) {
                size_t nl = ((size_t)p[i] << 8) | p[i + 1];
                i += 2;
                if (i + nl > pl) break;
                out_nal(p + i, nl);
                i += nl;
            }
        } else if (type == 28 && pl > 2) {            /* FU-A */
            int start = p[1] & 0x80, stop = p[1] & 0x40;
            if (start) {
                fu[0] = (uint8_t)((p[0] & 0xe0) | (p[1] & 0x1f));
                fulen = 1;
            }
            if (fulen && fulen + pl - 2 < sizeof fu) {
                memcpy(fu + fulen, p + 2, pl - 2);
                fulen += pl - 2;
            } else {
                fulen = 0;
            }
            if (stop && fulen) {
                out_nal(fu, fulen);
                fulen = 0;
            }
        }
    }
}
