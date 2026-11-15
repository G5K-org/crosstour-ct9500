#!/usr/bin/env python3
"""Optik der CT9500-Oberfläche (higv.bin): Schriften und Farben.

Abschnitt S0 (Schriften, ab BASE+0x38): Einträge zu 7 u32
  (ID, Pfad-Ref, ?, Größe, Fett, 0, 0); Pfad-Ref = Offset im String-Pool (S5).
Abschnitt S1 (Skins, ab BASE+0x16c): Einträge zu 14 u32
  (ID, Typ, Rand x8, Hintergrund, Vordergrund, ?, ?); Typ 0 = Farbe (ARGB), 1 = Bild.
"""
import re, struct
from langfile import crc_mpeg2

BASE = 0x50


def _secs(d):
    h = struct.unpack_from("<12I", d, 0x54)
    return [(BASE + h[i], h[i + 1]) for i in range(0, 10, 2)]


def _pool(d):
    po, ps = _secs(d)[4]
    return po, bytes(d[po:po + ps])


def fonts(d):
    o, sz = _secs(d)[0]
    po, pool = _pool(d)
    out = []
    for i in range(sz // 28):
        w = list(struct.unpack_from("<7I", d, o + 28 * i))
        e = pool.find(b"\0", w[1])
        out.append((o + 28 * i, w, pool[w[1]:e].decode()))
    return out


# Nur Schriften mit deckendem Hintergrund (Menüs). Die Statusleisten (Schrift 40/44) liegen
# halbtransparent über der Startseite; geglättete TrueType-Kanten lassen dort beim Wechsel
# (z. B. Wiedergabe) alte Texte durchscheinen -> dort bleibt die Bitmap-Schrift.
VECTOR_FONT_IDS = (29, 41)


def bitmap_fonts_to_vector(d, ids=VECTOR_FONT_IDS):
    """Bitmap-Schriften (*.ubf) mit den IDs ids auf res/font/vector.ttf umlenken."""
    d = bytearray(d)
    fl = fonts(d)
    vec = next(w[1] for _, w, p in fl if p.endswith("vector.ttf"))
    changed = []
    for off, w, p in fl:
        if ".ubf" in p and w[0] in ids:
            # Bitmap-Größe steht im Dateinamen (PF14/PF16); die eingetragene Größe (z. B. 20
            # bei Schrift 44) passt als TrueType nicht in die 20 px hohen Felder -> unsichtbar
            px = int(re.search(r"PF(\d+)", p).group(1))
            struct.pack_into("<I", d, off + 4, vec)
            struct.pack_into("<I", d, off + 12, px)
            changed.append((w[0], px))
    return d, changed


def recolor(d, mapping):
    """Farb-Skins umfärben: mapping {alte ARGB: neue ARGB} für Hintergrund/Vordergrund/Rand."""
    d = bytearray(d)
    o, sz = _secs(d)[1]
    n = 0
    for i in range(sz // 56):
        a = o + 56 * i
        r = list(struct.unpack_from("<14I", d, a))
        if r[1] != 0:
            continue
        new = [mapping.get(v, v) if 2 <= k <= 11 else v for k, v in enumerate(r)]
        if new != r:
            struct.pack_into("<14I", d, a, *new)
            n += 1
    return d, n


def fix_crc(d):
    struct.pack_into("<I", d, 0, crc_mpeg2(bytes(d[4:])))
    return d


# ---------------------------------------------------------------- Akzentfarbe (Bilder)
OLD_ACCENT = (6, 69, 234)        # Original-Blau #0645EA (auf Schwarz schlecht lesbar)
NEW_ACCENT = (10, 132, 255)      # Akzentblau #0A84FF


def recolor_png(data, old=OLD_ACCENT, new=NEW_ACCENT, tol=40):
    """Pixel nahe der alten Akzentfarbe auf die neue setzen (Alpha bleibt). Gibt PNG-Bytes
    zurück oder None, wenn nichts zu ändern war."""
    import io
    from PIL import Image
    im = Image.open(io.BytesIO(data))
    mode = im.mode
    im = im.convert("RGBA")
    px = im.load()
    n = 0
    for y in range(im.size[1]):
        for x in range(im.size[0]):
            r, g, b, a = px[x, y]
            if a and abs(r - old[0]) + abs(g - old[1]) + abs(b - old[2]) <= tol:
                px[x, y] = (*new, a)
                n += 1
    if not n:
        return None
    out = io.BytesIO()
    im.save(out, "PNG", optimize=True)
    return out.getvalue()


def accent_argb(c):
    return 0xFF000000 | (c[0] << 16) | (c[1] << 8) | c[2]
