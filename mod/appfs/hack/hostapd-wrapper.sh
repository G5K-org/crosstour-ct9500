#!/bin/sh
# Ersetzt /app/bin/hostapd. main_app ruft beim Einschalten des WLANs auf:
#   /app/bin/hostapd -e /app/bin/entropy.bin -B /dev/wifi/hostapd/hostapd.conf
# und danach /usr/sbin/udhcpd /app/udhcpd.conf; beim Ausschalten "killall hostapd udhcpd".
#
# WIFI_MODE=ap    -> Original-Zugangspunkt (aber mit WPA2/CCMP statt TKIP)
# WIFI_MODE=sta   -> nur Heimnetz
# WIFI_MODE=auto  -> Heimnetz versuchen, sonst Zugangspunkt (Standard, wenn SSID gesetzt)
#
# Dieser Prozess heißt "hostapd", damit main_app ihn per killall beenden kann.

. /app/hack/lib.sh
REAL=/app/hack/real/hostapd   # Prozessname muss "hostapd" bleiben (killall)
APCONF=""
for a in "$@"; do APCONF=$a; done          # letztes Argument = hostapd.conf

SSID=$(cfg STA_SSID)
MODE=$(cfg WIFI_MODE auto)
[ -z "$SSID" ] && MODE=ap
TIMEOUT=$(cfg STA_TIMEOUT 30)

# Zugangspunkt härten: WPA2 + CCMP (Original: WPA/WPA2 mit TKIP, ohne 802.11n)
harden_ap() {
    [ -f "$APCONF" ] || return
    sed -i 's/^wpa=3$/wpa=2/; s/^wpa_pairwise=.*/wpa_pairwise=CCMP/' "$APCONF"
    grep -q '^rsn_pairwise=' "$APCONF" || echo 'rsn_pairwise=CCMP' >> "$APCONF"
    s=$(cfg AP_SSID); p=$(cfg AP_PSK)
    [ -n "$s" ] && sed -i "s/^ssid=.*/ssid=$s/" "$APCONF"
    [ -n "$p" ] && sed -i "s/^wpa_passphrase=.*/wpa_passphrase=$p/" "$APCONF"
}

udhcpd_conf() {   # $1 = ap|off
    if [ "$1" = ap ]; then
        cat $HACK/udhcpd.conf.ap > $RUN/udhcpd.conf
    else
        # main_app startet udhcpd trotzdem; ohne gültiges Interface beendet er sich sofort
        echo "interface ct9500none" > $RUN/udhcpd.conf
    fi
}

start_ap() {
    log "WLAN: Zugangspunkt"
    echo ap > $RUN/wifi_state
    harden_ap
    udhcpd_conf ap
    $BB ip addr flush dev wlan0 2>/dev/null
    ifconfig wlan0 192.168.0.1 netmask 255.255.255.0 up
    $REAL "$@"
}

if [ "$MODE" = ap ]; then
    start_ap "$@"
    exit $?
fi

# ---------- Heimnetz ----------
udhcpd_conf off
PSK=$(cfg STA_PSK)
{
    echo "ctrl_interface=$RUN/wpa_ctrl"
    echo "network={"
    printf '    ssid="%s"\n' "$SSID"
    if [ -n "$PSK" ]; then printf '    psk="%s"\n    key_mgmt=WPA-PSK\n' "$PSK"; else echo "    key_mgmt=NONE"; fi
    echo "    scan_ssid=1"
    echo "}"
} > $RUN/wpa.conf
chmod 600 $RUN/wpa.conf

(
    sta_stop() {
        kill $(cat $RUN/wpa.pid 2>/dev/null) $(cat $RUN/udhcpc.pid 2>/dev/null) 2>/dev/null
        rm -f $RUN/wpa.pid $RUN/udhcpc.pid $RUN/sta_ip
    }
    trap 'sta_stop; log "WLAN: Heimnetz beendet"; echo off > $RUN/wifi_state; exit 0' TERM INT

    log "WLAN: verbinde mit '$SSID' (Modus $MODE)"
    echo connecting > $RUN/wifi_state
    $BB ip addr flush dev wlan0
    $BB ip link set wlan0 up
    $HACK/wpa_supplicant -i wlan0 -D nl80211 -c $RUN/wpa.conf > $RUN/wpa.log 2>&1 &
    echo $! > $RUN/wpa.pid

    i=0; ok=0
    while [ $i -lt $TIMEOUT ]; do
        if $HACK/wpa_cli -p $RUN/wpa_ctrl -i wlan0 status 2>/dev/null | grep -q '^wpa_state=COMPLETED'; then ok=1; break; fi
        sleep 1; i=$((i + 1))
    done

    if [ $ok = 0 ]; then
        log "WLAN: '$SSID' nicht erreichbar"
        sta_stop
        if [ "$MODE" = auto ]; then
            trap - TERM INT
            start_ap "$@"
            /usr/sbin/udhcpd /app/udhcpd.conf
        fi
        exit 0
    fi

    $BB udhcpc -i wlan0 -s $HACK/udhcpc.script -t 10 -T 2 -b -x hostname:ct9500 -p $RUN/udhcpc.pid >> $RUN/mod.log 2>&1
    echo sta > $RUN/wifi_state
    log "WLAN: verbunden, IP $(cat $RUN/sta_ip 2>/dev/null)"

    # Uhrzeit per NTP (Kamera hat keine gepufferte Uhr)
    if [ "$(cfg NTP 1)" = 1 ]; then
        sleep 3
        $BB timeout 20 $BB ntpd -n -q -p "$(cfg NTP_SERVER pool.ntp.org)" >> $RUN/mod.log 2>&1 && log "Zeit gestellt: $(date)"
    fi

    # Verbindung überwachen; bei Abbruch wieder verbinden lässt wpa_supplicant selbst
    while :; do sleep 1; done
) &
exit 0
