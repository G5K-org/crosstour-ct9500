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
    .equ STARTWINDOW,      0x00074c64   @ PDT_UI_WINMNG_StartWindow(handle, flag)
    .equ SETSKIN,          0x001b8fc8   @ HI_GV_Widget_SetSkin(handle, type, skin)
    .equ STR_OFF,          183          @ Sprachtext "AUS"/"OFF"
    .equ STR_ON,           184          @ Sprachtext "EIN"/"ON"

    .text
    .arm
    .global hook_onshow, hook_keydown, hook_usbwin, rows_btn, rows_lbl, rows_val, rows_btn_rev, rows_lbl_rev, rows_val_rev

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
refresh_all:
    push    {r4, lr}
    mov     r4, #0
1:  adr     r0, cmd_get
    mov     r1, r4
    bl      run_menu
    mov     r1, r0
    mov     r0, r4
    bl      set_label
    add     r4, r4, #1
    cmp     r4, #NROWS
    blt     1b
    bl      usb_get
    bl      usb_label
    pop     {r4, pc}

@ ---------------------------------------------------------------- usb_get() -> 0..2
usb_get:
    push    {r4, lr}
    sub     sp, sp, #8
    mov     r0, #2                  @ Vorgabe Massenspeicher, falls Lesen scheitert
    str     r0, [sp]
    mov     r0, #PT_USB_MODE
    mov     r1, sp
    bl      GETCOMM
    ldr     r0, [sp]
    cmp     r0, #2
    movhi   r0, #2
    add     sp, sp, #8
    pop     {r4, pc}

@ ---------------------------------------------------------------- usb_label(wert=r0)
usb_label:
    push    {r4, lr}
    adr     r1, usb_str
    ldr     r1, [r1, r0, lsl #2]
    ldr     r4, =FIRST_BTN + 3 * USB_ROW + 2
    mov     r0, r4
    bl      SETTEXTBYID
    mov     r0, r4
    mov     r1, #0
    bl      PAINT
    pop     {r4, pc}

@ ---------------------------------------------------------------- usb_toggle(): Speicher -> PC-Kamera -> Laden -> Speicher
usb_toggle:
    push    {r4, lr}
    sub     sp, sp, #8
    bl      usb_get
    subs    r4, r0, #1              @ 2 -> 1, 1 -> 0
    movmi   r4, #2                  @ 0 -> 2
    str     r4, [sp]
    mov     r0, #PT_USB_MODE
    mov     r1, sp
    bl      SETCOMM
    bl      ENABLEUSB
    mov     r0, r4
    bl      usb_label
    add     sp, sp, #8
    pop     {r4, pc}

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

@ ---------------------------------------------------------------- Handler-Tabelle Eintrag 55
hook_onshow:
    push    {r4, lr}
    bl      ORIG_ONSHOW             @ Original mit unveränderten r0-r2
    mov     r4, r0
    bl      refresh_all
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
3:  adr     r0, cmd_toggle
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
usb_str:    .word 476, 475, 474     @ Sprachtexte Laden / PC-Kamera / Speicher

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
