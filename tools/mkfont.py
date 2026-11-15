#!/usr/bin/env python3
"""UI-Schrift der CT9500 bauen: Inter (SIL OFL) + fehlende Zeichen aus der Original-Schrift.

  .venv/bin/python tools/mkfont.py <Inter-*.ttf> <ausgabe.ttf>

- Inter wird auf Latein (inkl. Erweiterungen), Griechisch, Kyrillisch, Satzzeichen und alle
  Zeichen der Sprachdateien (bin/*.lang) reduziert.
- Zeichen, die Inter nicht hat (v. a. Chinesisch/Japanisch der Sprachauswahl), werden samt
  Umrissen und Breiten aus der Original-Schrift (res/font/vector.ttf, Microsoft YaHei,
  nur 799 Glyphen) übernommen. Beide Schriften haben 2048 Einheiten/Em.
Die Original-Lizenz von Inter liegt unter mod/fonts/OFL.txt.
"""
import glob, os, sys
from fontTools.ttLib import TTFont
from fontTools import subset

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from langfile import load

ORIG = os.path.join(ROOT, "firmware/fs/appfs/bin/res/font/vector.ttf")


def needed_chars():
    cs = set(range(0x20, 0x180)) | set(range(0x400, 0x460)) | {0x490, 0x491} \
        | set(range(0x2010, 0x2027)) | {0x2030, 0x2039, 0x203A, 0x20AC, 0x2122, 0x2190, 0x2191, 0x2192, 0x2193}
    for f in glob.glob(os.path.join(ROOT, "firmware/fs/appfs/bin/*.lang")):
        _, strs = load(f)
        for s in strs:
            cs |= {ord(c) for c in s.decode("utf-8", "replace") if ord(c) >= 0x20}
    cs.discard(0xFFFD)
    return cs


def main(src, dst):
    need = needed_chars()
    inter = TTFont(src)
    have = set(inter.getBestCmap())
    opts = subset.Options()
    opts.layout_features = []          # einfacher FreeType-Renderer: kein Shaping
    opts.drop_tables += ["GSUB", "GPOS", "GDEF", "STAT", "DSIG"]
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    opts.glyph_names = True
    opts.hinting = True
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=sorted(need & have))
    sub.subset(inter)

    orig = TTFont(ORIG)
    ocmap = orig.getBestCmap()
    extra = sorted(c for c in need - have if c in ocmap)
    glyf, hmtx = inter["glyf"], inter["hmtx"]
    oglyf, ohmtx = orig["glyf"], orig["hmtx"]
    order = inter.getGlyphOrder()
    added = {}

    def copy_glyph(gname):
        if gname in added:
            return added[gname]
        new = "yh_" + gname
        g = oglyf[gname]
        if g.isComposite():
            for comp in g.components:
                comp.glyphName = copy_glyph(comp.glyphName)
        glyf.glyphs[new] = g
        hmtx.metrics[new] = ohmtx.metrics[gname]
        order.append(new)
        added[gname] = new
        return new

    for c in extra:
        new = copy_glyph(ocmap[c])
        for t in inter["cmap"].tables:
            if t.isUnicode():
                t.cmap[c] = new
    inter.setGlyphOrder(order)
    glyf.glyphOrder = order
    inter["maxp"].numGlyphs = len(order)
    inter["hhea"].numberOfHMetrics = len(order)
    if "post" in inter:
        inter["post"].formatType = 3.0     # keine Glyphennamen nötig, spart Platz
    # Familienname setzen, damit klar ist, was drin ist
    for rec in inter["name"].names:
        if rec.nameID in (1, 4, 16):
            rec.string = "CT9500 UI (Inter)"
    inter.save(dst)
    print(f"{dst}: {os.path.getsize(dst)} Bytes, {len(need & have)} Zeichen aus Inter, {len(extra)} aus Original")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
