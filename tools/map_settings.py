#!/usr/bin/env python3
"""Ermittelt, wo jeder Menüpunkt gespeichert wird (userPara.bin / param.bin).
Schaltet jeden Wert kurz um und stellt ihn danach wieder her."""
import os, sys, time, hashlib, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(__file__))
from camsh import run

H = os.environ.get("CT9500_HOST", "192.168.0.1")
SKIP = {"Factory Reset", "SD Format", "Wi-Fi", "Information", "Language"}


def cgi(cmd, **p):
    q = "&".join(f"-{k}={urllib.parse.quote(str(v))}" for k, v in p.items())
    return urllib.request.urlopen(f"http://{H}/cgi-bin/hi3510/{cmd}.cgi?{q}", timeout=10).read().decode()


def var(t, k):
    import re
    m = re.search(rf'var {k}="([^"]*)"', t)
    return m.group(1) if m else ""


def snap():
    out, _ = run("echo; sync; hexdump -v -e '1/1 \"%02x\"' /app/userPara.bin; echo; md5sum /app/param/param.bin /app/param/paramdef.bin; ls -la --full-time /app/param/ 2>/dev/null | grep bin")
    return out


def main():
    modes = sys.argv[1:] or ["NormalVideo", "NormalPhoto", "System"]
    for wm in modes:
        cur = var(cgi("getcurworkmode", act="get"), "workmode")
        if wm != "System" and cur != wm:
            cgi("setcurworkmode", act="set", workmode=wm); time.sleep(2)
        items = var(cgi("getprimarymenuitem", act="get", workmode=wm), "item").split(",")
        for name in items:
            if name in SKIP or not name:
                continue
            s = cgi("getsecondmenuitem", act="get", workmode=wm, name=name)
            val, opts = var(s, "value"), var(s, "item").split(",")
            if len(opts) < 2:
                continue
            other = next(o for o in opts if o != val)
            a = snap()
            r = cgi("setcurparameter", act="set", workmode=wm, name=name, value=other)
            time.sleep(1.5)
            b = snap()
            cgi("setcurparameter", act="set", workmode=wm, name=name, value=val)
            time.sleep(1)
            ua, ub = a.split("\n")[1].strip(), b.split("\n")[1].strip()
            diff = [i for i in range(min(len(ua), len(ub)) // 2) if ua[2*i:2*i+2] != ub[2*i:2*i+2]]
            pchg = a.split("\n")[2] != b.split("\n")[2]
            print(f"{wm:12} {name:24} {val:>10} -> {other:<10} {r.strip()[:8]:8} userPara:{[(i, ua[2*i:2*i+2], ub[2*i:2*i+2]) for i in diff]} param.bin:{'GEÄNDERT' if pchg else '-'}", flush=True)


if __name__ == "__main__":
    main()
