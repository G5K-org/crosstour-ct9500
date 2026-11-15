/* CT9500-Mod: Absturz-Rekorder für main_app (Diagnose).
 *
 * Installiert per signal() Handler für SIGSEGV/SIGBUS/SIGILL/SIGFPE/SIGABRT. Ohne SA_SIGINFO
 * legt der Kernel (ARM, setup_frame) am Stackpointer des Handlers struct sigframe ab:
 *   ucontext: uc_flags, uc_link, uc_stack(3 Wörter), dann sigcontext:
 *   trap_no, error_code, oldmask, r0..r10, fp, ip, sp, lr, pc, cpsr, fault_address
 * Der Einsprung crash_sig (src/menuhook.S) übergibt diesen Stackpointer.
 * Ausgabe: /dev/ct9500mod/crash.txt (Register + 64 Stack-Wörter), Auswertung tools/crash.py.
 * Danach Standard-Handler zurück -> der Fehler tritt erneut auf und beendet main_app wie zuvor.
 */
typedef unsigned int u32;
#define F(addr, ret, ...) ((ret (*)(__VA_ARGS__))(addr))
#define SIGNAL   F(0x00019b0c, void *, int, void *)
#define OPEN     F(0x0001a568, int, const char *, int, int)
#define WRITE    F(0x0001a154, int, int, const void *, u32)
#define CLOSE    F(0x0001a6dc, int, int)
#define SPRINTF  F(0x0001a5ec, int, char *, const char *, ...)

extern void crash_sig(int);           /* src/menuhook.S: mov r1, r0; mov r0, sp; b crash_dump */

static int g_installed = 0;
static char g_out[2048] = {0};

void crash_install(void)
{
    static const int sigs[] = {11, 7, 4, 8, 6};   /* SEGV, BUS, ILL, FPE, ABRT */
    unsigned i;
    if (g_installed) return;
    g_installed = 1;
    for (i = 0; i < sizeof sigs / sizeof sigs[0]; i++)
        SIGNAL(sigs[i], (void *)crash_sig);
}

void crash_dump(const u32 *frame, int sig)
{
    const u32 *mc = frame + 5;            /* sigcontext */
    const u32 *r = mc + 3;                /* r0.. */
    const u32 *sp;
    int n = 0, i, fd;
    n += SPRINTF(g_out + n, "sig %d trap %u err %08x fault %08x\npc %08x lr %08x sp %08x fp %08x cpsr %08x\n",
                 sig, mc[0], mc[1], r[18], r[15], r[14], r[13], r[11], r[16]);
    for (i = 0; i <= 12; i++)
        n += SPRINTF(g_out + n, "r%d %08x%s", i, r[i], (i % 4 == 3) ? "\n" : " ");
    n += SPRINTF(g_out + n, "\nstack:\n");
    sp = (const u32 *)r[13];
    for (i = 0; i < 64; i++)
        n += SPRINTF(g_out + n, "%08x%s", sp[i], (i % 8 == 7) ? "\n" : " ");
    fd = OPEN("/dev/ct9500mod/crash.txt", 0x241, 0644);   /* O_WRONLY|O_CREAT|O_TRUNC */
    if (fd >= 0) {
        WRITE(fd, g_out, n);
        CLOSE(fd);
    }
    SIGNAL(sig, (void *)0);               /* SIG_DFL: erneuter Fehler beendet main_app */
}
