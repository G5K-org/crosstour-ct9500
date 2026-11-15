#!/usr/bin/env python3
"""Erzeugt die Qualitätsstufen für den Livestream (venc.1 / vpss.0.vport.1).

Für jede Stufe werden die Mediamode-INIs angepasst, auf der Kamera mit dem
Original-Werkzeug ini2bin_board zu param.bin übersetzt und die Byte-Unterschiede
zur Basis als Patch-Datei gespeichert (mod/appfs/hack/stream/<stufe>.patch).
Format pro Zeile: "<dezimaler Offset in param.bin> <Hex-Bytes>".

Voraussetzung: PC im Kamera-WLAN, Telnet aktiv.
"""
import io, os, re, shutil, sys, tarfile, threading, http.server, functools, urllib.request
sys.path.insert(0, os.path.dirname(__file__))
from camsh import run

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "build", "param")            # Basis = unsere Standardwerte (M3)
OUT = os.path.join(ROOT, "mod", "appfs", "hack", "stream")
WORK = os.path.join(ROOT, "build", "presets")
PC_IP, PORT = "192.168.0.20", 8013

# Stufe -> (Breite, Höhe, kbit/s)
PRESETS = {
    "std":  (1024, 576, 2048),
    "high": (1280, 720, 5000),
    "max":  (1920, 1080, 10000),
}
OLD_POOL = 898560   # 1024*576*1.5 + 576*24


def pool_size(w, h):
    return w * h * 3 // 2 + h * 24


def setkey(text, section, key, value):
    """Wert in [section] ersetzen (Kommentar dahinter bleibt)."""
    pat = re.compile(rf'(^\[{re.escape(section)}\][^\[]*?^{key}\s*=\s*")[^"]*(")', re.M | re.S)
    new, n = pat.subn(rf'\g<1>{value}\g<2>', text, count=1)
    return new, n


def make_preset(name, w, h, kbps):
    d = os.path.join(WORK, name, "param")
    shutil.rmtree(os.path.join(WORK, name), ignore_errors=True)
    shutil.copytree(BASE, d)
    for f in sorted(os.listdir(d)):
        if not f.startswith("config_product_mediamode_") or not f.endswith(".ini"):
            continue
        p = os.path.join(d, f)
        t = open(p, encoding="latin-1").read()
        if not re.search(r'^\[venc\.1\][^\[]*res_width\s*=\s*"1024"', t, re.M | re.S):
            continue
        # Hauptauflösung des Modus: Vorschau nie größer als die Aufnahme
        mw = int(re.search(r'^\[venc\.0\][^\[]*?res_width\s*=\s*"(\d+)"', t, re.M | re.S).group(1))
        mh = int(re.search(r'^\[venc\.0\][^\[]*?res_height\s*=\s*"(\d+)"', t, re.M | re.S).group(1))
        if w <= mw and h <= mh:
            pw, ph = w, h
        elif mw >= 1024 and mh >= 576:
            pw, ph = mw, mh          # z.B. 720p-Modi: Vorschau = Aufnahmeauflösung
        else:
            pw, ph = 1024, 576
        changes = 0
        for sec in ("vpss.0.vport.1", "venc.1"):
            for k, v in (("res_width", pw), ("res_height", ph)):
                t, n = setkey(t, sec, k, v); changes += n
        for k in ("h264bitrate", "h265bitrate"):
            t, n = setkey(t, "venc.1", k, kbps); changes += n
        if (pw, ph) != (1024, 576):   # sonst Originalpuffer lassen (manche Modi weichen ab)
            t, n = setkey(t, "venc.1", "bufsize", pw * ph * 2); changes += n
        # Pool des Vorschau-Kanals vergrößern
        t, n = re.subn(rf'(blk_size\s*=\s*"){OLD_POOL}(")', rf'\g<1>{max(OLD_POOL, pool_size(pw, ph))}\g<2>', t)
        changes += n
        open(p, "w", encoding="latin-1").write(t)
        print(f"  {name}: {f} -> {pw}x{ph} {kbps}kbps ({changes} Werte)")


def serve(directory):
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
    h.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer((PC_IP, PORT), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main():
    if not os.path.isdir(BASE):
        sys.exit("build/param fehlt (Basis-INIs)")
    shutil.copy(os.path.join(ROOT, "firmware/fs/appfs/param/ini2bin_board"), os.path.join(BASE, "ini2bin_board"))
    for name, (w, h, k) in PRESETS.items():
        make_preset(name, w, h, k)
    tar = os.path.join(WORK, "presets.tar")
    with tarfile.open(tar, "w") as t:
        for name in PRESETS:
            t.add(os.path.join(WORK, name), arcname=name)
    srv = serve(WORK)
    names = " ".join(PRESETS)
    out, rc = run(f"""cd /; mkdir -p /tmp/mod; grep -q " /tmp/mod " /proc/mounts || mount -t tmpfs -o size=8m tmpfs /tmp/mod
cd /tmp/mod && rm -rf presets && mkdir presets && cd presets && wget -q -O p.tar http://{PC_IP}:{PORT}/presets.tar && tar xf p.tar && rm p.tar
for n in {names}; do (cd $n/param && rm -f param.bin paramdef.bin && chmod +x ini2bin_board && LD_LIBRARY_PATH=/app/lib ./ini2bin_board >/dev/null 2>&1 && ls -la param.bin); done
mkdir -p /app/sd/CT9500MOD/presets; for n in {names}; do cp $n/param/param.bin /app/sd/CT9500MOD/presets/$n.bin; done; sync; echo FERTIG""", timeout=120)
    srv.shutdown()
    if "FERTIG" not in out:
        sys.exit("Fehler auf der Kamera:\n" + out)
    bins = {}
    for n in PRESETS:
        bins[n] = urllib.request.urlopen(f"http://192.168.0.1/sd/CT9500MOD/presets/{n}.bin", timeout=20).read()
        print(f"{n}: {len(bins[n])} Bytes")
    base = open(os.path.join(ROOT, "mod/appfs/param/param.bin"), "rb").read()
    os.makedirs(OUT, exist_ok=True)
    ref = bins["std"]
    if base and ref != base:
        print("WARNUNG: std-Stufe weicht von der Basis ab")
    # Alle Offsets, an denen sich irgendeine Stufe unterscheidet
    offs = sorted({i for n in PRESETS for i in range(len(ref)) if bins[n][i] != ref[i]})
    # zu zusammenhängenden Bereichen gruppieren (4-Byte-ausgerichtet, ganze Werte)
    ranges = []
    for o in offs:
        a = o & ~3
        if ranges and a <= ranges[-1][1]:
            ranges[-1][1] = max(ranges[-1][1], a + 4)
        else:
            ranges.append([a, a + 4])
    for n in PRESETS:
        with open(os.path.join(OUT, f"{n}.patch"), "w") as f:
            for a, b in ranges:
                f.write(f"{a} {bins[n][a:b].hex()}\n")
    print(f"{len(offs)} Bytes in {len(ranges)} Bereichen unterscheiden sich; Patches in {OUT}")


if __name__ == "__main__":
    main()
