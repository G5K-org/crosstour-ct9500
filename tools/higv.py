#!/usr/bin/env python3
"""HiGV-Oberflächendatei (bin/higv.bin) der CT9500 lesen.

Datei: Kopf mit (Offset, Größe)-Paaren ab 0x54, Offsets relativ zu 0x50.
Abschnitt S4 (Fenster): u32 Anzahl, Anzahl x (ID, Offset, Größe), dann Fensterdaten.
Fenster: 12 Byte Kopf, dann Datensätze (Parser_VParser_SigleView):
  u32 Gesamtlänge | u32 lenB | u32 lenA(Low-Byte) | A (lenA) | B (lenB, auf 4) | Rest (Grunddaten)
  Grunddaten (u32): Typ, ID, x, y, w, h, Eltern-ID, ...

  tools/higv.py views
  tools/higv.py widgets <view-id>
"""
import struct, sys

BASE = 0x50


class Higv:
    def __init__(self, path):
        self.d = bytearray(open(path, "rb").read())
        h = struct.unpack_from("<12I", self.d, 0x54)
        self.sections = [(h[0], h[1]), (h[2], h[3]), (h[4], h[5]), (h[6], h[7]), (h[8], h[9])]
        # Achtung: Reihenfolge laut Kopf: (0x38,0x134),(0x16c,0x5b00),(0x5c6c,0x2e0),(0x5f4c,0x118b0),(0x177fc,0x3fbc)
        self.views_off = BASE + 0x5f4c

    def views(self):
        a = self.views_off
        n = struct.unpack_from("<I", self.d, a)[0]
        data = a + 4 + 12 * n
        return [(vid, data + off, size) for vid, off, size in (struct.unpack_from("<3I", self.d, a + 4 + 12 * i) for i in range(n))]

    def records(self, vid):
        for v, start, size in self.views():
            if v == vid:
                break
        else:
            raise KeyError(vid)
        p, end = start + 12, start + size
        while p < end:
            tot, lenb, lena = struct.unpack_from("<3I", self.d, p)
            lena &= 0xFF
            a = p + 12
            b = a + lena
            c = b + ((lenb + 3) & ~3)
            core = struct.unpack_from(f"<{(p + tot - c) // 4}I", self.d, c)
            yield dict(pos=p, tot=tot, A=bytes(self.d[a:b]), B=bytes(self.d[b:b + lenb]), core=core, core_pos=c)
            p += tot


if __name__ == "__main__":
    g = Higv(sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].isdigit() else "firmware/fs/appfs/bin/higv.bin")
    if sys.argv[1] == "views":
        for v, s, n in g.views():
            print(v, hex(s), n)
    elif sys.argv[1] == "widgets":
        for r in g.records(int(sys.argv[2])):
            c = r["core"]
            print(f"@{r['pos']:#07x} len{r['tot']:4} typ{c[0]:3} id{c[1]:5} xywh({c[2]},{c[3]},{c[4]},{c[5]}) par{c[6]:5} "
                  f"rest {' '.join(f'{x:x}' for x in c[7:16])} | A {r['A'].hex()} | B {r['B'].hex()}")
