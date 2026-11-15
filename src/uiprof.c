/* Einfacher Sampling-Profiler für main_app (CT9500).
 *
 *   uiprof <pid> <dauer_ms> [intervall_us]
 *
 * Liest periodisch /proc/<pid>/task/<tid>/syscall. Für blockierte Threads (Systemaufruf
 * aktiv) werden Stackpointer und PC geliefert; dann werden 1 KiB Stack aus /proc/<pid>/mem
 * gelesen und alle Wörter ausgegeben, die im Code von main_app liegen (Rücksprungadressen-
 * Kandidaten). Laufende Threads werden als "running" gezählt.
 * Ausgabe je Probe: t_ms tid name nr|running pc addr1 addr2 ...
 * Auswertung auf dem PC: tools/uiprof.py (Symbolnamen aus main_app).
 */
#include <dirent.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define TEXT_LO 0x00010000u
#define TEXT_HI 0x0035e600u
#define STACK_BYTES 1024

static long now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000L + ts.tv_nsec / 1000000L;
}

static int read_file(const char *p, char *buf, int n)
{
    int fd = open(p, O_RDONLY), r;
    if (fd < 0) return -1;
    r = read(fd, buf, n - 1);
    close(fd);
    if (r < 0) return -1;
    buf[r] = 0;
    return r;
}

int main(int argc, char **argv)
{
    if (argc < 3) { fprintf(stderr, "uiprof <pid> <ms> [us]\n"); return 1; }
    int pid = atoi(argv[1]);
    long dur = atol(argv[2]);
    int us = argc > 3 ? atoi(argv[3]) : 5000;
    char path[128], buf[512], name[64];
    unsigned int stack[STACK_BYTES / 4];
    snprintf(path, sizeof path, "/proc/%d/mem", pid);
    int memfd = open(path, O_RDONLY);
    long t0 = now_ms();
    while (now_ms() - t0 < dur) {
        snprintf(path, sizeof path, "/proc/%d/task", pid);
        DIR *d = opendir(path);
        if (!d) return 1;
        struct dirent *e;
        while ((e = readdir(d))) {
            if (e->d_name[0] == '.') continue;
            int tid = atoi(e->d_name);
            snprintf(path, sizeof path, "/proc/%d/task/%d/comm", pid, tid);
            if (read_file(path, name, sizeof name) < 0) continue;
            name[strcspn(name, "\n")] = 0;
            for (char *c = name; *c; c++) if (*c == ' ') *c = '_';
            snprintf(path, sizeof path, "/proc/%d/task/%d/syscall", pid, tid);
            if (read_file(path, buf, sizeof buf) < 0) continue;
            long t = now_ms() - t0;
            if (!strncmp(buf, "running", 7)) { printf("%ld %d %s running\n", t, tid, name); continue; }
            unsigned long v[9] = {0};
            char *p = buf;
            for (int i = 0; i < 9; i++) v[i] = strtoul(p, &p, 0);
            /* nr a1..a6 sp pc */
            printf("%ld %d %s %lu %#lx", t, tid, name, v[0], v[8]);
            if (memfd >= 0 && v[7] && pread(memfd, stack, sizeof stack, (off_t)v[7]) > 0) {
                for (int i = 0; i < STACK_BYTES / 4; i++)
                    if (stack[i] >= TEXT_LO && stack[i] < TEXT_HI) printf(" %#x", stack[i]);
            }
            putchar('\n');
        }
        closedir(d);
        fflush(stdout);
        usleep(us);
    }
    return 0;
}
