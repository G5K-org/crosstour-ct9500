#!/bin/sh
# Auf der Kamera: Tastendruck per CGI auslösen und messen, wann sich das Display (fb0) ändert.
#   uilatency.sh KEY_MENU [n]
# Gibt pro Durchgang die Millisekunden bis zur ersten Bildänderung und bis zum Ende des
# Neuzeichnens (keine Änderung mehr für 300 ms) aus.
KEY=${1:-KEY_MENU}; N=${2:-3}
ms() { read up _ < /proc/uptime; echo "${up%.*}${up#*.}0"; }   # Hundertstel -> ms
sum() { md5sum < /dev/fb0 | cut -c1-8; }
i=0
while [ $i -lt $N ]; do
    before=$(sum); t0=$(ms)
    wget -q -T 5 -O /dev/null "http://127.0.0.1/cgi-bin/hi3510/sendclickkey.cgi?-act=set&-type=$KEY" &
    first=""; last=$t0; prev=$before
    while :; do
        now=$(ms); s=$(sum)
        if [ "$s" != "$prev" ]; then [ -z "$first" ] && first=$((now - t0)); last=$now; prev=$s; fi
        [ $((now - last)) -gt 300 ] && [ -n "$first" ] && break
        [ $((now - t0)) -gt 4000 ] && break
    done
    echo "$KEY: erste Änderung ${first:-keine} ms, fertig $((last - t0)) ms"
    sleep 1; i=$((i + 1))
done
