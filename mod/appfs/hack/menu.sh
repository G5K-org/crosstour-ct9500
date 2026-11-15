#!/bin/sh
# Wird von main_app (neue Menüzeilen, src/menuhook.S) per system() aufgerufen:
#   menu.sh get <n>      Exit-Code = Zustand (0 = AUS, 1 = EIN)
#   menu.sh toggle <n>   umschalten, Exit-Code = neuer Zustand
# n: 0 = WLAN-Autostart, 1 = Heimnetz (sonst nur Kamera-WLAN), 2 = Telnet
#   menu.sh sync         Merker-Dateien $RUN/m_* schreiben (main_app liest nur diese,
#                        per access(), ohne Shell; Aufruf beim Start und nach toggle)
# Muss schnell sein und darf nie hängen (läuft im UI-Thread von main_app).
. /app/hack/lib.sh

state() {
    case "$1" in
        0) [ "$(cfg WIFI_AUTOSTART 0)" = 1 ] ;;
        1) [ "$(cfg WIFI_MODE auto)" != ap ] ;;
        2) [ "$(cfg TELNET 1)" = 1 ] ;;
        *) return 1 ;;
    esac
}

FLAGS="m_wlanauto m_heimnetz m_telnet"   # Index 0..2, Namen wie in src/menuhook.S
sync_flags() {
    n=0
    for f in $FLAGS; do
        if state $n; then : > $RUN/$f; else rm -f $RUN/$f; fi
        n=$((n + 1))
    done
}

case "$1" in
sync)
    sync_flags
    exit 0
    ;;
get)
    state "$2" && exit 1
    exit 0
    ;;
toggle)
    if state "$2"; then new=0; else new=1; fi
    case "$2" in
        0) cfg_set WIFI_AUTOSTART $new ;;
        1) if [ $new = 1 ]; then cfg_set WIFI_MODE auto; else cfg_set WIFI_MODE ap; fi ;;
        2) cfg_set TELNET $new
           if [ $new = 1 ]; then
               pidof telnetd >/dev/null || telnetd -l /bin/sh
           else
               killall telnetd 2>/dev/null
           fi ;;
        *) exit 0 ;;
    esac
    sync_flags
    log "Menü: Eintrag $2 -> $new"
    exit $new
    ;;
esac
exit 0
