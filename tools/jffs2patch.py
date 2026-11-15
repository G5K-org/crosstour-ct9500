#!/usr/bin/env python3
"""JFFS2-Image der CT9500 patchen, ohne es komplett neu zu bauen.

Das Original-Image (mkfs.jffs2, little endian, 64 KiB Erase-Blöcke, LZMA lc0/lp0/pb0
dict 8 KiB) wird Knoten für Knoten übernommen. Nur Knoten von geänderten oder
gelöschten Dateien fallen weg; neue Knoten werden am Ende angehängt.
Bei unverändertem Inhalt ist die Ausgabe byte-identisch mit dem Original.

Benutzung als Bibliothek:
    img = Jffs2Image.load("appfs.jffs2")
    img.put("bootapp", open("bootapp","rb").read(), mode=0o100750)
    img.mkdir("www")
    img.symlink("bin/sd", "/app/sd")
    img.delete("bin/CZ.lang")
    img.save("appfs.new.jffs2", max_size=8064*1024)
"""
import lzma, stat, struct, sys, time, zlib

MAGIC = 0x1985
T_DIRENT, T_INODE, T_CLEAN = 0xE001, 0xE002, 0x2003
COMPR_NONE, COMPR_LZMA = 0x00, 0x08
ERASE = 0x10000
PAGE = 4096
DT = {stat.S_IFDIR: 4, stat.S_IFREG: 8, stat.S_IFLNK: 10, stat.S_IFCHR: 2,
      stat.S_IFBLK: 6, stat.S_IFIFO: 1, stat.S_IFSOCK: 12}
LZMA_FILTERS = [{"id": lzma.FILTER_LZMA1, "dict_size": 0x2000, "lc": 0, "lp": 0, "pb": 0}]


def crc(b):
    return zlib.crc32(b, 0xFFFFFFFF) ^ 0xFFFFFFFF


def lzma_pack(data):
    """LZMA ohne Ende-Markierung wie das Original-mkfs.jffs2 (LZMA SDK, lc0/lp0/pb0, dict 8 KiB).
    Ohne pylzma wird nicht komprimiert (Python-lzma hängt immer eine Ende-Markierung an)."""
    try:
        import pylzma
    except ImportError:
        return None
    c = pylzma.compress(data, dictionary=13, literalContextBits=0, literalPosBits=0, posBits=0,
                        eos=0, algorithm=2, fastBytes=273)[5:]
    if lzma_unpack(c, len(data)) != data:
        raise RuntimeError("LZMA-Selbsttest fehlgeschlagen")
    return c


def lzma_unpack(data, size):
    return lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=LZMA_FILTERS).decompress(data, size)[:size]


class Node:
    __slots__ = ("raw", "type", "ino", "pino", "version", "name", "mode", "dtype")

    def __init__(self, raw):
        self.raw = raw
        _, self.type, _ = struct.unpack_from("<HHI", raw, 0)
        if self.type == T_DIRENT:
            self.pino, self.version, self.ino, _, ns, self.dtype = struct.unpack_from("<IIIIBB", raw, 12)
            self.name = raw[40:40 + ns].decode()
        elif self.type == T_INODE:
            self.ino, self.version, self.mode = struct.unpack_from("<III", raw, 12)


class Jffs2Image:
    def __init__(self, nodes, erase=ERASE):
        self.nodes = nodes            # Liste in Original-Reihenfolge (ohne Cleanmarker)
        self.erase = erase
        self.extra = []               # neue Knoten
        self.dropped_inos = set()
        self.dropped_dirents = set()  # id(node)
        self.dropped_nodes = set()    # id(node) einzelner Datenknoten (patch_bytes)
        self.now = int(time.time())
        self._index()

    # ---------- Laden ----------
    @classmethod
    def load(cls, path):
        d = open(path, "rb").read()
        nodes, i = [], 0
        while i + 12 <= len(d):
            magic, nt, tl = struct.unpack_from("<HHI", d, i)
            if magic != MAGIC or tl < 12 or crc(d[i:i + 8]) != struct.unpack_from("<I", d, i + 8)[0]:
                i += 4
                continue
            if nt != T_CLEAN:
                nodes.append(Node(d[i:i + tl]))
            i = (i + tl + 3) & ~3
        return cls(nodes)

    def _index(self):
        self.dirents = {}             # (pino, name) -> neuester Dirent-Knoten
        self.inodes = {}              # ino -> mode (neuester)
        self.maxver = {}
        for n in self.nodes + self.extra:
            if n.type == T_DIRENT:
                k = (n.pino, n.name)
                if k not in self.dirents or n.version > self.dirents[k].version:
                    self.dirents[k] = n
                self.maxver[("d", n.pino)] = max(self.maxver.get(("d", n.pino), 0), n.version)
            elif n.type == T_INODE:
                if n.version >= self.maxver.get(n.ino, 0):
                    self.inodes[n.ino] = n.mode
                self.maxver[n.ino] = max(self.maxver.get(n.ino, 0), n.version)
        self.maxino = max([1] + list(self.inodes))

    # ---------- Pfade ----------
    def lookup(self, path):
        ino = 1
        for part in [p for p in path.strip("/").split("/") if p]:
            n = self.dirents.get((ino, part))
            if n is None or n.ino == 0:
                return None
            ino = n.ino
        return ino

    def _parent(self, path):
        parts = path.strip("/").split("/")
        pino = self.lookup("/".join(parts[:-1])) if len(parts) > 1 else 1
        if pino is None:
            raise FileNotFoundError("/".join(parts[:-1]))
        return pino, parts[-1]

    def listdir(self, path=""):
        ino = self.lookup(path)
        return sorted(n for (p, n), d in self.dirents.items() if p == ino and d.ino)

    def read(self, path):
        ino = self.lookup(path)
        if ino is None:
            raise FileNotFoundError(path)
        best = {}
        for n in self.nodes + self.extra:
            if n.type == T_INODE and n.ino == ino and ino not in self.dropped_inos:
                off, csize, dsize, compr = struct.unpack_from("<IIIB", n.raw, 44)
                if off not in best or n.version > best[off][0]:
                    best[off] = (n.version, n.raw, csize, dsize, compr)
        isize = max([struct.unpack_from("<I", r[1], 28)[0] for r in best.values()] + [0])
        out = bytearray(isize)
        for off, (_, raw, csize, dsize, compr) in sorted(best.items()):
            data = raw[68:68 + csize]
            if compr == COMPR_LZMA:
                data = lzma_unpack(data, dsize)
            elif compr != COMPR_NONE:
                raise ValueError(f"Kompressor {compr} nicht unterstützt")
            out[off:off + dsize] = data[:dsize]
        return bytes(out[:isize])

    def mode(self, path):
        ino = self.lookup(path)
        return None if ino is None else self.inodes.get(ino)

    # ---------- Knoten erzeugen ----------
    def _dirent(self, pino, name, ino, dtype):
        ver = self.maxver.get(("d", pino), 0) + 1
        self.maxver[("d", pino)] = ver
        nb = name.encode()
        body = struct.pack("<HHI", MAGIC, T_DIRENT, 40 + len(nb))
        body += struct.pack("<I", crc(body))
        body += struct.pack("<IIIIBBH", pino, ver, ino, self.now, len(nb), dtype, 0)
        body += struct.pack("<I", crc(body[:32])) + struct.pack("<I", crc(nb)) + nb
        n = Node(body)
        self.extra.append(n)
        return n

    def _inode(self, ino, mode, data, offset, isize, compress=True, uid=0, gid=0):
        ver = self.maxver.get(ino, 0) + 1
        self.maxver[ino] = ver
        payload, compr = data, COMPR_NONE
        if compress and data:
            c = lzma_pack(data)
            if c is not None and len(c) < len(data):
                payload, compr = c, COMPR_LZMA
        hdr = struct.pack("<HHI", MAGIC, T_INODE, 68 + len(payload))
        hdr += struct.pack("<I", crc(hdr))
        hdr += struct.pack("<IIIHHIIIIIIIBBH", ino, ver, mode, uid, gid, isize,
                           self.now, self.now, self.now, offset, len(payload), len(data), compr, 0, 0)
        hdr += struct.pack("<I", crc(payload))
        hdr += struct.pack("<I", crc(hdr[:60]))
        self.extra.append(Node(hdr + payload))

    def _remove_entry(self, pino, name):
        old = self.dirents.get((pino, name))
        if old is not None and old.ino:
            # Ersetzt einen alten Eintrag: dessen Inode-Knoten fliegen raus, wenn sonst niemand darauf zeigt
            refs = [k for k, d in self.dirents.items() if d.ino == old.ino]
            if len(refs) == 1:
                self.dropped_inos.add(old.ino)
            self.dropped_dirents.add(id(old))
            del self.dirents[(pino, name)]

    # ---------- Öffentliche Operationen ----------
    def put(self, path, data, mode=0o100755, compress=True):
        pino, name = self._parent(path)
        if not stat.S_ISREG(mode) and not stat.S_ISLNK(mode):
            mode |= stat.S_IFREG
        self._remove_entry(pino, name)
        self.maxino += 1
        ino = self.maxino
        if not data:
            self._inode(ino, mode, b"", 0, 0, compress)
        for off in range(0, len(data), PAGE):
            self._inode(ino, mode, data[off:off + PAGE], off, len(data), compress)
        self.dirents[(pino, name)] = self._dirent(pino, name, ino, DT[stat.S_IFMT(mode)])
        self.inodes[ino] = mode

    def symlink(self, path, target):
        self.put(path, target.encode(), mode=stat.S_IFLNK | 0o777, compress=False)

    def mkdir(self, path, mode=0o40755):
        if self.lookup(path) is not None:
            return
        pino, name = self._parent(path)
        self.maxino += 1
        ino = self.maxino
        self._inode(ino, mode, b"", 0, 0, False)
        self.dirents[(pino, name)] = self._dirent(pino, name, ino, 4)
        self.inodes[ino] = mode

    def patch_bytes(self, path, offset, new):
        """Bytes in einer vorhandenen Datei ersetzen, minimal-invasiv: alle Original-Knoten
        bleiben, nur die betroffene(n) 4-KiB-Seite(n) bekommen neue, UNKOMPRIMIERTE Knoten
        (höhere Version) und die alten Knoten dieser Seiten fliegen raus."""
        ino = self.lookup(path)
        data = bytearray(self.read(path))
        data[offset:offset + len(new)] = new
        pages = range(offset // PAGE * PAGE, offset + len(new), PAGE)
        for pg in pages:
            old = [n for n in self.nodes + self.extra
                   if n.type == T_INODE and n.ino == ino and struct.unpack_from("<I", n.raw, 44)[0] == pg]
            if not old:
                raise ValueError(f"kein Knoten für Seite {pg:#x}")
            ref = max(old, key=lambda n: n.version)
            payload = bytes(data[pg:pg + PAGE])
            ver = self.maxver.get(ino, 0) + 1
            self.maxver[ino] = ver
            hdr = bytearray(ref.raw[:68])
            struct.pack_into("<I", hdr, 4, 68 + len(payload))            # totlen
            struct.pack_into("<I", hdr, 8, crc(bytes(hdr[:8])))           # hdr_crc
            struct.pack_into("<I", hdr, 16, ver)                          # version
            struct.pack_into("<III", hdr, 48, len(payload), len(payload), 0)  # csize, dsize, compr/usercompr/flags
            struct.pack_into("<I", hdr, 60, crc(payload))                 # data_crc
            struct.pack_into("<I", hdr, 64, crc(bytes(hdr[:60])))         # node_crc
            for n in old:
                self.dropped_nodes.add(id(n))
            self.extra.append(Node(bytes(hdr) + payload))

    def update_file(self, path, new):
        """Datei auf neuen Inhalt bringen (auch größer), minimal-invasiv: nur geänderte oder
        neue 4-KiB-Seiten bekommen neue, unkomprimierte Knoten; alle anderen bleiben original.
        Die neuen Knoten tragen die neue Dateigröße (gilt, weil sie die höchste Version haben)."""
        ino = self.lookup(path)
        old = self.read(path)
        if len(new) < len(old):
            raise ValueError("Verkleinern nicht unterstützt")
        nodes = [n for n in self.nodes + self.extra if n.type == T_INODE and n.ino == ino]
        ref = max(nodes, key=lambda n: n.version)
        changed = []
        for pg in range(0, len(new), PAGE):
            if new[pg:pg + PAGE] == old[pg:pg + PAGE] and pg + PAGE <= len(old):
                continue
            changed.append(pg)
            for n in nodes:
                if struct.unpack_from("<I", n.raw, 44)[0] == pg:
                    self.dropped_nodes.add(id(n))
            payload = bytes(new[pg:pg + PAGE])
            ver = self.maxver.get(ino, 0) + 1
            self.maxver[ino] = ver
            hdr = bytearray(ref.raw[:68])
            struct.pack_into("<I", hdr, 4, 68 + len(payload))
            struct.pack_into("<I", hdr, 8, crc(bytes(hdr[:8])))
            struct.pack_into("<I", hdr, 16, ver)
            struct.pack_into("<I", hdr, 28, len(new))                     # isize
            struct.pack_into("<I", hdr, 44, pg)                            # offset
            struct.pack_into("<III", hdr, 48, len(payload), len(payload), 0)
            struct.pack_into("<I", hdr, 60, crc(payload))
            struct.pack_into("<I", hdr, 64, crc(bytes(hdr[:60])))
            self.extra.append(Node(bytes(hdr) + payload))
        # Wächst die Datei, muss auch die (bisher) letzte Seite die neue Größe tragen: ist abgedeckt,
        # weil sie sich durch das Anhängen ändert oder ohnehin neu geschrieben wird.
        return changed

    def chmod(self, path, perm):
        data = self.read(path)
        mode = (self.mode(path) & ~0o7777) | perm
        self.put(path, data, mode)

    def delete(self, path):
        pino, name = self._parent(path)
        if (pino, name) not in self.dirents:
            raise FileNotFoundError(path)
        ino = self.dirents[(pino, name)].ino
        if stat.S_ISDIR(self.inodes.get(ino, 0)):
            for child in self.listdir(path):
                self.delete(f"{path}/{child}")
            self.dropped_inos.add(ino)
        self._remove_entry(pino, name)

    # ---------- Schreiben ----------
    def _output_nodes(self):
        for n in self.nodes:
            if id(n) in self.dropped_nodes:
                continue
            if n.type == T_INODE and n.ino in self.dropped_inos:
                continue
            if n.type == T_DIRENT and (id(n) in self.dropped_dirents or n.ino in self.dropped_inos):
                continue
            yield n
        for n in self.extra:
            if id(n) in self.dropped_nodes:
                continue
            if n.type == T_DIRENT and id(n) in self.dropped_dirents:
                continue
            if n.type == T_INODE and n.ino in self.dropped_inos:
                continue
            yield n

    def build(self):
        clean = struct.pack("<HHI", MAGIC, T_CLEAN, 12)
        clean += struct.pack("<I", crc(clean))
        out = bytearray()
        for n in self._output_nodes():
            ln = (len(n.raw) + 3) & ~3
            if len(out) % self.erase == 0 or (len(out) % self.erase) + ln > self.erase:
                if len(out) % self.erase:
                    out += b"\xff" * (self.erase - len(out) % self.erase)
                out += clean
            out += n.raw + b"\xff" * (ln - len(n.raw))
        return bytes(out)

    def save(self, path, max_size=None):
        data = self.build()
        if max_size and len(data) > max_size:
            raise SystemExit(f"Image zu groß: {len(data)} > {max_size} Bytes")
        open(path, "wb").write(data)
        return len(data)


if __name__ == "__main__":
    # Selbsttest: unverändert neu schreiben muss byte-identisch sein
    src = sys.argv[1]
    a = open(src, "rb").read()
    b = Jffs2Image.load(src).build()
    print("identisch" if a == b else f"UNTERSCHIED: {len(a)} vs {len(b)}, erste Abweichung bei "
          f"{next(i for i in range(min(len(a), len(b))) if a[i] != b[i]) if a[:len(b)] != b[:len(a)] else min(len(a), len(b))}")
