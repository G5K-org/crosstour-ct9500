#!/usr/bin/env python3
"""Screenshot vom CT9500-Display (Framebuffer /dev/fb0, 240x320, 16 bpp) als PNG.

  tools/screenshot.py ausgabe.png [--rotate]
Liest das Bild per Telnet + kleinem HTTP-Server auf der Kamera (Port 8083).
"""
import os, struct, sys, urllib.request, zlib
sys.path.insert(0, os.path.dirname(__file__))
from camsh import run

HOST = os.environ.get("CT9500_HOST", "192.168.0.1")
W, H = 240, 320


def png(path, w, h, rgb):
    raw = b"".join(b"\x00" + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h))
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "screen.png"
    run("mkdir -p /dev/ct9500mod/shot; dd if=/dev/fb0 of=/dev/ct9500mod/shot/fb.raw bs=153600 count=1 2>/dev/null; "
        "grep -q 8083 /proc/net/tcp 2>/dev/null; netstat -tln | grep -q ':8083 ' || /app/hack/busybox httpd -p 8083 -h /dev/ct9500mod/shot", host=HOST)
    d = urllib.request.urlopen(f"http://{HOST}:8083/fb.raw", timeout=10).read()
    # Format ermitteln: ARGB1555 (HiFB-Standard) oder RGB565
    fmt = os.environ.get("FBFMT", "argb1555")
    rgb = bytearray()
    for i in range(0, W * H * 2, 2):
        v = d[i] | d[i + 1] << 8
        if fmt == "rgb565":
            r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
            rgb += bytes((r * 255 // 31, g * 255 // 63, b * 255 // 31))
        else:
            r, g, b = (v >> 10) & 31, (v >> 5) & 31, v & 31
            rgb += bytes((r * 255 // 31, g * 255 // 31, b * 255 // 31))
    if "--rotate" in sys.argv:   # 90° drehen (Display ist im Querformat montiert)
        rot = bytearray(len(rgb))
        for y in range(H):
            for x in range(W):
                s = (y * W + x) * 3
                nx, ny = y, W - 1 - x
                t = (ny * H + nx) * 3
                rot[t:t + 3] = rgb[s:s + 3]
        png(out, H, W, bytes(rot))
    else:
        png(out, W, H, bytes(rgb))
    print(out)


if __name__ == "__main__":
    main()
