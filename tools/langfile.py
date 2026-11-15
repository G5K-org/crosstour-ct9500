#!/usr/bin/env python3
"""HiGV-Sprachdateien (bin/*.lang) der CT9500 lesen und schreiben.

Format: 4 Byte CRC | 2..27 Sprachkürzel (nullgefüllt) | u32 Anzahl @0x1C |
        u32 Offsets[Anzahl] @0x20 | nullterminierte UTF-8-Texte
CRC = CRC-32/MPEG-2 (Poly 0x04C11DB7, Start 0xFFFFFFFF, nicht reflektiert, kein XOR)
über alles ab Byte 4 (geprüft in HI_GV_Lan_Register / BParser_CrcGen).

  tools/langfile.py dump bin/de.lang
"""
import struct, sys

_TABLE = []
for i in range(256):
    c = i << 24
    for _ in range(8):
        c = ((c << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if c & 0x80000000 else (c << 1) & 0xFFFFFFFF
    _TABLE.append(c)


def crc_mpeg2(data):
    c = 0xFFFFFFFF
    for b in data:
        c = ((c << 8) & 0xFFFFFFFF) ^ _TABLE[((c >> 24) ^ b) & 0xFF]
    return c


def load(path):
    d = open(path, "rb").read()
    if struct.unpack_from("<I", d, 0)[0] != crc_mpeg2(d[4:]):
        raise ValueError(f"{path}: CRC stimmt nicht")
    n = struct.unpack_from("<I", d, 0x1C)[0]
    offs = struct.unpack_from(f"<{n}I", d, 0x20)
    base = 0x20 + 4 * n
    strings = [d[base + o:d.index(b"\0", base + o)] for o in offs]
    return d[4:0x1C], strings      # Kopf (Sprachkürzel), Texte als Bytes


def build(head, strings):
    offs, blob = [], bytearray()
    for s in strings:
        offs.append(len(blob))
        blob += s + b"\0"
    body = head + struct.pack("<I", len(strings)) + struct.pack(f"<{len(strings)}I", *offs) + blob
    return struct.pack("<I", crc_mpeg2(body)) + body


def patch(data_path, changes):
    """changes: {index: neuer Text} -> neue Dateibytes"""
    head, strings = load(data_path)
    for i, text in changes.items():
        strings[i] = text.encode("utf-8")
    return build(head, strings)


if __name__ == "__main__":
    if sys.argv[1:2] == ["dump"]:
        _, s = load(sys.argv[2])
        for i, t in enumerate(s):
            print(i, t.decode("utf-8", "replace"))
