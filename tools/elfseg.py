#!/usr/bin/env python3
"""main_app der CT9500 um ein Code-/Datensegment erweitern (zusätzliche Menüzeilen).

  tools/elfseg.py <main_app> <ausgabe>

1. src/menuhook.S bei SEG_VA assemblieren/linken (musl-Toolchain, nur ARM-Code ohne libc).
2. Programmkopf 7 (PT_GNU_RELRO, nur Schreibschutz-Hilfe für ld.so) -> PT_LOAD (RWX) für
   das neue Segment am Dateiende.
3. SYSTEM_SET_button_onkeydown: Verweise auf die 6 Zeilenlisten (31 Einträge) auf die neuen
   Listen (35 Einträge) umbiegen; Konstanten 31 -> 35 (auch in SYSTEM_SET_onshow).
4. HiGV-Handlertabelle: Eintrag 55 (onshow) und 56 (button_onkeydown) -> Hooks.
Jede Änderung prüft vorher den Originalinhalt.
"""
import os, re, struct, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TC = os.path.join(ROOT, "toolchain/armv7l-linux-musleabihf-cross/bin/armv7l-linux-musleabihf-")
SRC = os.path.join(ROOT, "src/menuhook.S")
SEG_VA = 0x00420000
NEW_ROWS = 35

# VA der Original-Listen -> Symbol der neuen Liste
LISTS = {0x378700: "rows_btn", 0x37877C: "rows_lbl", 0x3787F8: "rows_val",
         0x378874: "rows_btn_rev", 0x3788F0: "rows_lbl_rev", 0x37896C: "rows_val_rev"}
# Literal-Pool-Wort (VA), zugehöriger "add rX, pc, rX" (VA), Original-Ziel
LIST_REFS = [
    (0x881C4, 0x87C74, 0x3787F8), (0x881C8, 0x87C7C, 0x37877C), (0x881CC, 0x87C88, 0x378700),  # MENU: SYSTEM_SET_exit
    (0x881D0, 0x87CB4, 0x3787F8), (0x881D4, 0x87CBC, 0x37877C), (0x881D8, 0x87CC8, 0x378700),  # hoch
    (0x881F4, 0x87D84, None), (0x881F8, 0x87D8C, None), (0x881FC, 0x87D98, 0x378874),          # runter
]
# Instruktionen mit Konstante 31 (VA, Originalwort)
IMM31 = [(0x87C80, 0xE3A0101F), (0x87CC0, 0xE3A0101F), (0x87D08, 0xE353001F), (0x87D34, 0xE3A0301F),
         (0x87D90, 0xE3A0101F), (0x87DE4, 0xE3A0201F), (0x87E00, 0xE3A0301F), (0x7C2A8, 0xE3A0301F),
         # SYSTEM_SET_groupbox_*_exit (34x): Zähler "%d/%d" (Widget 566) nach Schließen eines Dialogs
         (0x7C61C, 0xE3A0301F), (0x7C7B8, 0xE3A0301F), (0x7C950, 0xE3A0301F), (0x7CAE8, 0xE3A0301F),
         (0x7CC98, 0xE3A0301F), (0x7CE30, 0xE3A0301F), (0x7CFC8, 0xE3A0301F), (0x7D160, 0xE3A0301F),
         (0x7D2F8, 0xE3A0301F), (0x7D490, 0xE3A0301F), (0x7D628, 0xE3A0301F), (0x7D7C0, 0xE3A0301F),
         (0x7D958, 0xE3A0301F), (0x7DAF0, 0xE3A0301F), (0x7DC88, 0xE3A0301F), (0x7DE24, 0xE3A0301F),
         (0x7DFC0, 0xE3A0301F), (0x7E158, 0xE3A0301F), (0x7E2F0, 0xE3A0301F), (0x7E488, 0xE3A0301F),
         (0x7E624, 0xE3A0301F), (0x7E7BC, 0xE3A0301F), (0x7E954, 0xE3A0301F), (0x7EAEC, 0xE3A0301F),
         (0x7EC84, 0xE3A0301F), (0x7EE1C, 0xE3A0301F), (0x7EFB4, 0xE3A0301F), (0x7F17C, 0xE3A0301F),
         (0x7F3D0, 0xE3A0301F), (0x7F56C, 0xE3A0301F), (0x7F708, 0xE3A0301F), (0x7F8A4, 0xE3A0301F),
         (0x7FA40, 0xE3A0301F), (0x7FBD8, 0xE3A0301F)]
HANDLER_TABLE = 0x37835C          # VA, 200 Einträge
HOOKS = {55: (0x7C13C, "hook_onshow"), 56: (0x87BB4, "hook_keydown")}
# B/BL umbiegen: (VA der Instruktion, ursprüngliches Ziel, neues Symbol)
CALLS = [(0x612B8, 0x74C64, "hook_usbwin"),    # bl: USB-Fenster 176, Bild/Text nach Zustand
         # PDT_UI_POWERCTRL_PreProcessEvent: Bildschirm-Ruhemodus auch im USB-Modus
         (0x71FD4, 0x71FF0, "pwr_usb_pause"),  # b: Sprungtabelle Zustand 10 (UVC)
         (0x71FD8, 0x71FF0, "pwr_usb_pause"),  # b: Sprungtabelle Zustand 11 (USB-Speicher)
         (0x71FCC, 0x72038, "pwr_resume"),     # b: alle anderen Zustände (Resume)
         (0xA7FD0, 0xA0228, "hook_clickkey"),  # bl: sendclickkey.cgi Test-Tasten K<n>/L<n>
         (0x5FA20, 0x5FA8C, "hook_long_wifi"), # b: lang WLAN-Taste = Einstellungen
         (0x7C0BC, 0x622C8, "hook_set_exit"),  # bl: Einstellungen verlassen ohne Moduswechsel
         # Eigenes Menü (ctui): HiGV-Refresh unterdrücken, Tasten umleiten
         (0x2255FC, 0x19E0C, "hook_refresh"), (0x22563C, 0x19E0C, "hook_refresh"),
         (0x5F9B4, 0x1AA368, "hook_input"), (0x5FAE0, 0x1AA368, "hook_input"),
         (0x5FB7C, 0x1AA368, "hook_input"), (0x5FC90, 0x1AA368, "hook_input")]


def segments(d):
    phoff, phentsize, phnum = struct.unpack_from("<I", d, 0x1C)[0], *struct.unpack_from("<HH", d, 0x2A)
    return phoff, phentsize, [struct.unpack_from("<8I", d, phoff + i * phentsize) for i in range(phnum)]


def va2off(d, va):
    for p in segments(d)[2]:
        if p[0] == 1 and p[2] <= va < p[2] + p[4]:
            return p[1] + va - p[2]
    raise ValueError(hex(va))


CSRC = [os.path.join(ROOT, "src/menucat.c"), os.path.join(ROOT, "src/crash.c")]
CFLAGS = ["-O2", "-mcpu=cortex-a7", "-marm", "-mfloat-abi=soft", "-ffreestanding", "-fno-builtin",
          "-fno-pic", "-fno-common", "-fno-zero-initialized-in-bss", "-fno-stack-protector",
          "-fno-unwind-tables", "-fno-asynchronous-unwind-tables", "-Wall", "-Werror"]


def build_blob():
    with tempfile.TemporaryDirectory() as t:
        o, e, b = os.path.join(t, "h.o"), os.path.join(t, "h.elf"), os.path.join(t, "h.bin")
        subprocess.run([TC + "gcc", "-c", "-mcpu=cortex-a7", "-marm", "-o", o, SRC], check=True)
        objs = [o]
        for c in CSRC:      # C-Teile: freistehend, alles in .text/.rodata/.data (kein .bss)
            co = os.path.join(t, os.path.basename(c) + ".o")
            subprocess.run([TC + "gcc", "-c", *CFLAGS, "-o", co, c], check=True)
            objs.append(co)
        subprocess.run([TC + "ld", "-Ttext", hex(SEG_VA), "-N", "-o", e, *objs], check=True)
        hdr = subprocess.run([TC + "objdump", "-h", e], capture_output=True, text=True, check=True).stdout
        if re.search(r"\.bss\s+0*[1-9a-f]", hdr):
            raise SystemExit("elfseg: .bss im Segment - Variablen initialisieren")
        subprocess.run([TC + "objcopy", "-O", "binary", "-j", ".text", "-j", ".rodata", "-j", ".data", e, b], check=True)
        syms = {}
        for line in subprocess.run([TC + "nm", e], capture_output=True, text=True, check=True).stdout.splitlines():
            p = line.split()
            if len(p) == 3:
                syms[p[2]] = int(p[0], 16)
        return open(b, "rb").read(), syms


def patch(d, syms, blob):
    d = bytearray(d)
    def word(va):
        return struct.unpack_from("<I", d, va2off(d, va))[0]
    def setword(va, v):
        struct.pack_into("<I", d, va2off(d, va), v & 0xFFFFFFFF)

    # 3a) Listenverweise
    for lit, addpc, expect in LIST_REFS:
        tgt = (addpc + 8 + struct.unpack("<i", struct.pack("<I", word(lit)))[0]) & 0xFFFFFFFF
        if expect is not None and tgt != expect:
            raise SystemExit(f"Literal {lit:#x}: Ziel {tgt:#x} statt {expect:#x}")
        if tgt not in LISTS:
            raise SystemExit(f"Literal {lit:#x}: unbekanntes Ziel {tgt:#x}")
        setword(lit, syms[LISTS[tgt]] - (addpc + 8))
        print(f"  Liste {tgt:#x} -> {LISTS[tgt]} ({syms[LISTS[tgt]]:#x}) via Literal {lit:#x}")
    # 3b) 31 -> 34
    for va, orig in IMM31:
        if word(va) != orig:
            raise SystemExit(f"Instruktion {va:#x}: {word(va):#x} statt {orig:#x}")
        setword(va, (orig & ~0xFF) | NEW_ROWS)
    print(f"  {len(IMM31)} Konstanten 31 -> {NEW_ROWS}")
    # 4) Handlertabelle
    for idx, (orig, sym) in HOOKS.items():
        va = HANDLER_TABLE + 4 * idx
        if word(va) != orig:
            raise SystemExit(f"Handler {idx}: {word(va):#x} statt {orig:#x}")
        setword(va, syms[sym])
        print(f"  Handler {idx}: {orig:#x} -> {sym} ({syms[sym]:#x})")
    # 5) B/BL umbiegen (Bedingung/Art bleibt erhalten)
    for va, orig, sym in CALLS:
        w = word(va)
        tgt = (va + 8 + (((w & 0xFFFFFF) ^ 0x800000) - 0x800000) * 4) & 0xFFFFFFFF
        if (w & 0x0E000000) != 0x0A000000 or tgt != orig:   # B/BL, beliebige Bedingung
            raise SystemExit(f"B/BL {va:#x}: {w:#x} (Ziel {tgt:#x}) statt {orig:#x}")
        setword(va, (w & 0xFF000000) | (((syms[sym] - (va + 8)) >> 2) & 0xFFFFFF))
        print(f"  {'BL' if w & 0x01000000 else 'B '}{'' if w >> 28 == 0xE else f'(cond {w >> 28:x})'} {va:#x}: {orig:#x} -> {sym} ({syms[sym]:#x})")
    # 2) neues Segment
    phoff, phentsize, phdrs = segments(d)
    if phdrs[7][0] != 0x6474E552:          # PT_GNU_RELRO
        raise SystemExit(f"Programmkopf 7 ist {phdrs[7][0]:#x}, nicht GNU_RELRO")
    while len(d) % 0x1000:
        d.append(0)
    off = len(d)
    d += blob
    struct.pack_into("<8I", d, phoff + 7 * phentsize, 1, off, SEG_VA, SEG_VA, len(blob), len(blob), 7, 0x1000)
    print(f"  Segment @ Datei {off:#x} / VA {SEG_VA:#x}, {len(blob)} Bytes (RWX)")
    return bytes(d)


def build(src_path):
    blob, syms = build_blob()
    return patch(open(src_path, "rb").read(), syms, blob), syms


if __name__ == "__main__":
    out, syms = build(sys.argv[1])
    open(sys.argv[2], "wb").write(out)
    print("fertig:", sys.argv[2], len(out), "Bytes")
