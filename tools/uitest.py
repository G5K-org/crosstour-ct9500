#!/usr/bin/env python3
"""Automatische UI-Tests an der CT9500 (über USB-Debug oder WLAN).

  .venv/bin/python tools/uitest.py <name> <schritt> [schritt ...]
Schritte: Taste (K0..K3, L1..L3) mit optionaler Wartezeit "K3:2", "shot" = Screenshot,
"open" = Einstellungen per Schnellzugriff öffnen (wiederholt, bis das Menü sichtbar ist).
Screenshots: <scratch>/<name>_<n>.png und eine Übersicht <name>_all.png.
Sicherheit: L0 (lang Modus = Ausschalten) wird verweigert; Tasten werden erst gesendet, wenn
die Kamera auf Tasten reagiert (kurz nach dem Start ignoriert main_app sie).
"""
import os, subprocess, sys, time, urllib.request
from PIL import Image

HOST = os.environ.get("CT9500_HOST", "192.168.7.1")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.environ.get("UITEST_OUT", "/tmp")


def key(t):
    if t.upper() == "L0":
        raise SystemExit("L0 verweigert (Ausschalten)")
    urllib.request.urlopen(f"http://{HOST}/cgi-bin/hi3510/sendclickkey.cgi?-act=set&-type={t}", timeout=5).read()


def shot(path):
    subprocess.run([sys.executable, os.path.join(ROOT, "tools/screenshot.py"), path, "--rotate"],
                   env=dict(os.environ, CT9500_HOST=HOST), check=True, capture_output=True)
    return Image.open(path).convert("RGB")


def is_home(im):
    """Startseite: untere Leiste (y 222..239) dunkelgrau mit Text, Mitte schwarz (Video)."""
    mid = im.crop((60, 80, 260, 160)).getextrema()
    return all(hi < 20 for _, hi in mid)


def main():
    name, steps = sys.argv[1], sys.argv[2:]
    shots = []
    for st in steps:
        t, _, w = st.partition(":")
        wait = float(w or 2)
        if t == "shot":
            p = os.path.join(OUT, f"{name}_{len(shots) + 1}.png")
            shot(p)
            shots.append(p)
            print("shot", p)
        elif t == "open":
            for attempt in range(8):
                key("L1")
                time.sleep(3)
                if not is_home(shot(os.path.join(OUT, f"{name}_probe.png"))):
                    print(f"Menü offen (Versuch {attempt + 1})")
                    break
                time.sleep(5)
            else:
                raise SystemExit("Menü ging nicht auf")
        else:
            key(t)
            time.sleep(wait)
    if shots:
        ims = [Image.open(p) for p in shots]
        w, h = ims[0].size
        cols = min(3, len(ims))
        rows = (len(ims) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * w + (cols - 1) * 10, rows * h + (rows - 1) * 10), "white")
        for i, im in enumerate(ims):
            sheet.paste(im, ((i % cols) * (w + 10), (i // cols) * (h + 10)))
        sheet.save(os.path.join(OUT, f"{name}_all.png"))
        print("Übersicht", os.path.join(OUT, f"{name}_all.png"))


if __name__ == "__main__":
    main()
