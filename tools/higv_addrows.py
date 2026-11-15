#!/usr/bin/env python3
"""Neue Zeilen im Einstellungsfenster (View 564, SYSTEM_SET) der CT9500 hinzufügen.

Klont die Vorlage-Zeile 21 ("Datumsanzeige": Button 631, Label 632, Wert 633) und hängt
die neuen Zeilen hinter die letzte Zeile (Version, ID 653/654) an.

Datei-Aufbau siehe tools/higv.py. Geändert werden:
  - View 564: 3 Datensätze je neuer Zeile eingefügt
  - View-Tabelle: Größe View 564, Offsets aller späteren Views
  - Kopf: Größe S4 (0x70), Offset/Größe S5 (0x74/0x78), Ende (0x7C),
          Handle-Grenzen (0x48 Klon-Start, 0x50 max. vergebenes Handle)
  - String-Pool S5: neue Texte "<Sprachindex>" angehängt
  - CRC-32/MPEG-2 ab Byte 4
"""
import struct, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from higv import Higv, BASE
from langfile import crc_mpeg2

VIEW = 564
TEMPLATE = (631, 632, 633)       # Datumsanzeige: Button, Label, Wert
LAST_ROW_LABEL = 654             # danach beginnen die Popups (655)
ROW_STEP = 40
WIFI_ICON = (0x210, 0x20F, 0x20F)  # Icons aus Zeile "WLAN"


def skin_by_file(src, fname):
    """Skin-ID eines Bild-Skins anhand des Dateinamens (z. B. "wifi_select.png")."""
    g = Higv(src)
    d = g.d
    h = struct.unpack_from("<12I", d, 0x54)
    po, ps = BASE + h[8], h[9]
    pool = bytes(d[po:po + ps])
    o, sz = BASE + h[2], h[3]
    for i in range(sz // 56):
        r = struct.unpack_from("<14I", d, o + 56 * i)
        if r[1] == 1:
            e = pool.find(b"\0", r[10])
            if pool[r[10]:e].decode(errors="replace").endswith("/" + fname):
                return r[0]
    raise KeyError(fname)


def icon_of(src, name):
    """(normal, aktiv, aktiv) für <name>_no_select.png / <name>_select.png"""
    a = skin_by_file(src, name + "_select.png")
    return (skin_by_file(src, name + "_no_select.png"), a, a)


def add_rows(src, rows):
    """rows: Liste von (lang_index, icon_tuple oder None). Gibt (bytes, [(btn, label, value)]) zurück."""
    g = Higv(src)
    d = bytearray(g.d)
    h = list(struct.unpack_from("<16I", d, 0x48))
    max_handle = h[2]                      # 0x50
    s4_off, s4_size, s5_off, s5_size, end = h[9], h[10], h[11], h[12], h[13]
    assert s4_off == 0x5F4C and s5_off == s4_off + s4_size and end == s5_off + s5_size

    recs = list(g.records(VIEW))
    byid = {r["core"][1]: r for r in recs}
    tpl = [byid[i] for i in TEMPLATE]
    last_y = max(r["core"][3] for r in recs if r["core"][0] == 2 and 569 <= r["core"][1] <= 653)
    insert_at = byid[LAST_ROW_LABEL]["pos"] + byid[LAST_ROW_LABEL]["tot"]
    assert byid[655]["pos"] == insert_at

    pool_abs = BASE + s5_off
    pool = bytearray(d[pool_abs:pool_abs + s5_size])
    new_handles, blob = [], bytearray()
    nid = max_handle + 1
    for n, (lang_idx, icon) in enumerate(rows):
        y = last_y + ROW_STEP * (n + 1)
        text_ref = len(pool)
        pool += str(lang_idx).encode() + b"\0"
        ids = (nid, nid + 1, nid + 2)
        nid += 3
        for k, t in enumerate(tpl):
            raw = bytearray(d[t["pos"]:t["pos"] + t["tot"]])
            core_off = t["core_pos"] - t["pos"]
            def setw(i, v):
                struct.pack_into("<I", raw, core_off + 4 * i, v)
            setw(1, ids[k])
            setw(3, y)
            if k == 0 and icon:
                setw(8, icon[0]); setw(9, icon[1]); setw(10, icon[2])
            if k == 1:
                setw(9, text_ref)          # Label-Text -> "<lang_idx>"
            blob += raw
        new_handles.append(ids)

    delta, pdelta = len(blob), len(pool) - s5_size
    # View-Daten einfügen
    d[insert_at:insert_at] = blob
    # View-Tabelle anpassen
    vt = BASE + s4_off
    nviews = struct.unpack_from("<I", d, vt)[0]
    v564_off = None
    for i in range(nviews):
        e = vt + 4 + 12 * i
        vid, off, size = struct.unpack_from("<3I", d, e)
        if vid == VIEW:
            v564_off = off
            struct.pack_into("<3I", d, e, vid, off, size + delta)
    for i in range(nviews):
        e = vt + 4 + 12 * i
        vid, off, size = struct.unpack_from("<3I", d, e)
        if off > v564_off:
            struct.pack_into("<3I", d, e, vid, off + delta, size)
    # String-Pool (letzter Abschnitt, liegt am Dateiende) ersetzen
    pool_abs += delta
    d[pool_abs:pool_abs + s5_size] = pool
    # Kopf
    h[0] = nid                 # 0x48: Start der Klon-Handles
    h[2] = nid - 1             # 0x50: höchstes vergebenes Handle
    h[10] = s4_size + delta    # 0x70
    h[11] = s5_off + delta     # 0x74
    h[12] = s5_size + pdelta   # 0x78
    h[13] = end + delta + pdelta  # 0x7C
    struct.pack_into("<16I", d, 0x48, *h)
    struct.pack_into("<I", d, 0, crc_mpeg2(bytes(d[4:])))
    return bytes(d), new_handles


if __name__ == "__main__":
    out, handles = add_rows(sys.argv[1], [(470, WIFI_ICON), (471, WIFI_ICON), (472, None)])
    open(sys.argv[2], "wb").write(out)
    print("neue Handles:", handles)
