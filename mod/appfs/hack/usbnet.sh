#!/bin/sh
# USB-Debugzugang: g_multi = RNDIS-Netzwerk + serielle Konsole (ACM) + leerer Wechseldatenträger.
#   usbnet.sh start   Module laden, usb0 = 192.168.7.1, DHCP für den PC, getty auf ttyGS0
#   usbnet.sh stop    alles wieder entladen
#   usbnet.sh status
#   usbnet.sh enabled  Exit 0, wenn der Debug-Modus eingeschaltet ist (Menü, schnell)
#   usbnet.sh on|off   Debug-Modus dauerhaft ein/aus (USB_DEBUG) und sofort starten/stoppen
#   usbnet.sh boot     beim Einschalten (start.sh): starten, wenn eingeschaltet
# Nur wenn main_app selbst kein USB-Gadget benutzt (USB-Modus "Laden"), sonst belegt
# g_webcam bzw. die Massenspeicher-Funktion den USB-Controller.
. /app/hack/lib.sh

KO=/app/komod
IP=192.168.7.1

start() {
    if lsmod | grep -q '^g_webcam\|^g_mass_storage'; then
        log "usbnet: USB-Controller belegt (Webcam/Speicher aktiv)"; echo busy; return 1
    fi
    lsmod | grep -q '^g_multi' || {
        for m in libcomposite u_ether usb_f_rndis u_serial usb_f_acm; do
            lsmod | grep -q "^$m " || insmod $KO/$m.ko || { log "usbnet: insmod $m fehlgeschlagen"; return 1; }
        done
        # feste MAC-Adressen -> der PC erkennt die Verbindung wieder; removable ohne Medium
        insmod $KO/g_multi.ko removable=1 luns=1 iProduct=CT9500-Debug \
            dev_addr=02:c7:95:00:00:01 host_addr=02:c7:95:00:00:02 || { log "usbnet: insmod g_multi fehlgeschlagen"; return 1; }
    }
    i=0; while [ ! -d /sys/class/net/usb0 ] && [ $i -lt 20 ]; do sleep 0.2; i=$((i+1)); done
    ifconfig usb0 $IP netmask 255.255.255.0 up
    cat > $RUN/udhcpd.usb.conf <<EOF
start		192.168.7.2
end		192.168.7.2
interface	usb0
max_leases	1
lease_file	$RUN/udhcpd.usb.leases
opt	subnet	255.255.255.0
opt	lease	86400
EOF
    touch $RUN/udhcpd.usb.leases
    ps | grep -q "[u]dhcpd.usb.conf" || /usr/sbin/udhcpd $RUN/udhcpd.usb.conf
    # Konsole auf der seriellen USB-Schnittstelle (respawn in eigener Schleife)
    if ! [ -f $RUN/usbgetty.pid ] || ! kill -0 "$(cat $RUN/usbgetty.pid)" 2>/dev/null; then
        ( while lsmod | grep -q '^g_multi'; do /sbin/getty -n -l /bin/sh 115200 ttyGS0 vt100; sleep 1; done ) &
        echo $! > $RUN/usbgetty.pid
    fi
    log "usbnet: gestartet ($IP)"
    echo ok
}

stop() {
    [ -f $RUN/usbgetty.pid ] && kill "$(cat $RUN/usbgetty.pid)" 2>/dev/null; rm -f $RUN/usbgetty.pid
    for p in $(ps | grep '[u]dhcpd.usb.conf' | awk '{print $1}'); do kill $p; done
    killall getty 2>/dev/null
    for m in g_multi usb_f_acm u_serial usb_f_rndis u_ether; do
        lsmod | grep -q "^$m " && rmmod $m
    done
    log "usbnet: gestoppt"
    echo ok
}

case "$1" in
enabled) [ "$(cfg USB_DEBUG 0)" = 1 ]; exit $? ;;
on) cfg_set USB_DEBUG 1; : > $RUN/m_usbdebug; start ;;
off) cfg_set USB_DEBUG 0; rm -f $RUN/m_usbdebug; stop ;;
boot)
    [ "$(cfg USB_DEBUG 0)" = 1 ] || { rm -f $RUN/m_usbdebug; exit 0; }
    : > $RUN/m_usbdebug      # Merker für das Menü (main_app liest ihn per access())
    sleep 8   # main_app hat sein USB-Gadget (falls doch Webcam/Speicher eingestellt) dann geladen
    start ;;
start) start ;;
stop) stop ;;
status) lsmod | grep -q '^g_multi' && echo on || echo off; ifconfig usb0 2>/dev/null | grep 'inet ' ;;
*) echo "usage: $0 start|stop|status|enabled|on|off|boot"; exit 1 ;;
esac
