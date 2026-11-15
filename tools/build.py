#!/usr/bin/env python3
"""Baut ein CT9500-Update-Paket für die SD-Karte.

  .venv/bin/python tools/build.py M1            -> out/M1/ (7 Images + config)
  .venv/bin/python tools/build.py recovery      -> out/recovery/ (Original, nur Versionscode erhöht)

Der Bootloader flasht beim Einschalten, wenn die Dateien im Wurzelverzeichnis der
SD-Karte liegen und der Versionscode in `config` (swverv2) sich vom installierten
unterscheidet. Jeder Build bekommt daher einen neuen, höheren Code
(Zähler in out/.buildcounter).
"""
import os, re, shutil, stat, sys, warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
sys.path.insert(0, os.path.dirname(__file__))
from jffs2patch import Jffs2Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STOCK = os.path.join(ROOT, "firmware/extracted/CT9500-V4.1.0.2-A _2020305改善SD卡/CT9500-V4.1.0.2-A")
MOD = os.path.join(ROOT, "mod")
OUT = os.path.join(ROOT, "out")
PART_KB = {"appfs.jffs2": 8064, "rootfs.jffs2": 1920, "uImage": 2560, "media_app_zip.bin": 2944}
STOCK_CODE = 303111844        # S2_GR01V2_2_2GDDR3_0303111844


def next_code():
    os.makedirs(OUT, exist_ok=True)
    f = os.path.join(OUT, ".buildcounter")
    n = int(open(f).read()) + 1 if os.path.exists(f) else 1
    open(f, "w").write(str(n))
    return STOCK_CODE + n


def overlay(img, srcdir):
    """Alle Dateien aus srcdir (gleiche Pfade wie im Image) einspielen."""
    for root, dirs, files in os.walk(srcdir):
        rel = os.path.relpath(root, srcdir)
        rel = "" if rel == "." else rel
        for d in sorted(dirs):
            img.mkdir(os.path.join(rel, d), 0o40750)
        for f in sorted(files):
            p, dst = os.path.join(root, f), os.path.join(rel, f)
            if os.path.islink(p):
                img.symlink(dst, os.readlink(p))
            else:
                img.put(dst, open(p, "rb").read(), 0o100750)
            print(f"  + {dst}")


BUILD = os.path.join(ROOT, "build", "src")
BINARIES = {   # Ziel im Image -> selbst gebautes ARM-Programm
    "hack/busybox": os.path.join(BUILD, "busybox-1.36.1/busybox"),
    "hack/wpa_supplicant": os.path.join(BUILD, "wpa_supplicant-2.11/wpa_supplicant/wpa_supplicant"),
    "hack/wpa_cli": os.path.join(BUILD, "wpa_supplicant-2.11/wpa_supplicant/wpa_cli"),
    "hack/rtsp2h264": os.path.join(ROOT, "build", "rtsp2h264"),   # aus src/rtsp2h264.c
    "hack/memdump": os.path.join(ROOT, "build", "memdump"),       # aus src/memdump.c (Screenshots)
}
# Werden weder von main_app noch von Skripten benutzt (Originale liegen in firmware/fs/)
REMOVE = ["rtwpriv", "param/bin2flash", "param/ini2bin_board", "sharefs/scene_ini2bin_board",
          "komod/uvcvideo.ko", "komod/gspca_main.ko", "komod/hi3559v200_nnie.ko"]


def mod_version(name):
    return f"{name} ({__import__('datetime').date.today().isoformat()})"


def stage_hack(dst, name):
    """Inhalt von /app/hack als Verzeichnis (für Live-Tests ohne Flashen)."""
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(os.path.join(MOD, "appfs", "hack"), dst)
    for path, src in BINARIES.items():
        shutil.copy(src, os.path.join(dst, os.path.relpath(path, "hack")))
    os.makedirs(os.path.join(dst, "real"), exist_ok=True)
    shutil.copy(os.path.join(ROOT, "firmware/fs/appfs/bin/hostapd"), os.path.join(dst, "real/hostapd"))
    open(os.path.join(dst, "VERSION"), "w").write(mod_version(name) + "\n")
    for root, _, files in os.walk(dst):
        for f in files:
            os.chmod(os.path.join(root, f), 0o750)


# Binär-Patches in main_app: (Dateioffset, Originalbytes, neue Bytes, Zweck)
MAIN_APP_PATCHES = [
    # V100_start_wifi_timer (VA 0x52cbc): Original schaltet das WLAN 3 Minuten nach dem
    # Einschalten ab, wenn keine Handy-App verbunden ist - im Heimnetz-Modus also immer
    # (am 15.11. mit M10 beobachtet). Erste Instruktion "push {fp, lr}" -> "bx lr".
    (0x42CBC, bytes.fromhex("00482de9"), bytes.fromhex("1eff2fe1"), "WLAN-3-Minuten-Abschaltung deaktiviert"),
    # UI_SetWifiControl (VA 0x63c30): bei WLAN an ohne verbundene Handy-App blendet das Original
    # Widget 140 ein (Vollbild "SSID/PWD" über dem Startbildschirm, blockiert die Bedienung).
    # "bl HI_GV_Widget_Show" -> "bl HI_GV_Widget_Hide" (0x1b8b88).
    (0x53C30, bytes.fromhex("685505eb"), bytes.fromhex("d45305eb"), "WLAN-Info-Vollbild (SSID/PWD) nicht mehr einblenden"),
]


# Neue Menüzeilen (Einstellungen): Sprachindex -> (Deutsch, Englisch/sonst)
MENU_ROWS = {470: ("WLAN-Autostart", "WiFi autostart"),
             471: ("Heimnetz", "Home network"),
             472: ("Telnet", "Telnet"),
             473: ("USB-Modus", "USB mode"),
             # Werte der Zeile USB-Modus (src/menuhook.S usb_str)
             474: ("Speicher", "Storage"),
             475: ("PC-Kamera", "PC camera"),
             476: ("Laden", "Charge"),
             477: ("Debug", "Debug")}


def patch_main_app(img):
    """Byte-Patches (MAIN_APP_PATCHES) + neues Segment für die zusätzlichen Menüzeilen
    (tools/elfseg.py). Nur geänderte 4-KiB-Seiten werden neu (unkomprimiert) geschrieben."""
    import elfseg
    data = bytearray(img.read("bin/main_app"))
    for off, old, new, why in MAIN_APP_PATCHES:
        if data[off:off + len(old)] != old:
            raise SystemExit(f"main_app: unerwartete Bytes bei {off:#x} ({why}) - Abbruch")
        data[off:off + len(new)] = new
        print(f"  ~ bin/main_app @{off:#x}: {why}")
    blob, syms = elfseg.build_blob()
    data = elfseg.patch(bytes(data), syms, blob)
    pages = img.update_file("bin/main_app", data)
    print(f"  ~ bin/main_app: {len(pages)} Seiten neu, Größe {len(data)}")


def patch_higv(img):
    import higv_addrows
    stock = os.path.join(ROOT, "firmware/fs/appfs/bin/higv.bin")
    TELNET_ICON = (0x21A, 0x219, 0x219)   # Skins md_no_select/md_select (unbenutzt) -> Terminal-Icon
    USB_ICON = (0x228, 0x227, 0x227)      # Skins hdr_no_select/hdr_select (unbenutzt) -> USB-Icon
    new, handles = higv_addrows.add_rows(stock, [(470, higv_addrows.WIFI_ICON), (471, higv_addrows.WIFI_ICON),
                                                 (472, TELNET_ICON), (473, USB_ICON)])
    assert handles == [(1121, 1122, 1123), (1124, 1125, 1126), (1127, 1128, 1129),
                       (1130, 1131, 1132)], handles  # wie in src/menuhook.S
    import higv_theme
    new, fchg = higv_theme.bitmap_fonts_to_vector(new)
    new, ncol = higv_theme.recolor(new, {higv_theme.accent_argb(higv_theme.OLD_ACCENT): higv_theme.accent_argb(higv_theme.NEW_ACCENT)})
    new = higv_theme.fix_crc(new)
    img.put("bin/higv.bin", bytes(new), img.mode("bin/higv.bin"))
    print(f"  ~ bin/higv.bin: {len(handles)} Menüzeilen ({handles}); Bitmap-Schriften -> vector.ttf {fchg}")


def patch_lang(img):
    """Deutsche Korrekturen (mod/lang_de.py) + Texte der neuen Menüzeilen in allen Sprachen."""
    sys.path.insert(0, MOD)
    from lang_de import DE
    from langfile import load, build
    for fn in sorted(img.listdir("bin")):
        if not fn.endswith(".lang"):
            continue
        head, strings = load(os.path.join(ROOT, "firmware/fs/appfs/bin", fn))
        changes = dict(DE) if fn == "de.lang" else {}
        for idx, (de, other) in MENU_ROWS.items():
            changes[idx] = de if fn == "de.lang" else other
        need = max(changes) + 1
        strings += [b""] * (need - len(strings))
        for i, t in changes.items():
            strings[i] = t.encode("utf-8")
        img.put(f"bin/{fn}", build(head, strings), img.mode(f"bin/{fn}"))
    print(f"  ~ bin/*.lang: Menütexte {sorted(MENU_ROWS)}; de.lang {len(DE)} Korrekturen")


def patch_font(img):
    """UI-Schrift: Inter (SIL OFL) + CJK-Zeichen der Original-Schrift (tools/mkfont.py)."""
    import mkfont
    out = os.path.join(ROOT, "build", "ui_font.ttf")
    mkfont.main(os.path.join(MOD, "fonts", "Inter-Medium.ttf"), out)
    img.put("bin/res/font/vector.ttf", open(out, "rb").read(), img.mode("bin/res/font/vector.ttf"))
    img.mkdir("hack/fonts", 0o40750)
    img.put("hack/fonts/OFL-Inter.txt", open(os.path.join(MOD, "fonts", "OFL.txt"), "rb").read(), 0o100640)
    print("  ~ bin/res/font/vector.ttf: Inter (Lizenz: hack/fonts/OFL-Inter.txt)")


def patch_pictures(img):
    """Akzentfarbe der Oberflächenbilder: #0645EA -> Akzentblau #0A84FF (tools/higv_theme.py)."""
    import higv_theme
    base = os.path.join(ROOT, "firmware/fs/appfs/bin")
    n = 0
    for root, _, files in os.walk(os.path.join(base, "res/pic")):
        for f in files:
            if f.endswith(".png"):
                rel = os.path.relpath(os.path.join(root, f), os.path.join(ROOT, "firmware/fs/appfs"))
                new = higv_theme.recolor_png(open(os.path.join(root, f), "rb").read())
                if new:
                    img.put(rel, new, img.mode(rel))
                    n += 1
    print(f"  ~ bin/res/pic: {n} Bilder auf Akzentfarbe {higv_theme.NEW_ACCENT}")
    # Neue Icons (modernen Stil, tools/mkicons.py; Symbole: Tabler Icons, MIT)
    import mkicons
    out = os.path.join(ROOT, "build", "icons")
    shutil.rmtree(out, ignore_errors=True)
    icons = mkicons.build(out)
    for rel in icons:
        dst = "bin/" + rel
        img.put(dst, open(os.path.join(out, rel), "rb").read(), img.mode(dst) or 0o100750)
    img.put("hack/fonts/LICENSE-tabler-icons.txt", open(os.path.join(MOD, "icons/tabler/LICENSE"), "rb").read(), 0o100640)
    print(f"  ~ bin/res/pic: {len(icons)} neue Icons")


def patch_appfs(img, name):
    overlay(img, os.path.join(MOD, "appfs"))
    patch_font(img)
    patch_pictures(img)
    patch_main_app(img)
    patch_higv(img)
    patch_lang(img)
    for path, src in BINARIES.items():
        img.put(path, open(src, "rb").read(), 0o100750)
        print(f"  + {path}")
    img.mkdir("hack/real", 0o40750)
    img.put("hack/real/hostapd", img.read("bin/hostapd"), 0o100750)
    img.put("bin/hostapd", open(os.path.join(MOD, "appfs/hack/hostapd-wrapper.sh"), "rb").read(), 0o100750)
    img.put("hack/VERSION", (mod_version(name) + "\n").encode(), 0o100640)
    img.symlink("udhcpd.conf", "/dev/ct9500mod/udhcpd.conf")
    print("  ~ bin/hostapd -> Wrapper, Original nach hack/real/hostapd; udhcpd.conf -> /dev/ct9500mod")
    for path in REMOVE:
        img.delete(path)
        print(f"  - {path}")
    boot = img.read("bootapp").decode()
    if "/dev/ma.log" not in boot:   # main_app-Ausgabe nur bei /etc/ct9500mod/debug mitschreiben
        boot = boot.replace("./main_app &", "if [ -f /etc/ct9500mod/debug ]; then ./main_app > /dev/ma.log 2>&1 & else ./main_app & fi")
    if "/app/hack/preboot.sh" not in boot:
        boot = boot.replace("#start application", "# CT9500-Mod: vor main_app\n[ -x /app/hack/preboot.sh ] && /app/hack/preboot.sh\n\n#start application")
    if "/app/hack/start.sh" not in boot:
        boot = boot.rstrip("\n") + "\n\n# CT9500-Mod\n[ -x /app/hack/start.sh ] && /app/hack/start.sh &\n"
    img.put("bootapp", boot.encode(), img.mode("bootapp"))
    print("  ~ bootapp")


def make_ota(dst, files):
    """OTA-Paket (tar) für die Weboberfläche: Images + config + MANIFEST.sha256."""
    import hashlib, tarfile
    man = "".join(f"{hashlib.sha256(open(os.path.join(dst, f), 'rb').read()).hexdigest()}  {f}\n" for f in files)
    open(os.path.join(dst, "MANIFEST.sha256"), "w").write(man)
    tar = dst + ".tar"
    with tarfile.open(tar, "w", format=tarfile.USTAR_FORMAT) as t:
        for f in files + ["MANIFEST.sha256"]:
            ti = t.gettarinfo(os.path.join(dst, f), f)
            ti.uid = ti.gid = 0; ti.uname = ti.gname = "root"; ti.mode = 0o644
            t.addfile(ti, open(os.path.join(dst, f), "rb"))
    os.remove(os.path.join(dst, "MANIFEST.sha256"))
    print(f"OTA-Paket: {tar} ({os.path.getsize(tar)} Bytes)")


def main():
    if sys.argv[1:2] == ["stage"]:
        stage_hack(os.path.join(ROOT, "build", "stage", "hack"), sys.argv[2] if len(sys.argv) > 2 else "dev")
        print("Staging: build/stage/hack")
        return
    name = sys.argv[1] if len(sys.argv) > 1 else "test"
    ota_files = sys.argv[2].split(",") if len(sys.argv) > 2 else ["config", "appfs.jffs2"]
    dst = os.path.join(OUT, name)
    shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(dst)
    for f in os.listdir(STOCK):
        shutil.copy(os.path.join(STOCK, f), dst)

    if name != "recovery":
        img = Jffs2Image.load(os.path.join(STOCK, "appfs.jffs2"))
        patch_appfs(img, name)
        size = img.save(os.path.join(dst, "appfs.jffs2"), max_size=PART_KB["appfs.jffs2"] * 1024)
        print(f"appfs.jffs2: {size} Bytes, frei {PART_KB['appfs.jffs2'] * 1024 - size}")

    code = next_code()
    cfg = open(os.path.join(STOCK, "config")).read()
    cfg = re.sub(r"(swverv2 'S2_GR01V2_2_2GDDR3_)\d+'", lambda m: f"{m.group(1)}{code:010d}'", cfg)
    open(os.path.join(dst, "config"), "w", newline="\n").write(cfg)
    print(f"Versionscode: {code:010d}")
    print(f"Fertig: {dst}")
    make_ota(dst, ota_files)


if __name__ == "__main__":
    main()
