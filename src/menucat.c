/* CT9500-Mod: Einstellungen mit Kategorien (moderne Navigation).
 *
 * Statt einer flachen Liste mit 35 Zeilen zeigt das Einstellungsfenster (SYSTEM_SET, View 564)
 * zuerst eine Übersicht mit Kategorien. OK öffnet eine Kategorie, die nur ihre Zeilen zeigt;
 * die Modus-Taste führt zurück zur Übersicht und dort aus den Einstellungen heraus.
 *
 * Umsetzung: alle Zeilen (Button/Label/Wert) liegen in der Scroll-Ansicht 568. Für die aktuelle
 * Seite werden die übrigen Zeilen ausgeblendet, die sichtbaren untereinander verschoben
 * (HI_GV_Widget_Move) und die Navigation (hoch/runter) über die Original-Hilfsfunktion
 * ui_active_Z2Menu_next_widget mit eigenen Zeilenlisten erledigt.
 *
 * STAND 2026-11-15: DEAKTIVIERT (Aufrufe in src/menuhook.S auskommentiert). Ergebnis der Tests:
 * HI_GV_Widget_Move/Active melden Erfolg (Rect danach 0,0,42,42), aber die Scroll-Ansicht 568
 * zeichnet verschobene Zeilen nicht (eigene, beim Aufbau festgelegte Anordnung), und nach
 * SYSTEM_SET_onshow setzt der Original-Code den Fokus wieder auf die alten Zeilen. Hide/Show
 * macht Zeilen dauerhaft fokusunfähig. Nächster Ansatz: eigene View in higv.bin oder eigene
 * Darstellung.
 *
 * Läuft im eigenen Segment von main_app (tools/elfseg.py), ohne libc; Funktionen von main_app
 * werden über feste Adressen aufgerufen. Aufgerufen aus src/menuhook.S (hook_onshow,
 * hook_keydown).
 */
typedef unsigned int u32;

#define F(addr, ret, ...) ((ret (*)(__VA_ARGS__))(addr))
#define W_ACTIVE      F(0x001b8300, int, u32)
#define W_SHOW        F(0x001b91d8, int, u32)
#define W_HIDE        F(0x001b8b88, int, u32)
#define W_MOVE        F(0x001b93a8, int, u32, int, int)
#define W_PAINT       F(0x001b8efc, int, u32, void *)
#define W_SETTEXT     F(0x001b9550, int, u32, const char *)
#define W_SETTEXTID   F(0x001b9620, int, u32, u32)
#define SPRINTF       F(0x0001a5ec, int, char *, const char *, ...)
#define NEXT_WIDGET   F(0x00062e3c, int, const u32 *, u32, const u32 *, const u32 *, u32)
#define W_GETRECT     F(0x001b9a50, int, u32, int *)

/* Diagnose (per tools/peek lesbar, Adresse: nm): [0..3] Rect vorher, [4..7] nachher,
 * [8] Show-Ret, [9] Move-Ret, [10] Active-Ret, [11] Anzahl Tastenaufrufe, [12..15] letzte
 * Taste (hwnd, key, index, page) */
int menucat_dbg[16] = {0};

#define KEY_OK    0x1003a
#define KEY_NEXT  0x1003b     /* "runter" (Original: Vorwärtslisten) */
#define KEY_MODE  0x1003c     /* Zurück / Verlassen */
#define KEY_PREV  0x1003d     /* "hoch" (Original: Rückwärtslisten) */

#define W_TITLE   565
#define W_COUNTER 566
#define W_SCROLL  568
#define ROW_H     40
#define NONE      0xffffffffu

/* Zeilen: Button, Label, Wert (NONE = Zeile ohne Wert) */
struct row { u32 btn, lbl, val; };

static const struct row ROWS[] = {
    /*  0 */ {569, 570, 571},   /* Videoauflösung */
    /*  1 */ {572, 573, 574},   /* Bildauflösung */
    /*  2 */ {575, 576, 577},   /* Zeitraffer */
    /*  3 */ {578, 579, 580},   /* Loop */
    /*  4 */ {581, 582, 583},   /* Zeitlupe */
    /*  5 */ {584, 585, 586},   /* Bildstabilisierung */
    /*  6 */ {587, 588, 589},   /* Encoder */
    /*  7 */ {590, 591, 592},   /* Bildwinkel */
    /*  8 */ {593, 594, 595},   /* Timer */
    /*  9 */ {596, 597, 598},   /* Serienbild */
    /* 10 */ {599, 600, 601},   /* Mikrofon */
    /* 11 */ {602, 603, 604},   /* Boot-Aufnahme */
    /* 12 */ {605, 606, 607},   /* Belichtung */
    /* 13 */ {608, 609, 610},   /* ISO */
    /* 14 */ {611, 612, 613},   /* Weißabgleich */
    /* 15 */ {614, 615, 616},   /* DNG */
    /* 16 */ {617, 618, 619},   /* Szene */
    /* 17 */ {620, 621, 622},   /* Drehen */
    /* 18 */ {623, 624, 625},   /* Netzfrequenz */
    /* 19 */ {626, 627, 628},   /* Sprache */
    /* 20 */ {629, 630, NONE},  /* Datum/Uhrzeit */
    /* 21 */ {631, 632, 633},   /* Datumsanzeige */
    /* 22 */ {634, 635, NONE},  /* WLAN */
    /* 23 */ {636, 637, 638},   /* Tastenton */
    /* 24 */ {639, 640, 641},   /* Bildschirmschoner */
    /* 25 */ {642, 643, 644},   /* Auto-Aus */
    /* 26 */ {645, 646, NONE},  /* Löschen */
    /* 27 */ {647, 648, NONE},  /* Formatieren */
    /* 28 */ {649, 650, NONE},  /* SD-Test */
    /* 29 */ {651, 652, NONE},  /* Werkseinstellungen */
    /* 30 */ {653, 654, NONE},  /* Version */
    /* 31 */ {1121, 1122, 1123},/* WLAN-Autostart */
    /* 32 */ {1124, 1125, 1126},/* Heimnetz */
    /* 33 */ {1127, 1128, 1129},/* Telnet */
    /* 34 */ {1130, 1131, 1132},/* USB-Modus */
    /* 35.. Kategorie-Zeilen (tools/build.py, Handles ab 1133) */
    /* 35 */ {1133, 1134, 1135},
    /* 36 */ {1136, 1137, 1138},
    /* 37 */ {1139, 1140, 1141},
    /* 38 */ {1142, 1143, 1144},
    /* 39 */ {1145, 1146, 1147},
    /* 40 */ {1148, 1149, 1150},
    /* 41 */ {1151, 1152, 1153},
};
#define NROWS (int)(sizeof ROWS / sizeof ROWS[0])
#define FIRST_CAT_ROW 35
#define NCATS 7

/* Kategorien: Sprachtext des Titels (tools/build.py MENU_ROWS) und Zeilen */
static const signed char CAT_ROWS[NCATS][9] = {
    {0, 2, 3, 4, 5, 6, 7, 11, -1},     /* Video */
    {1, 8, 9, 15, -1},                 /* Foto */
    {12, 13, 14, 16, 17, 18, -1},      /* Bild */
    {10, 23, 21, 24, -1},              /* Ton & Anzeige */
    {22, 31, 32, 33, 34, -1},          /* Verbindungen */
    {19, 20, 25, 29, 30, -1},          /* System */
    {26, 27, 28, -1},                  /* Speicher */
};
#define LANG_SETTINGS 478              /* "Einstellungen"; Kategorien 479..485 */

/* Zustand */
/* Alle Variablen explizit initialisiert: mit -fno-zero-initialized-in-bss landen sie in .data
 * (das Segment hat kein .bss, tools/elfseg.py). */
static int g_page = -1;                /* -1 = Übersicht, sonst Kategorie */
static int g_cat_sel = 0;              /* zuletzt gewählte Kategorie (Rückkehr) */
static int g_n = 0, g_idx = 0;
static u32 g_btn[10] = {0}, g_lbl[10] = {0}, g_val[10] = {0};
static u32 g_btn_r[10] = {0}, g_lbl_r[10] = {0}, g_val_r[10] = {0};
static char g_buf[16] = {0};

static void counter(void)
{
    SPRINTF(g_buf, "%d/%d", g_idx + 1, g_n);
    W_SETTEXT(W_COUNTER, g_buf);
    W_PAINT(W_COUNTER, 0);
}

static void move_row(const struct row *r, int y)
{
    W_MOVE(r->btn, 0, y);
    W_MOVE(r->lbl, 43, y);
    if (r->val != NONE) W_MOVE(r->val, 64, y);
}

/* Seite aufbauen: list = Zeilenindizes (Ende -1), sel = zu aktivierende Position.
 * Kein Hide/Show (danach bekommen die Zeilen keinen Fokus mehr): die Zeilen der Seite werden
 * nach oben verschoben, alle anderen weit nach unten, wo die Navigation nie hinkommt. */
static void layout(const signed char *list, int sel)
{
    int i, n = 0, far = 0;
    char on[NROWS];
    for (i = 0; i < NROWS; i++) on[i] = 0;
    for (n = 0; list[n] >= 0; n++) {
        const struct row *r = &ROWS[(int)list[n]];
        on[(int)list[n]] = 1;
        move_row(r, n * ROW_H);
        g_btn[n] = r->btn;
        g_lbl[n] = r->lbl;
        g_val[n] = r->val;
    }
    for (i = 0; i < NROWS; i++)
        if (!on[i]) move_row(&ROWS[i], 2000 + ROW_H * far++);
    g_n = n;
    for (i = 0; i < n; i++) {          /* Rückwärtslisten für "hoch" */
        g_btn_r[i] = g_btn[n - 1 - i];
        g_lbl_r[i] = g_lbl[n - 1 - i];
        g_val_r[i] = g_val[n - 1 - i];
    }
    if (sel >= n) sel = 0;
    g_idx = sel;
    menucat_dbg[10] = W_ACTIVE(g_btn[sel]);
    W_GETRECT(g_btn[0], &menucat_dbg[4]);
    counter();
    W_PAINT(W_SCROLL, 0);
}

static const signed char OVERVIEW[] = {35, 36, 37, 38, 39, 40, 41, -1};

static void show_overview(int sel)
{
    int i;
    g_page = -1;
    W_SETTEXTID(W_TITLE, LANG_SETTINGS);
    W_PAINT(W_TITLE, 0);
    for (i = 0; i < NCATS; i++)
        W_SETTEXT(ROWS[FIRST_CAT_ROW + i].val, "\xe2\x80\xba");   /* › */
    layout(OVERVIEW, sel);
}

static void show_category(int c)
{
    g_page = c;
    g_cat_sel = c;
    W_SETTEXTID(W_TITLE, LANG_SETTINGS + 1 + c);
    W_PAINT(W_TITLE, 0);
    layout(CAT_ROWS[c], 0);
}

/* Aufruf nach SYSTEM_SET_onshow (Fenster wird angezeigt) */
void menucat_show(void)
{
    show_overview(0);
}

static int index_of(u32 h)
{
    int i;
    for (i = 0; i < g_n; i++)
        if (g_btn[i] == h) return i;
    return -1;
}

/* Aufruf am Anfang von SYSTEM_SET_button_onkeydown. Rückgabe 1 = Taste verarbeitet. */
int menucat_key(u32 hwnd, u32 key, u32 lparam)
{
    int i;
    (void)lparam;
    i = index_of(hwnd);
    menucat_dbg[11]++;
    menucat_dbg[12] = hwnd;
    menucat_dbg[13] = key;
    menucat_dbg[14] = i;
    menucat_dbg[15] = g_page;
    if (i < 0)
        return 0;                       /* nicht unsere Seite (z. B. Dialog): Original */
    g_idx = i;
    if (key == KEY_NEXT) {
        NEXT_WIDGET(g_btn, g_n, g_lbl, g_val, hwnd);
        g_idx = (i + 1 < g_n) ? i + 1 : 0;
        counter();
        return 1;
    }
    if (key == KEY_PREV) {
        NEXT_WIDGET(g_btn_r, g_n, g_lbl_r, g_val_r, hwnd);
        g_idx = (i > 0) ? i - 1 : g_n - 1;
        counter();
        return 1;
    }
    if (g_page < 0) {                   /* Übersicht */
        if (key == KEY_OK) {
            show_category(i);
            return 1;
        }
        return 0;                       /* Modus-Taste: Einstellungen verlassen (Original) */
    }
    if (key == KEY_MODE) {              /* Kategorie -> zurück zur Übersicht */
        show_overview(g_cat_sel);
        return 1;
    }
    return 0;                           /* OK in Kategorie: Original öffnet den Dialog */
}
