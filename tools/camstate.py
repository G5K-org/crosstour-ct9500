#!/usr/bin/env python3
"""Kamera-Einstellungen vor Tests sichern und danach wiederherstellen.

  tools/camstate.py save  <datei>
  tools/camstate.py restore <datei>
Gesichert: aktueller Modus, alle Menüpunkte (getprimarymenuitem) für Video und Foto, WLAN an/aus.
"""
import json, os, re, sys, time, urllib.parse, urllib.request

HOST = os.environ.get("CT9500_HOST", "192.168.7.1")


def cgi(cmd, **p):
    q = "&".join(f"-{k}={urllib.parse.quote(str(v))}" for k, v in p.items())
    return urllib.request.urlopen(f"http://{HOST}/cgi-bin/hi3510/{cmd}.cgi?{q}", timeout=10).read().decode()


def var(t, n):
    m = re.search(rf'var {n}="([^"]*)"', t)
    return m.group(1) if m else ""


def save(path):
    st = {"workmode": var(cgi("getcurworkmode", act="get"), "workmode"),
          "wifi": var(cgi("getwifi", act="get"), "enablewifi"), "params": {}}
    for wm in ("NormalVideo", "NormalPhoto"):
        t = cgi("getprimarymenuitem", act="get", workmode=wm)
        st["params"][wm] = dict(zip(var(t, "item").split(","), var(t, "cur").split(",")))
    json.dump(st, open(path, "w"), indent=1)
    print("gesichert:", st)


def restore(path):
    st = json.load(open(path))
    now = save.__wrapped__ if hasattr(save, "__wrapped__") else None
    for wm, items in st["params"].items():
        t = cgi("getprimarymenuitem", act="get", workmode=wm)
        cur = dict(zip(var(t, "item").split(","), var(t, "cur").split(",")))
        for k, v in items.items():
            if cur.get(k) != v:
                print(f"zurück: {wm} {k}: {cur.get(k)} -> {v}", cgi("setcurparameter", act="set", workmode=wm, name=k, value=v).strip())
    if var(cgi("getcurworkmode", act="get"), "workmode") != st["workmode"]:
        print("Modus zurück:", cgi("setcurworkmode", act="set", workmode=st["workmode"]).strip())
    if var(cgi("getwifi", act="get"), "enablewifi") != st["wifi"]:
        print("WARNUNG: WLAN-Zustand abweichend (soll %s) - bitte prüfen" % st["wifi"])
    print("Wiederherstellung fertig")


if __name__ == "__main__":
    {"save": save, "restore": restore}[sys.argv[1]](sys.argv[2])
