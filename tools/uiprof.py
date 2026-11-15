#!/usr/bin/env python3
"""Auswertung von src/uiprof.c: welche main_app-Funktionen warten/laufen wie oft.

  tools/uiprof.py profil.txt [thread-filter]
Für jede Probe eines blockierten Threads wird die erste Adresse im Stack, die direkt hinter
einem BL liegt (echte Rücksprungadresse), einer Funktion zugeordnet; dazu die Kette der
ersten 4 solcher Adressen.
"""
import collections, os, re, struct, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(ROOT, "firmware/fs/appfs/bin/main_app")


def symbols():
    out = subprocess.run(["readelf", "-sW", MAIN], capture_output=True, text=True).stdout
    syms = []
    for l in out.splitlines():
        p = l.split()
        if len(p) >= 8 and p[3] == "FUNC" and int(p[2]) > 0:
            syms.append((int(p[1], 16), int(p[2]), p[7]))
    syms.sort()
    return syms


def main():
    syms = symbols()
    starts = [s[0] for s in syms]
    data = open(MAIN, "rb").read()
    import bisect

    def fn(a):
        i = bisect.bisect_right(starts, a) - 1
        if i >= 0 and syms[i][0] <= a < syms[i][0] + syms[i][1]:
            return syms[i][2]
        return None

    def is_ret(a):   # Instruktion davor ist BL/BLX
        o = a - 4 - 0x10000
        if o < 0 or o + 4 > len(data):
            return False
        w = struct.unpack_from("<I", data, o)[0]
        return (w & 0x0F000000) == 0x0B000000 or (w & 0x0FFFFFF0) == 0x012FFF30

    flt = sys.argv[2] if len(sys.argv) > 2 else None
    count, chains, states = collections.Counter(), collections.Counter(), collections.Counter()
    samples = 0
    for line in open(sys.argv[1]):
        p = line.split()
        if len(p) < 4 or not p[0].isdigit():
            continue
        if flt and not re.search(flt, p[2]):
            continue
        samples += 1
        if p[3] == "running":
            states[(p[2], "running")] += 1
            continue
        rets = [int(x, 16) for x in p[5:] if is_ret(int(x, 16))]
        names = []
        for a in rets:
            n = fn(a - 4)
            if n and (not names or names[-1] != n):
                names.append(n)
        states[(p[2], f"sys{p[3]}")] += 1
        if names:
            count[(p[2], names[0])] += 1
            chains[(p[2], " < ".join(names[:5]))] += 1
    print(f"{samples} Proben")
    print("\n== Zustände je Thread")
    for (t, s), n in states.most_common(25):
        print(f"{n:5}  {t:18} {s}")
    print("\n== Ketten (innerste zuerst)")
    for (t, c), n in chains.most_common(25):
        print(f"{n:5}  {t:18} {c}")


if __name__ == "__main__":
    main()
