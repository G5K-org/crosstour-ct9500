#!/bin/sh
# CT9500-Mod: läuft in /app/bootapp VOR main_app. Muss schnell und fehlertolerant sein.
#
# Fehlt /app/userPara.bin (nach jedem Flashen von appfs), zeigt main_app die Sprachauswahl
# ("Guide") - und die stürzt im Original ab, wenn in den Parametern nicht Englisch steht.
# Darum die zuletzt gesicherte Datei (start.sh sichert sie bei jedem Start) zurücklegen.
P=/etc/ct9500mod
if [ ! -f /app/userPara.bin ]; then
    mkdir -p $P
    if [ -f $P/userPara.bin ]; then src=$P/userPara.bin; else src=/app/hack/userPara.default; fi
    cp $src /app/userPara.bin
    echo "$(date '+%F %T') userPara.bin aus $src angelegt" >> $P/preboot.log
fi
rm -f $P/restore_userpara $P/stream_request
exit 0
