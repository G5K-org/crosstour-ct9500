#!/usr/bin/env python3
"""Steuerung der Crosstour CT9500 (Firmware V4.1.0.2-A) über WLAN.

Mit dem Kamera-WLAN verbinden (SSID CT9500_xxxxxx, Passwort 12345678), dann z.B.:
  ct9500.py status
  ct9500.py rec start | rec stop
  ct9500.py photo
  ct9500.py mode NormalVideo|Loop Video|VideoLapse|SlowRec|NormalPhoto|TimerPhoto|Burst
  ct9500.py settings [Modus]          # alle Menüpunkte mit Optionen
  ct9500.py set "Encode Mode" H265 [--mode NormalVideo]
  ct9500.py files                     # Dateien auf der SD-Karte
  ct9500.py download [ZIEL] [--all]   # neueste (oder alle) Dateien laden
  ct9500.py live                      # Livebild mit mpv/ffplay
  ct9500.py synctime                  # Uhrzeit vom PC übernehmen
  ct9500.py raw getwifi               # beliebigen CGI-Befehl aufrufen
"""
import argparse, datetime, html.parser, os, re, shutil, subprocess, sys
import urllib.parse, urllib.request

HOST = os.environ.get("CT9500_HOST", "192.168.0.1")
CGI = f"http://{HOST}/cgi-bin/hi3510"
RTSP = f"rtsp://{HOST}/livestream/12"
DCIM = "/sd/DCIM/"
ERRORS = {"-5555": "Parameter fehlt/falsch", "-4444": "unbekannter Modus",
          "-2222": "unbekannter Typ"}


def cgi(command, act="get", **params):
    q = "&".join([f"-act={act}"] + [f"-{k}={urllib.parse.quote(str(v))}" for k, v in params.items()])
    with urllib.request.urlopen(f"{CGI}/{command}.cgi?{q}", timeout=10) as r:
        text = r.read().decode("utf-8", "replace").strip()
    m = re.search(r'SvrFuncResult="([^"]*)"', text)
    if m:
        raise SystemExit(f"Fehler bei {command}: {m.group(1)} ({ERRORS.get(m.group(1), '?')})")
    return text


def parse(text):
    return dict(re.findall(r'var (\w+)="([^"]*)"', text))


def menu(mode):
    p = parse(cgi("getprimarymenuitem", workmode=mode))
    out = []
    for name in p.get("item", "").split(","):
        if not name:
            continue
        try:
            s = parse(cgi("getsecondmenuitem", workmode=mode, name=name))
            out.append((name, s.get("value", ""), s.get("item", "").split(",")))
        except SystemExit:
            out.append((name, "", []))
    return out


class _Links(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href", "")
            if href and not href.endswith(("./", "../")):
                self.links.append(href)


def ls(path):
    with urllib.request.urlopen(f"http://{HOST}{path}", timeout=10) as r:
        p = _Links(); p.feed(r.read().decode("utf-8", "replace"))
    return p.links


def all_files():
    files = []
    for d in ls(DCIM):
        if d.endswith("/"):
            files += [f for f in ls(d) if not f.endswith("/")]
    return sorted(files)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("rec").add_argument("action", choices=["start", "stop"])
    sub.add_parser("photo")
    sub.add_parser("mode").add_argument("workmode")
    sub.add_parser("settings").add_argument("workmode", nargs="?")
    s = sub.add_parser("set"); s.add_argument("name"); s.add_argument("value"); s.add_argument("--mode")
    sub.add_parser("files")
    d = sub.add_parser("download"); d.add_argument("dest", nargs="?", default="."); d.add_argument("--all", action="store_true")
    sub.add_parser("live")
    sub.add_parser("synctime")
    r = sub.add_parser("raw"); r.add_argument("command"); r.add_argument("params", nargs="*", help="key=value"); r.add_argument("--set", action="store_true")
    a = ap.parse_args()

    if a.cmd == "status":
        dev, st = parse(cgi("getdeviceattr")), parse(cgi("getworkstate"))
        mode, sd = parse(cgi("getcurworkmode")), parse(cgi("getsdstate"))
        cnt, t = parse(cgi("getfiletypecount")), parse(cgi("getsystime"))
        rec = "JA" + (f" ({st['time']} s)" if "time" in st else "") if st.get("running") == "true" else "nein"
        print(f"{dev.get('name')}  {dev.get('softversion')}  ({dev.get('type')})")
        print(f"Modus:     {mode.get('workmode')}  [{st.get('workmode')}]   Aufnahme läuft: {rec}")
        print(f"SD-Karte:  {sd.get('sdstate')}  belegt {sd.get('used')} von {sd.get('total')}")
        print(f"Dateien:   {cnt.get('videocount')} Videos, {cnt.get('imagecount')} Fotos")
        print(f"Kamerazeit: {t.get('time')}")
    elif a.cmd == "rec":
        print(cgi("workmodecmd", "set", cmd=a.action))
    elif a.cmd == "photo":
        cur = parse(cgi("getcurworkmode")).get("workmode")
        if cur not in ("NormalPhoto", "TimerPhoto", "Burst"):
            cgi("setcurworkmode", "set", workmode="NormalPhoto")
        print(cgi("workmodecmd", "set", cmd="start"))
        if cur not in ("NormalPhoto", "TimerPhoto", "Burst"):
            import time; time.sleep(2); cgi("setcurworkmode", "set", workmode=cur)
    elif a.cmd == "mode":
        print(cgi("setcurworkmode", "set", workmode=a.workmode))
    elif a.cmd == "settings":
        modes = [a.workmode] if a.workmode else [parse(cgi("getcurworkmode"))["workmode"], "System"]
        for m in modes:
            print(f"[{m}]")
            for name, val, opts in menu(m):
                print(f"  {name:24} = {val:12} {'(' + ', '.join(opts) + ')' if len(opts) > 1 else ''}")
    elif a.cmd == "set":
        mode = a.mode or parse(cgi("getcurworkmode"))["workmode"]
        print(cgi("setcurparameter", "set", workmode=mode, name=a.name, value=a.value))
        print(parse(cgi("getsecondmenuitem", workmode=mode, name=a.name)).get("value"))
    elif a.cmd == "files":
        for f in all_files():
            print(f"http://{HOST}{f}")
    elif a.cmd == "download":
        files = all_files()
        for f in (files if a.all else files[-1:]):
            dst = os.path.join(a.dest, os.path.basename(f))
            print(f"{f} -> {dst}")
            urllib.request.urlretrieve(f"http://{HOST}{f}", dst)
    elif a.cmd == "live":
        player = next((p for p in ("mpv", "ffplay", "vlc") if shutil.which(p)), None)
        if not player:
            sys.exit(f"Kein Player gefunden. Stream: {RTSP}")
        args = {"mpv": ["mpv", "--rtsp-transport=tcp", "--profile=low-latency", RTSP],
                "ffplay": ["ffplay", "-rtsp_transport", "tcp", "-fflags", "nobuffer", RTSP],
                "vlc": ["vlc", RTSP]}[player]
        subprocess.run(args)
    elif a.cmd == "synctime":
        now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        print(cgi("setsystime", "set", time=now)); print(parse(cgi("getsystime")))
    elif a.cmd == "raw":
        params = dict(p.split("=", 1) for p in a.params)
        print(cgi(a.command.removesuffix(".cgi"), "set" if a.set else "get", **params))


if __name__ == "__main__":
    main()
