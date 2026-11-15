#!/usr/bin/env python3
"""Neue Icons für die CT9500-Oberfläche erzeugen (modernen Stil).

  .venv/bin/python tools/mkicons.py <ausgabe-verzeichnis>

- Einstellungen (res/pic/GKU_PHOTO/set-button/*_select.png, *_no_select.png, 42x42):
  weißes Linien-Symbol auf farbigem, abgerundetem Quadrat, Farbe je Bereich (wie die
  moderne Einstellungs-Apps). Symbole: Tabler Icons (MIT, mod/icons/tabler/LICENSE) bzw. Text.
- Startseite (z2-home-button, top_icon_*): weiße Linien-Symbole, Akku im modernen Stil.
Ausgabe: Dateien unter <ausgabe>/<Pfad relativ zu bin/>, gleiche Pixelgrößen wie das Original.
"""
import io, os, sys
import cairosvg
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLER = os.path.join(ROOT, "mod/icons/tabler")
FONT = os.path.join(ROOT, "mod/fonts/Inter-Medium.ttf")
SS = 4   # Überabtastung

# Farbpalette (dunkles Design)
RED, ORANGE, YELLOW, GREEN, MINT, TEAL, BLUE, INDIGO, PURPLE, PINK, GRAY = (
    (255, 69, 58), (255, 159, 10), (255, 214, 10), (48, 209, 88), (99, 230, 226), (64, 200, 224),
    (10, 132, 255), (94, 92, 230), (191, 90, 242), (255, 55, 95), (142, 142, 147))

# Einstellungs-Icon -> (Tabler-Name oder "T:Text", Farbe)
SETTINGS = {
    "resolution": ("video", RED), "lapse": ("hourglass", RED), "loop": ("repeat", RED),
    "slow": ("gauge", RED), "dis": ("focus-centered", RED), "encode": ("file-settings", RED),
    "fov": ("angle", RED), "bootrec": ("player-record", RED), "car": ("car", RED),
    "photosize": ("photo", ORANGE), "timer": ("alarm", ORANGE), "burst": ("stack-2", ORANGE),
    "dng": ("T:RAW", ORANGE),
    "expose": ("exposure", GREEN), "iso": ("T:ISO", GREEN), "wb": ("T:WB", GREEN),
    "scene": ("mountain", GREEN), "rotation": ("rotate-clockwise", GREEN),
    "wdr": ("contrast", GREEN), "ldc": ("aperture", GREEN), "frequency": ("wave-sine", TEAL),
    # unbenutzte Original-Skins, für die Mod-Zeilen umgewidmet (tools/build.py patch_higv)
    "md": ("terminal-2", GRAY), "hdr": ("usb", TEAL),
    "audio_mute": ("microphone", PINK), "keytone": ("volume", PINK), "voice": ("volume", PINK),
    "wifi": ("wifi", BLUE),
    "language": ("world", GRAY), "time": ("clock", GRAY), "date_stamp": ("calendar", GRAY),
    "dormant": ("moon", INDIGO), "shutdown": ("power", INDIGO),
    "del": ("trash", RED), "sd_format": ("device-sd-card", GRAY), "reset": ("restore", GRAY),
    "vinfo": ("info-circle", GRAY),
}


def svg_icon(name, px, color=(255, 255, 255), stroke=2.0):
    svg = open(os.path.join(TABLER, name + ".svg")).read()
    svg = svg.replace('stroke="currentColor"', 'stroke="#%02x%02x%02x"' % color)
    svg = svg.replace('stroke-width="2"', f'stroke-width="{stroke}"')
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=px * SS, output_height=px * SS)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def text_icon(text, px, color=(255, 255, 255)):
    im = Image.new("RGBA", (px * SS, px * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    size = px * SS
    f = ImageFont.truetype(FONT, int(size * (0.62 if len(text) <= 2 else 0.46)))
    try:
        f.set_variation_by_name("Bold")
    except Exception:
        pass
    bb = d.textbbox((0, 0), text, font=f, stroke_width=SS // 2)
    d.text(((size - (bb[2] - bb[0])) / 2 - bb[0], (size - (bb[3] - bb[1])) / 2 - bb[1]), text,
           font=f, fill=color + (255,), stroke_width=SS // 2, stroke_fill=color + (255,))
    return im


def glyph(spec, px, color=(255, 255, 255)):
    return text_icon(spec[2:], px, color) if spec.startswith("T:") else svg_icon(spec, px, color)


def settings_icon(spec, bg, size=42, box=30, radius=8, glyph_px=20):
    S = size * SS
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    o = (size - box) // 2 * SS
    d.rounded_rectangle((o, o, o + box * SS - 1, o + box * SS - 1), radius * SS, fill=bg + (255,))
    g = glyph(spec, glyph_px)
    go = (S - g.size[0]) // 2
    im.alpha_composite(g, (go, go))
    return im.resize((size, size), Image.LANCZOS)


def line_icon(spec, w, h, glyph_px=None, color=(255, 255, 255)):
    px = glyph_px or min(w, h)
    g = glyph(spec, px, color).resize((px, px), Image.LANCZOS)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    im.alpha_composite(g, ((w - px) // 2, (h - px) // 2))
    return im


def battery(w, h, level, charging=False):
    """Akku-Symbol: abgerundeter Rahmen, Pol rechts, Füllstand (level 0..1)."""
    S = SS
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    bw, bh = (w - 3) * S, int(h * 0.8) * S
    y0 = (h * S - bh) // 2
    d.rounded_rectangle((S // 2, y0, bw, y0 + bh), 3 * S, outline=(255, 255, 255, 150), width=S + S // 2)
    d.rounded_rectangle((bw + S, y0 + bh // 3, bw + 2 * S + S // 2, y0 + bh * 2 // 3), S, fill=(255, 255, 255, 150))
    col = (48, 209, 88) if charging else ((255, 69, 58) if level <= 0.2 else (255, 255, 255))
    if level > 0:
        inner = (S * 2 + S // 2, y0 + S * 2, S * 2 + S // 2 + int((bw - S * 4) * level), y0 + bh - S * 2)
        d.rounded_rectangle(inner, 2 * S, fill=col + (255,))
    if charging:   # Blitz
        cx, cy = bw // 2, y0 + bh // 2
        pts = [(cx + S, cy - bh // 2 + S), (cx - 3 * S, cy + S), (cx, cy + S), (cx - S, cy + bh // 2 - S),
               (cx + 3 * S, cy - S), (cx, cy - S)]
        d.polygon(pts, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255))
    return im.resize((w, h), Image.LANCZOS)


def build(out):
    files = {}
    sb = "res/pic/GKU_PHOTO/set-button/"
    for name, (spec, col) in SETTINGS.items():
        im = settings_icon(spec, col)
        files[sb + name + "_no_select.png"] = im
        files[sb + name + "_select.png"] = im
    hb = "res/pic/GKU_PHOTO/z2-home-button/"
    levels = [0.05, 0.3, 0.55, 0.8, 1.0]
    for i, lv in enumerate(levels):
        files[hb + f"battery_{i}.png"] = battery(26, 15, lv)
        files[f"res/pic/top_icon_battery_{i}.png"] = battery(23, 13, lv).crop((0, 0, 23, 13)).resize((23, 13)) \
            if False else _pad(battery(23, 13, lv), 23, 26)
    files[hb + "battery_ac.png"] = battery(26, 15, 1.0, charging=True)
    files["res/pic/top_icon_battery_ac.png"] = _pad(battery(23, 13, 1.0, charging=True), 23, 26)
    files["res/pic/top_icon_wifi.png"] = line_icon("wifi", 23, 26, 20)
    files["res/pic/top_icon_wifi_fo.png"] = line_icon("wifi", 23, 26, 20, BLUE)
    files["res/pic/top_icon_usb.png"] = line_icon("usb", 23, 26, 20)
    files[hb + "mode_recnormal.png"] = line_icon("video", 26, 18, 18)
    files[hb + "mode_rec.png"] = line_icon("video", 26, 18, 18, RED)
    files[hb + "mode_photo.png"] = line_icon("camera", 26, 18, 18)
    files[hb + "mode_burst.png"] = line_icon("stack-2", 26, 18, 18)
    files[hb + "mode_timer.png"] = line_icon("alarm", 26, 18, 18)
    files[hb + "timelapse_mode_normal.png"] = line_icon("hourglass", 26, 18, 18)
    files[hb + "timelapse_mode_rec.png"] = line_icon("hourglass", 26, 18, 18, RED)
    files[hb + "muteoff.png"] = line_icon("microphone", 15, 18, 15)
    files[hb + "mute.png"] = line_icon("microphone-off", 15, 18, 15, RED)
    files[hb + "nosd.png"] = line_icon("device-sd-card", 15, 18, 15, RED)
    for rel, im in files.items():
        p = os.path.join(out, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        im.save(p, optimize=True)
    return sorted(files)


def _pad(im, w, h):
    c = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    c.alpha_composite(im, ((w - im.size[0]) // 2, (h - im.size[1]) // 2))
    return c


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "build", "icons")
    fl = build(out)
    print(f"{len(fl)} Icons nach {out}")
