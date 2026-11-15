#!/bin/sh
# Auf der Kamera: Tasten-Protokoll (src/menuhook.S, keylog) aus main_app lesen.
#   keylog.sh <adresse_hex>     z. B. keylog.sh 4207d0
# Ausgabe: Nr Art(1=down,2=up) hWidget Taste lParam
A=$((0x$1)); P=$(pidof main_app)
dd if=/proc/$P/mem bs=8 skip=$((A / 8)) count=129 2>/dev/null | hexdump -v -e '4/4 "%08x " "\n"' |
awk 'NR==1 { n = strtonum("0x" $1); next } { print }' > /dev/null 2>&1
# busybox awk kennt kein strtonum -> Ausgabe roh, Auswertung auf dem PC
dd if=/proc/$P/mem bs=8 skip=$((A / 8)) count=129 2>/dev/null | hexdump -v -e '4/4 "%08x " "\n"'
