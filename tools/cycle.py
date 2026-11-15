#!/usr/bin/env python3
"""rawparam-Ringspeicher ("Cycle") so lesen wie u-boot (Cycle_Get_InitData / cread).

  tools/cycle.py image.bin [vergleich.patch ...]
Gibt alle Einträge aus, prüft Magics/Längen wie der Bootloader, entpackt den
letzten gültigen Eintrag und prüft die param.bin-Magics (arap/mrap wie main_app).
"""
import struct, sys, zlib

RAWLEN = 51964


def parse(d):
    if d[:4] != b"lcyc":
        raise ValueError("Kopf-Magic fehlt")
    size = struct.unpack_from("<I", d, 4)[0]
    off, items = 16, []
    while off + 16 <= len(d):
        if d[off:off + 4] != b"scyc":
            if d[off:off + 4] != b"\xff\xff\xff\xff":
                raise ValueError(f"u32MagicItemStart falsch bei {off}: {d[off:off+4]!r}")
            break
        ln, nxt, raw = struct.unpack_from("<III", d, off + 4)
        if nxt >= size // 3:
            raise ValueError(f"Eintrag {off}: Länge {nxt} >= {size // 3}")
        if d[off + 16 + ln:off + 20 + ln] != b"ecyc":
            raise ValueError(f"Eintrag {off}: MagicEnd fehlt")
        items.append((off, ln, nxt, raw))
        off += nxt
    if not items:
        raise ValueError("kein Eintrag")
    off, ln, nxt, raw = items[-1]
    body = zlib.decompressobj(31).decompress(d[off + 16:off + 16 + ln])
    if len(body) != raw or raw != RAWLEN:
        raise ValueError(f"entpackt {len(body)} statt {raw}")
    if body[:4] != b"arap" or body[-4:] != b"mrap":
        raise ValueError("param.bin-Magics (arap/mrap) fehlen")
    return items, body


if __name__ == "__main__":
    d = open(sys.argv[1], "rb").read()
    items, body = parse(d)
    print(f"{len(items)} Einträge, letzter bei {items[-1][0]}, {len(body)} Bytes, Magics ok")
    for p in sys.argv[2:]:
        ok = all(body[int(o):int(o) + len(bytes.fromhex(h))] == bytes.fromhex(h)
                 for o, h in (l.split() for l in open(p)))
        print(f"  passt zu {p}: {ok}")
