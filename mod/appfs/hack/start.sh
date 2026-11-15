#!/bin/sh
# CT9500-Mod: wird von /app/bootapp nach dem Start von main_app aufgerufen.
# Defensiv: Fehler hier dürfen den normalen Kamerabetrieb nie stören.
. /app/hack/lib.sh
log "Mod $MODVER startet"

# Loopback ist im Original nicht aktiv (die Weboberfläche spricht main_app über 127.0.0.1 an)
ifconfig lo 127.0.0.1 up

# DNS für Programme der Mod (musl liest /etc/resolv.conf)
touch $RUN/resolv.conf
[ -e /etc/resolv.conf ] || touch /etc/resolv.conf 2>/dev/null
mount --bind $RUN/resolv.conf /etc/resolv.conf 2>/dev/null

# devpts für Telnet
if [ ! -e /dev/pts/ptmx ]; then
    mkdir -p /dev/pts
    mount -t devpts devpts /dev/pts
fi

# Auf die SD-Karte warten (main_app mountet sie nach /app/sd)
i=0
while [ $i -lt 30 ] && ! sd_mounted; do sleep 1; i=$((i + 1)); done

if sd_mounted; then
    # Nach einem OTA-Update ist die Flash-Konfiguration weg: aus SD-Sicherung holen
    [ -f $CONF ] || { [ -f $SDBAK ] && cp $SDBAK $CONF && log "Konfiguration aus SD-Sicherung wiederhergestellt"; }

    # Update-Dateien im SD-Wurzelverzeichnis entfernen, sobald sie installiert sind
    if [ -f $SD/config ]; then
        want=$(sed -n "s/^setenv swverv2 '\(.*\)'.*/\1/p" $SD/config)
        if [ -n "$want" ] && [ "$want" = "$(installed_swver)" ]; then
            for f in config appfs.jffs2 rootfs.jffs2 uImage media_app_zip.bin rawparam rawparambak ota.tar; do
                rm -f $SD/$f
            done
            log "Update $want installiert, Update-Dateien von SD entfernt"
        fi
    fi
fi

# userPara.bin (Crosstour-Einstellungen inkl. "Sprachauswahl erledigt") sichern, damit
# preboot.sh sie nach dem nächsten Flashen zurücklegen kann. Nur sichern, wenn die
# Sprachauswahl erledigt ist (Byte 29 = 1), sonst würde der Zustand "Guide" gesichert.
(
    sleep 20
    if [ -f /app/userPara.bin ] && [ "$(hexdump -s 29 -n 1 -e '1/1 "%u"' /app/userPara.bin)" = 1 ]; then
        cmp -s /app/userPara.bin $PERSIST/userPara.bin || { cp /app/userPara.bin $PERSIST/userPara.bin && log "userPara.bin gesichert"; }
    fi
) &

# Telnet (Port 23, ohne Passwort!) nur wenn eingeschaltet
if [ "$(cfg TELNET 1)" = 1 ]; then
    telnetd -l /bin/sh
fi

# USB-Debugzugang (Netzwerk + Konsole über USB), wenn im Menü "USB-Modus: Debug" gewählt
$HACK/usbnet.sh boot > /dev/null 2>&1 &

# Weboberfläche auf Port 8081
pw=$(cfg WEB_PASS)
if [ -n "$pw" ]; then echo "/:admin:$pw" > $RUN/httpd.conf; else : > $RUN/httpd.conf; fi
chmod 600 $RUN/httpd.conf
$BB httpd -p 8081 -h $HACK/www -c $RUN/httpd.conf

# WLAN beim Einschalten automatisch an. main_app kann das selbst nicht; über die
# Tasten-Schnittstelle (sendclickkey KEY_BACK) schaltet der Startbildschirm das WLAN um.
# Die Taste schaltet um, darum nur klicken, wenn das WLAN wirklich aus ist.
if [ "$(cfg WIFI_AUTOSTART 0)" = 1 ] && [ "$(hexdump -s 29 -n 1 -e '1/1 "%u"' /app/userPara.bin 2>/dev/null)" = 1 ]; then
    (
        G="http://127.0.0.1/cgi-bin/hi3510/getwifi.cgi?-act=get"
        wifi_on() {
            case "$(cat $RUN/wifi_state 2>/dev/null)" in ap|sta|connecting) return 0 ;; esac
            wget -q -T 5 -O - "$G" 2>/dev/null | grep -q 'enablewifi="1"'
        }
        i=0   # warten, bis main_app antwortet
        while [ $i -lt 60 ] && ! wget -q -T 3 -O /dev/null "$G" 2>/dev/null; do sleep 1; i=$((i + 1)); done
        sleep 5   # Startbildschirm fertig aufbauen lassen
        n=0
        while [ $n -lt 2 ] && ! wifi_on; do
            wget -q -T 5 -O /dev/null "http://127.0.0.1/cgi-bin/hi3510/sendclickkey.cgi?-act=set&-type=KEY_BACK"
            log "WLAN-Autostart: Tastendruck gesendet"
            sleep 20; n=$((n + 1))
        done
        wifi_on && log "WLAN-Autostart: WLAN ist an"
    ) &
fi

# Notfallmodus: Hat main_app nach 60 s die SD-Karte nicht eingebunden oder antwortet nicht,
# Karte selbst einbinden, Diagnose schreiben und WLAN (Heimnetz/Zugangspunkt) selbst starten.
# So bleibt die Kamera per Telnet/Weboberfläche erreichbar, auch wenn main_app hängt.
(
    i=0
    while [ $i -lt 60 ]; do
        sd_mounted && wget -q -T 3 -O /dev/null "http://127.0.0.1/cgi-bin/hi3510/getdeviceattr.cgi?-act=get" 2>/dev/null && exit 0
        sleep 1; i=$((i + 1))
    done
    log "NOTFALL: main_app antwortet nicht oder SD fehlt"
    if ! sd_mounted; then
        [ -b /dev/mmcblk0p1 ] || sh /app/komod/mmc_load.sh >/dev/null 2>&1
        j=0; while [ $j -lt 10 ] && [ ! -b /dev/mmcblk0p1 ]; do sleep 1; j=$((j + 1)); done
        mount -t vfat /dev/mmcblk0p1 $SD 2>/dev/null && log "NOTFALL: SD selbst eingebunden"
    fi
    if sd_mounted; then
        D=$SD/CT9500MOD/notfall; mkdir -p $D
        ps > $D/ps.txt; dmesg > $D/dmesg.txt; cat /proc/mounts > $D/mounts.txt
        cp $RUN/mod.log $D/mod.log 2>/dev/null; sync
    fi
    if ! ifconfig wlan0 >/dev/null 2>&1; then
        sh /app/open_wifi.sh >/dev/null 2>&1; sleep 5
    fi
    if [ ! -f /dev/wifi/hostapd/hostapd.conf ]; then   # sonst schreibt main_app die Datei
        mkdir -p /dev/wifi/hostapd
        printf 'interface=wlan0\ndriver=nl80211\nctrl_interface=/dev/wifi/hostapd\nssid=CT9500-NOTFALL\nchannel=6\nhw_mode=g\nieee80211n=1\nwpa=2\nwpa_key_mgmt=WPA-PSK\nwpa_pairwise=CCMP\nwpa_passphrase=12345678\n' > /dev/wifi/hostapd/hostapd.conf
    fi
    case "$(cat $RUN/wifi_state 2>/dev/null)" in
        ap|sta|connecting) ;;
        *) log "NOTFALL: starte WLAN selbst"
           /app/bin/hostapd -e /app/bin/entropy.bin -B /dev/wifi/hostapd/hostapd.conf ;;
    esac
    sleep 30
    if sd_mounted; then cp $RUN/mod.log $SD/CT9500MOD/notfall/mod.log 2>/dev/null; dmesg > $SD/CT9500MOD/notfall/dmesg2.txt; sync; fi
) &

# Optionales Benutzerskript auf der SD-Karte (wartet ggf. auf den Notfallmodus)
(
    i=0; while [ $i -lt 75 ] && ! sd_mounted; do sleep 1; i=$((i + 1)); done
    if sd_mounted && [ -f $SD/autorun.sh ]; then
        sh $SD/autorun.sh > $SD/autorun.log 2>&1
    fi
) &
log "Mod bereit"
