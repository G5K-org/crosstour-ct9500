#!/bin/sh
# Gemeinsame Funktionen der CT9500-Mod. Wird per "." eingebunden.

HACK=/app/hack
BB=$HACK/busybox
RUN=/dev/ct9500mod                  # RAM (devtmpfs), existiert ab Boot
SD=/app/sd
PERSIST=/etc/ct9500mod              # rootfs-Partition: übersteht appfs-Updates
CONF=$PERSIST/ct9500mod.conf        # Einstellungen (Weboberfläche)
SDCONF=$SD/wifi.conf                # optionale Überschreibung auf der SD-Karte
SDBAK=$SD/CT9500MOD/ct9500mod.conf  # Sicherung (übersteht OTA-Updates)
MODVER=$(cat $HACK/VERSION 2>/dev/null)

mkdir -p $RUN
[ -d $PERSIST ] || mkdir -p $PERSIST 2>/dev/null
# Umzug aus M2 (dort lag die Konfiguration in appfs)
[ -f /app/private/ct9500mod.conf ] && [ ! -f $CONF ] && mv /app/private/ct9500mod.conf $CONF 2>/dev/null

log() { echo "$(date '+%F %T') $*" >> $RUN/mod.log; }

# Wert aus einer KEY="VALUE"-Datei lesen (ohne die Datei auszuführen)
cfg_file_get() {
    [ -f "$2" ] || return 1
    sed -n "s/^$1=\"\(.*\)\"[[:space:]]*\$/\1/p; s/^$1=\([^\"]*\)\$/\1/p" "$2" | tail -1 |
        sed 's/\\"/"/g; s/\\\\/\\/g'
}

# Effektiven Wert holen: SD-Datei > Flash-Konfiguration > Standardwert
cfg() {
    v=$(cfg_file_get "$1" "$SDCONF")
    [ -n "$v" ] || v=$(cfg_file_get "$1" "$CONF")
    [ -n "$v" ] || v=$2
    echo "$v"
}

# Wert in die Flash-Konfiguration schreiben (und auf SD sichern)
cfg_set() {
    key=$1
    val=$(printf '%s' "$2" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr -d '\n\r')
    touch $CONF
    grep -v "^$key=" $CONF > $CONF.tmp 2>/dev/null
    printf '%s="%s"\n' "$key" "$val" >> $CONF.tmp
    mv $CONF.tmp $CONF
    chmod 600 $CONF
    cfg_backup
}

cfg_backup() {
    if grep -q " $SD " /proc/mounts 2>/dev/null; then
        mkdir -p $SD/CT9500MOD && cp $CONF $SDBAK 2>/dev/null
    fi
}

sd_mounted() { grep -q " $SD " /proc/mounts 2>/dev/null; }

# Installierter Versionscode (u-boot-Umgebung im Flash)
installed_swver() {
    strings /dev/mtd0 2>/dev/null | sed -n 's/^swverv2=//p' | tail -1
}
