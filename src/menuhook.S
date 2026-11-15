@ CT9500-Mod: zusätzliche Zeilen im Einstellungsmenü (SYSTEM_SET).
@ Liegt in einem eigenen Segment (siehe tools/elfseg.py). ARM-Modus, AAPCS.
@
@ Neue Zeilen (higv.bin, tools/higv_addrows.py):  Button / Label / Wert
@   Index 0: 1121 / 1122 / 1123   WLAN-Autostart
@   Index 1: 1124 / 1125 / 1126   Heimnetz
@   Index 2: 1127 / 1128 / 1129   Telnet
@   Index 3: 1130 / 1131 / 1132   USB-Modus (Standard beim Einstecken)
@ Werte der Zeilen 0-2 liefert /app/hack/menu.sh (Exit-Code 0 = AUS, 1 = EIN).
@ Zeile 3 benutzt direkt die Parameterverwaltung von main_app:
@   HI_PDT_PARAM_Get/SetCommParam(HI_PDT_PARAM_TYPE_USB_MODE = 30, &wert)
@   wert: 0 = Laden, 1 = UVC (PC-Kamera), 2 = Massenspeicher
@   Anzeige-Wert 3 = Debug: für main_app "Laden" (kein eigenes Gadget), dazu startet
@   /app/hack/usbnet.sh das g_multi-Gadget (USB-Netzwerk + Konsole). Merker USB_DEBUG.
@   SetCommParam setzt das Speicher-Flag -> landet wie jede Einstellung im rawparam.
@   PDT_UI_COMM_EnableUSB() liest den Wert und ruft HI_USB_SetMode (wie beim Boot).

    .equ ORIG_ONSHOW,      0x0007c13c   @ SYSTEM_SET_onshow
    .equ ORIG_KEYDOWN,     0x00087bb4   @ SYSTEM_SET_button_onkeydown
    .equ SYSTEM,           0x0001a844   @ system@plt
    .equ SETTEXTBYID,      0x001b9620   @ HI_GV_Widget_SetTextByID(handle, strID)
    .equ PAINT,            0x001b8efc   @ HI_GV_Widget_Paint(handle, rect)
    .equ KEY_OK,           0x0001003a
    .equ FIRST_BTN,        1121
    .equ NROWS,            3            @ Zeilen über menu.sh
    .equ USB_ROW,          3            @ Zeilenindex USB-Modus
    .equ GETCOMM,          0x000250b0   @ HI_PDT_PARAM_GetCommParam(type, void *out)
    .equ SETCOMM,          0x00027514   @ HI_PDT_PARAM_SetCommParam(type, void *in)
    .equ ENABLEUSB,        0x00059ecc   @ PDT_UI_COMM_EnableUSB(void)
    .equ PT_USB_MODE,      30
    .equ ACCESS,           0x0001a5e0   @ access@plt
    .equ STARTWINDOW,      0x00074c64   @ PDT_UI_WINMNG_StartWindow(handle, flag)
    .equ SETSKIN,          0x001b8fc8   @ HI_GV_Widget_SetSkin(handle, type, skin)
    .equ STR_OFF,          183          @ Sprachtext "AUS"/"OFF"
    .equ STR_ON,           184          @ Sprachtext "EIN"/"ON"

    .text
    .arm
    .global hook_onshow, hook_keydown, hook_usbwin, pwr_usb_pause, pwr_resume, rows_btn, rows_lbl, rows_val, rows_btn_rev, rows_lbl_rev, rows_val_rev

@ ---------------------------------------------------------------- set_label(idx=r0, state=r1)
set_label:
    push    {r4, lr}
    mov     r2, #3
    mul     r4, r0, r2
    ldr     r2, =FIRST_BTN + 2
    add     r4, r4, r2              @ Wert-Handle = 1123 + 3*idx
    cmp     r1, #1
    ldreq   r1, =STR_ON
    ldrne   r1, =STR_OFF
    mov     r0, r4
    bl      SETTEXTBYID
    mov     r0, r4
    mov     r1, #0
    bl      PAINT
    pop     {r4, pc}

@ ---------------------------------------------------------------- run_menu(cmd_table=r0, idx=r1) -> state
run_menu:
    push    {r4, lr}
    ldr     r0, [r0, r1, lsl #2]    @ Befehlsstring
    bl      SYSTEM
    cmn     r0, #1                  @ -1 = Fehler
    moveq   r0, #0
    lsr     r0, r0, #8              @ Exit-Code
    and     r0, r0, #0xff
    cmp     r0, #1
    movne   r0, #0
    pop     {r4, pc}

@ ---------------------------------------------------------------- refresh_all()
refresh_all:                            @ Zustände aus Merker-Dateien (menu.sh sync), ohne Shell
    push    {r4, lr}
    mov     r4, #0
1:  ldr     r0, =st_paths
    ldr     r0, [r0, r4, lsl #2]
    mov     r1, #0                  @ F_OK
    bl      ACCESS
    cmp     r0, #0
    moveq   r0, #1                  @ Datei da = EIN
    movne   r0, #0
    mov     r1, r0
    mov     r0, r4
    bl      set_label
    add     r4, r4, #1
    cmp     r4, #NROWS
    blt     1b
    bl      usb_get
    bl      usb_label
    pop     {r4, pc}

@ ---------------------------------------------------------------- usb_get() -> 0..3
usb_get:
    push    {r4, lr}
    sub     sp, sp, #8
    mov     r0, #2                  @ Vorgabe Massenspeicher, falls Lesen scheitert
    str     r0, [sp]
    mov     r0, #PT_USB_MODE
    mov     r1, sp
    bl      GETCOMM
    ldr     r4, [sp]
    cmp     r4, #2
    movhi   r4, #2
    cmp     r4, #0                  @ "Laden": Debug-Merker abfragen
    bne     1f
    ldr     r0, =s_st_usbdbg
    mov     r1, #0
    bl      ACCESS
    cmp     r0, #0                  @ Merker-Datei da = Debug eingeschaltet
    moveq   r4, #3
1:  mov     r0, r4
    add     sp, sp, #8
    pop     {r4, pc}

@ ---------------------------------------------------------------- usb_label(wert=r0)
usb_label:
    push    {r4, lr}
    ldr     r1, =usb_str
    ldr     r1, [r1, r0, lsl #2]
    ldr     r4, =FIRST_BTN + 3 * USB_ROW + 2
    mov     r0, r4
    bl      SETTEXTBYID
    mov     r0, r4
    mov     r1, #0
    bl      PAINT
    pop     {r4, pc}

@ ---------------------------------------------------------------- usb_toggle(): Speicher -> PC-Kamera -> Laden -> Debug -> Speicher
usb_toggle:
    push    {r4, r5, r6, lr}
    sub     sp, sp, #8
    bl      usb_get
    mov     r5, r0                  @ bisher
    ldr     r1, =usb_next
    ldr     r4, [r1, r0, lsl #2]    @ neu
    cmp     r4, #3
    bne     1f
    ldr     r0, =s_dbg_on            @ Laden -> Debug: main_app bleibt auf "Laden"
    bl      SYSTEM
    b       2f
1:  cmp     r5, #3
    bne     3f
    ldr     r0, =s_dbg_off           @ Debug -> Speicher: erst g_multi freigeben
    bl      SYSTEM
3:  str     r4, [sp]
    mov     r0, #PT_USB_MODE
    mov     r1, sp
    bl      SETCOMM
    bl      ENABLEUSB
2:  mov     r0, r4
    bl      usb_label
    add     sp, sp, #8
    pop     {r4, r5, r6, pc}

usb_next:   .word 3, 0, 1, 2        @ Laden->Debug, PC-Kamera->Laden, Speicher->PC-Kamera, Debug->Speicher
s_st_usbdbg: .asciz "/dev/ct9500mod/m_usbdebug"
s_st0:      .asciz "/dev/ct9500mod/m_wlanauto"
s_st1:      .asciz "/dev/ct9500mod/m_heimnetz"
s_st2:      .asciz "/dev/ct9500mod/m_telnet"
    .balign 4
st_paths:   .word s_st0, s_st1, s_st2
s_dbg_on:   .asciz "/app/hack/usbnet.sh on >/dev/null 2>&1"
s_dbg_off:  .asciz "/app/hack/usbnet.sh off >/dev/null 2>&1"
    .balign 4

@ ---------------------------------------------------------------- hook_usbwin(r0=176, r1=1)
@ Ersetzt in PDT_UI_COMM_LCDEventProc (Ereignis 0x11700000 = Zustand gewechselt) den Aufruf
@ "bl PDT_UI_WINMNG_StartWindow" für das USB-Fenster 176. Das Original zeigt dort immer den
@ statischen Inhalt aus higv.bin (Massenspeicher-Bild/-Text), auch im UVC-Zustand.
@ Neuer Zustand steht im Ereignis: [fp-584] -> Ereignis, +8 = Zustand (10 = UVC, 11 = Speicher).
@ Bild/Text wie USB_CONNECTING_onkeydown: UVC = Text 397 + Skin 349, Speicher = Text 396 + Skin 178.
hook_usbwin:
    ldr     r3, [fp, #-584]         @ fp gehört noch dem Aufrufer
    ldr     r3, [r3, #8]
    push    {r4, r5, r6, lr}
    mov     r5, r3
    bl      STARTWINDOW
    mov     r4, r0                  @ Rückgabewert für den Aufrufer
    cmp     r5, #10
    moveq   r1, #397
    movne   r1, #396
    moveq   r6, #349
    movne   r6, #178
    mov     r0, #179
    bl      SETTEXTBYID
    mov     r0, #177
    mov     r1, #1
    mov     r2, r6
    bl      SETSKIN
    mov     r0, #179
    mov     r1, #0
    bl      PAINT
    mov     r0, #177
    mov     r1, #0
    bl      PAINT
    mov     r0, r4
    pop     {r4, r5, r6, pc}

@ ---------------------------------------------------------------- Bildschirm-Ruhemodus im USB-Modus
@ PDT_UI_POWERCTRL_PreProcessEvent (0x71db0), Ereignis 0x11700000 (Zustand gewechselt):
@ Original pausiert für Zustände 9-14 (ausser 12) Bildschirm- UND System-Ruhemodus
@ (CONTROL PAUSE, Bereich SYSTEM_SCREEN) und setzt beim Rückweg beides fort.
@ Für UVC (10) / USB-Speicher (11) pausieren wir nur SYSTEM (Kamera bleibt an), der
@ Bildschirm geht nach der eingestellten Zeit aus; Tastendruck weckt (Original-Logik).
@ Rückweg: Resume SYSTEM_SCREEN würde am nicht pausierten Bildschirm-Timer abbrechen
@ (POWERCTRL_ResumeEventProc kehrt beim ersten Fehler zurück) -> dann nur SYSTEM.
@ Lokale Variablen des Aufrufers (fp gehört ihm, wir werden per "b" angesprungen):
@   [fp-376] Pause(0)/Resume(1), [fp-372] Bereich SYSTEM(0)/SYSTEM_SCREEN(1), [fp-368] bResetTimer
    .equ PWR_FLAG,         0x003782fc   @ 1 = Ruhemodus läuft (nicht pausiert)
    .equ PWR_RET0,         0x00072004   @ "return 0" (nichts zu tun)
    .equ PWR_RET0B,        0x0007204c
    .equ PWR_GO,           0x00072080   @ weiter mit HI_POWERCTRL_EventPreProc

pwr_usb_pause:                          @ ersetzt Sprungtabelle Zustand 10 und 11 (Original 0x71ff0)
    ldr     r3, =PWR_FLAG
    ldr     r2, [r3]
    cmp     r2, #0
    beq     PWR_RET0
    mov     r2, #0
    str     r2, [r3]
    ldr     r3, =pwr_usb_paused
    mov     r2, #1
    str     r2, [r3]
    mov     r3, #0
    str     r3, [fp, #-376]         @ PAUSE
    str     r3, [fp, #-372]         @ nur SYSTEM
    str     r3, [fp, #-368]
    b       PWR_GO

pwr_resume:                             @ ersetzt "b 0x72038" (übrige Zustände)
    ldr     r3, =PWR_FLAG
    ldr     r2, [r3]
    cmp     r2, #0
    bne     PWR_RET0B
    mov     r2, #1
    str     r2, [r3]
    mov     r3, #1
    str     r3, [fp, #-376]         @ RESUME
    str     r3, [fp, #-368]         @ Timer neu starten
    ldr     r2, =pwr_usb_paused
    ldr     r3, [r2]
    cmp     r3, #0
    moveq   r3, #1                  @ normal: SYSTEM_SCREEN
    movne   r3, #0                  @ aus USB: nur SYSTEM
    str     r3, [fp, #-372]
    mov     r3, #0
    str     r3, [r2]
    b       PWR_GO

    .ltorg
pwr_usb_paused: .word 0

@ ---------------------------------------------------------------- Schnellzugriff Einstellungen
@ WLAN-Taste (Taste 1) lang drücken (Ereignis 0x10800001) öffnet auf dem Startbildschirm
@ (Video-/Fotomodi) sofort die Einstellungen, ohne den Umweg Foto -> Wiedergabe (je 1-2 s
@ Neuaufbau der Pipeline). PDT_UI_COMM_OnEvent, Sprungtabelle "lang gedrückt" (0x5fa14):
@ Eintrag Taste 1 "b 0x5fa8c" (sendet Taste 0x10039, die die Startseite ignoriert) -> hier.
@ Muss im OnEvent-Kontext laufen: aus HOME_PAGE_OnKeyDown heraus wird das Fenster überdeckt.
@ Lang Modus-Taste (Taste 0) = Ausschalten bleibt unverändert.
    .equ LONG1_ORIG,  0x0005fa8c
    .equ ONEV_RET0,   0x0005f884        @ OnEvent: return 0
    .equ GETSTATE,    0x00031130        @ HI_PDT_STATEMNG_GetState(&st), st = 12 Byte
    .equ ISSHOW,      0x001b8e3c        @ HI_GV_Widget_IsShow(h)
    .equ SCRDORMANT,  0x00071af4        @ PDT_UI_POWERCTRL_IsScreenDormant()
    .equ SHOWSYSSET,  0x00052f34        @ UI_ShowSystemSet()
    .equ KEYTONE,     0x00059dbc        @ PDT_UI_COMM_KeyTone(4)
    .global hook_long_wifi
hook_long_wifi:
    push    {r4, r5}
    sub     sp, sp, #16             @ Zustand: 12 Byte
    ldr     r4, =long_dbg           @ Diagnose: [0] Aufrufe, [1] Stufe, [2] Zustand, [3] IsShow(564)
    ldr     r5, [r4]
    add     r5, r5, #1
    str     r5, [r4]
    mov     r5, #1
    str     r5, [r4, #4]
    bl      SCRDORMANT              @ Bildschirm aus: Original (weckt nur auf)
    cmp     r0, #0
    bne     1f
    mov     r0, sp
    bl      GETSTATE
    cmp     r0, #0
    bne     1f
    ldr     r0, [sp]
    str     r0, [r4, #8]
    mov     r5, #2
    str     r5, [r4, #4]
    cmp     r0, #8                  @ 0..8 = Video-/Fotomodi
    bhi     1f
    mov     r5, #3
    str     r5, [r4, #4]
    mov     r0, #103                @ Startbildschirm sichtbar?
    bl      ISSHOW
    cmp     r0, #0
    beq     1f
    mov     r5, #4
    str     r5, [r4, #4]
    mov     r0, #564                @ Einstellungen nicht schon offen
    bl      ISSHOW
    str     r0, [r4, #12]
    cmp     r0, #0
    bne     1f
    mov     r5, #5
    str     r5, [r4, #4]
    mov     r0, #4
    bl      KEYTONE
    ldr     r0, =s_ui_sysset        @ ctui will die Original-Liste ("System")?
    bl      UNLINKF
    cmp     r0, #0
    beq     3f
    ldr     r0, =UI_OPEN            @ sonst: eigenes Menü (ctui) öffnen
    bl      ui_send
    cmp     r0, #0
    beq     4f                      @ ctui hat übernommen
3:  ldr     r0, =quick_set          @ Merker: per Schnellzugriff geöffnet
    mov     r1, #1
    str     r1, [r0]
    bl      SHOWSYSSET
4:  add     sp, sp, #16
    pop     {r4, r5}
    b       ONEV_RET0
1:  add     sp, sp, #16
    pop     {r4, r5}
    b       LONG1_ORIG

@ SYSTEM_SET_exit ruft GKU_Change_WorkMode(gespeicherter Modus, Rückruf) (bl 0x7c0bc): schaltet
@ immer in den gespeicherten Aufnahmemodus (Pipeline-Neuaufbau ~1 s, aus Foto -> Video).
@ Nach Schnellzugriff stattdessen ohne Moduswechsel zurück: wie der Rückruf
@ V100_PDT_UI_PLAYBACK_OnReceiveMsgResult bei Erfolg (Startseite an, 564/155 zu, speichern).
    .equ CHANGE_WM,   0x000622c8        @ GKU_Change_WorkMode
    .equ STARTWIN,    0x00074c64        @ PDT_UI_WINMNG_StartWindow(h, 1)
    .equ FINISHWIN,   0x00075108        @ PDT_UI_WINMNG_FinishWindow(h)
    .equ USERSAVE,    0x000ca638        @ gku_user_SaveParam(1)
    .global hook_set_exit
hook_set_exit:
    ldr     r12, =quick_set
    ldr     r3, [r12]
    cmp     r3, #0
    beq     CHANGE_WM               @ normal geöffnet: Original
    mov     r3, #0
    str     r3, [r12]
    push    {r4, lr}
    mov     r0, #103
    mov     r1, #1
    bl      STARTWIN
    ldr     r0, =564
    bl      FINISHWIN
    mov     r0, #155
    bl      FINISHWIN
    mov     r0, #1
    bl      USERSAVE
    mov     r0, #0
    pop     {r4, pc}
    .ltorg
quick_set:  .word 0
long_dbg:   .word 0, 0, 0, 0

@ ---------------------------------------------------------------- Test-Tasten über sendclickkey.cgi
@ PDT_NETCTRL_SendClickKey ruft am Ende PDT_NETCTRL_PublishEvent(&ev) auf (0xa7fd0).
@ Zusätzliche Typen (-type=..): "K<n>" = Klick (0x10800000), "L<n>" = langer Druck
@ (0x10800001), n = 0..3 (0 Modus, 1 WLAN, 2 Auslöser, 3). "L0" wird verweigert:
@ lang Modus = Ausschalten. Typ-String beim Aufrufer in [fp-588]; [ev] = ID, [ev+4] = Taste.
    .equ NET_PUBLISH, 0x000a0228
    .global hook_clickkey
hook_clickkey:
    sub     r2, fp, #588
    ldrb    r1, [r2]
    orr     r1, r1, #0x20           @ Kleinbuchstabe
    ldrb    r3, [r2, #1]
    sub     r3, r3, #'0'
    cmp     r3, #3
    bhi     9f
    mov     r12, #0x10800000
    cmp     r1, #'k'
    beq     8f
    cmp     r1, #'l'
    bne     9f
    cmp     r3, #0
    beq     9f                      @ L0 nie (Ausschalten)
    add     r12, r12, #1
8:  str     r12, [r0]
    str     r3, [r0, #4]
9:  b       NET_PUBLISH

@ ---------------------------------------------------------------- Eigenes Menü (ctui) - Anbindung
@ Das Menü-Programm /app/hack/ctui zeichnet selbst (FBIO_REFRESH mit eigener Zeichenfläche).
@ Solange /dev/ct9500mod/ui_active existiert:
@   - HiGV darf die Anzeige nicht aktualisieren (Refresh-ioctl in HIGO_ADP_SetLayerSurface
@     wird übersprungen; HiGV zeichnet weiter in seine eigene Zeichenfläche, ctui zeigt diese
@     beim Schließen wieder an),
@   - alle Tasten (HI_GV_SendInputEvent in PDT_UI_COMM_OnEvent) gehen als 4-Byte-Tastencode an
@     die FIFO /dev/ct9500mod/ui.fifo statt an die Oberfläche.
@ Öffnen: lang WLAN-Taste (hook_long_wifi) schreibt UI_OPEN in die FIFO.
    .equ IOCTL,       0x00019e0c        @ ioctl@plt
    .equ SENDINPUT,   0x001aa368        @ HI_GV_SendInputEvent
    .equ OPENF,       0x0001a568        @ open@plt
    .equ WRITEF,      0x0001a154        @ write@plt
    .equ CLOSEF,      0x0001a6dc        @ close@plt
    .equ UNLINKF,     0x0001a0b8        @ unlink@plt
    .equ UI_OPEN,     0x55490001

    .global hook_refresh, hook_input, ui_send
hook_refresh:                           @ ersetzt "bl ioctl" (FBIO_REFRESH) - r0-r2 = ioctl-Argumente
    push    {r0-r3, r12, lr}
    ldr     r0, =s_ui_active
    mov     r1, #0
    bl      ACCESS
    cmp     r0, #0
    pop     {r0-r3, r12, lr}
    moveq   r0, #0                  @ ctui aktiv: nicht anzeigen, Erfolg melden
    bxeq    lr
    b       IOCTL

hook_input:                             @ ersetzt "bl HI_GV_SendInputEvent" - r0 = Ereignis {Typ, Taste}
    push    {r0-r3, r4, lr}
    mov     r4, r0
    ldr     r0, =s_ui_active
    mov     r1, #0
    bl      ACCESS
    cmp     r0, #0
    bne     1f
    ldr     r0, [r4, #4]            @ Tastencode
    bl      ui_send
    pop     {r0-r3, r4, lr}
    mov     r0, #0
    bx      lr
1:  pop     {r0-r3, r4, lr}
    b       SENDINPUT

ui_send:                                @ ui_send(wort): 4 Byte nichtblockierend in die FIFO, r0 = 0 ok
    push    {r4, r5, lr}
    sub     sp, sp, #12
    str     r0, [sp]
    ldr     r0, =s_ui_fifo
    ldr     r1, =0x801              @ O_WRONLY | O_NONBLOCK
    mov     r2, #0
    bl      OPENF
    subs    r4, r0, #0
    movlt   r0, #1
    blt     2f
    mov     r1, sp
    mov     r2, #4
    bl      WRITEF
    mov     r5, r0
    mov     r0, r4
    bl      CLOSEF
    cmp     r5, #4
    moveq   r0, #0
    movne   r0, #1
2:  add     sp, sp, #12
    pop     {r4, r5, pc}

    .ltorg
s_ui_active: .asciz "/dev/ct9500mod/ui_active"
s_ui_fifo:   .asciz "/dev/ct9500mod/ui.fifo"
s_ui_sysset: .asciz "/dev/ct9500mod/ui_sysset"
    .balign 4

@ ---------------------------------------------------------------- Absturz-Rekorder (src/crash.c)
@ Signal-Handler-Einsprung: beim Eintritt zeigt sp auf den Signal-Frame des Kernels.
    .global crash_sig
crash_sig:
    mov     r1, r0                  @ Signalnummer
    mov     r0, sp                  @ struct sigframe
    push    {r4, lr}
    bl      crash_dump
    pop     {r4, pc}

@ ---------------------------------------------------------------- Handler-Tabelle Eintrag 55
hook_onshow:
    push    {r4, lr}
    bl      ORIG_ONSHOW             @ Original mit unveränderten r0-r2
    mov     r4, r0
    bl      refresh_all
    bl      crash_install           @ src/crash.c: Absturz-Rekorder (einmalig)
    @ bl    menucat_show            @ src/menucat.c (deaktiviert: Scroll-Ansicht zeichnet verschobene
    @                               @ Zeilen nicht neu, Original setzt den Fokus zurück; siehe menucat.c)
    mov     r0, r4
    pop     {r4, pc}

@ ---------------------------------------------------------------- Handler-Tabelle Eintrag 56
hook_keydown:
    ldr     r3, =KEY_OK
    cmp     r1, r3
    bne     ORIG_KEYDOWN            @ andere Tasten: Original (Tail-Call, r0-r2 unverändert)
    ldr     r3, =FIRST_BTN
    sub     r3, r0, r3              @ r3 = hWidget - 1121
    cmp     r3, #(3 * (NROWS + 1))
    bhs     ORIG_KEYDOWN            @ keine neue Zeile
    mov     r12, #3
    udiv    r3, r3, r12             @ Zeilenindex
    push    {r4, r5, r6, lr}
    mov     r5, r3
    mul     r4, r3, r12
    ldr     r12, =FIRST_BTN
    add     r4, r4, r12             @ Button der Zeile = 1121 + 3*idx
    cmp     r0, r4
    bne     2f
    cmp     r5, #USB_ROW
    bne     3f
    bl      usb_toggle
    b       2f
3:  ldr     r0, =cmd_toggle
    mov     r1, r5
    bl      run_menu
    mov     r1, r0
    mov     r0, r5
    bl      set_label
2:  mov     r0, #100                @ wie das Original (HIGV_PROC_GOON)
    pop     {r4, r5, r6, pc}

    .ltorg

cmd_get:    .word s_get0, s_get1, s_get2
cmd_toggle: .word s_tog0, s_tog1, s_tog2
usb_str:    .word 476, 475, 474, 477  @ Sprachtexte Laden / PC-Kamera / Speicher / Debug

s_get0: .asciz "/app/hack/menu.sh get 0"
s_get1: .asciz "/app/hack/menu.sh get 1"
s_get2: .asciz "/app/hack/menu.sh get 2"
s_tog0: .asciz "/app/hack/menu.sh toggle 0"
s_tog1: .asciz "/app/hack/menu.sh toggle 1"
s_tog2: .asciz "/app/hack/menu.sh toggle 2"

    .balign 4
@ Zeilenlisten (31 Original + 4 neu), vorwärts und rückwärts; -1 = Zeile ohne Wert
rows_btn:
    .word 569,572,575,578,581,584,587,590,593,596,599,602,605,608,611,614,617,620,623,626,629,631,634,636,639,642,645,647,649,651,653
    .word 1121,1124,1127,1130
rows_lbl:
    .word 570,573,576,579,582,585,588,591,594,597,600,603,606,609,612,615,618,621,624,627,630,632,635,637,640,643,646,648,650,652,654
    .word 1122,1125,1128,1131
rows_val:
    .word 571,574,577,580,583,586,589,592,595,598,601,604,607,610,613,616,619,622,625,628,-1,633,-1,638,641,644,-1,-1,-1,-1,-1
    .word 1123,1126,1129,1132
rows_btn_rev:
    .word 1130,1127,1124,1121
    .word 653,651,649,647,645,642,639,636,634,631,629,626,623,620,617,614,611,608,605,602,599,596,593,590,587,584,581,578,575,572,569
rows_lbl_rev:
    .word 1131,1128,1125,1122
    .word 654,652,650,648,646,643,640,637,635,632,630,627,624,621,618,615,612,609,606,603,600,597,594,591,588,585,582,579,576,573,570
rows_val_rev:
    .word 1132,1129,1126,1123
    .word -1,-1,-1,-1,-1,644,641,638,-1,633,-1,628,625,622,619,616,613,610,607,604,601,598,595,592,589,586,583,580,577,574,571
