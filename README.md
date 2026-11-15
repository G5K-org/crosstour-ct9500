# CT9500 Custom-Firmware-Mod

Inoffizielle Erweiterungen für die Action-Cam **Crosstour CT9500** (HiSilicon Hi3559V200,
Original-Firmware V4.1.0.2-A). Das Projekt patcht eine selbst beschaffte Original-Firmware
und erzeugt daraus Update-Pakete (SD-Karte oder OTA über die Weboberfläche der Mod).

> **Kein offizielles Projekt.** Nicht mit Crosstour oder HiSilicon verbunden; Marken gehören
> ihren Inhabern. Nutzung auf eigenes Risiko – fehlerhafte Firmware kann die Kamera unbrauchbar
> machen. Den Bootloader (u-boot) fasst das Projekt nicht an.

## Was enthalten ist

- **Eigenes Einstellungsmenü** (`src/ctui.c`) im modernen Stil: Kategorien, Modus-Wahl, alle
  Aufnahme-Einstellungen, Schalter für die Mod-Funktionen. Öffnet über den normalen
  Moduskreis oder per langem Druck auf die WLAN-Taste.
- **Neue Icons** (`tools/mkicons.py`), Schrift **Inter**, neue Akzentfarbe.
- **WLAN**: Heimnetz-Client, Autostart, kein Abschalten nach 3 Minuten, kein blockierendes
  SSID-Vollbild; **Weboberfläche** (Port 8081) mit Live-Vorschau, Dateien, Einstellungen, OTA.
- **USB**: wählbarer USB-Modus (PC-Kamera/UVC bis 4K30, Speicher, Laden) und ein
  **Debug-Modus** (Netzwerk über USB + serielle Konsole) für Entwicklung ohne WLAN.
- Schnellzugriff auf die Einstellungen, Bildschirm-Ruhemodus im USB-Modus u. a.

## Was NICHT enthalten ist

Keine Firmware-Dateien, Binärdateien oder Daten des Herstellers. Für einen Build wird die
Original-Firmware V4.1.0.2-A benötigt (nicht Teil dieses Repos), entpackt nach
`firmware/extracted/…` bzw. `firmware/fs/` (siehe `tools/build.py`). Die Patches beziehen sich
auf genau diese Version; Adressen in `src/menuhook.S` und `tools/elfseg.py` passen nur dazu.

## Aufbau

| Pfad | Inhalt |
|---|---|
| `src/menuhook.S`, `src/menucat.c`, `src/crash.c` | Code, der als zusätzliches Segment in `main_app` eingefügt wird |
| `src/ctui.c` | eigenes Menü-Programm (zeichnet per HiFB `FBIO_REFRESH`) |
| `tools/` | Build (`build.py`), ELF-/JFFS2-/HiGV-Werkzeuge, Icons, Schrift, Tests |
| `mod/appfs/hack/` | Skripte und Weboberfläche, die ins Image kommen |
| `mod/lang_de.py` | Korrekturen der deutschen Texte |

Build (mit Original-Firmware und ARM-Toolchain `armv7l-linux-musleabihf`):

```
.venv/bin/python tools/build.py M50          # -> out/M50/ (SD-Karte) und out/M50.tar (OTA)
```

## Lizenzen von Fremdbestandteilen

| Bestandteil | Lizenz | Datei |
|---|---|---|
| Inter (Schrift, Rasmus Andersson) | SIL Open Font License 1.1 | `mod/fonts/OFL.txt` |
| Tabler Icons (Paweł Kuna) | MIT | `mod/icons/tabler/LICENSE` |
| stb_truetype (Sean Barrett) | Public Domain / MIT | Kopf von `src/third_party/stb_truetype.h` |
| jmuxer (Samir Das) | MIT | Kopf von `mod/appfs/hack/www/jmuxer.min.js` |

Busybox und wpa_supplicant werden beim Build aus den offiziellen Quellen übersetzt
(GPL-2.0 bzw. BSD) und sind nicht im Repo enthalten.
