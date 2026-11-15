/* peek <pid> <addr_hex> <anzahl_woerter>: Speicher eines Prozesses als 32-Bit-Wörter ausgeben
 * (Diagnose, z. B. Tasten-Protokoll keylog in main_app). */
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
int main(int argc, char **argv)
{
    if (argc < 4) { fprintf(stderr, "peek <pid> <addr_hex> <n>\n"); return 1; }
    char p[64];
    snprintf(p, sizeof p, "/proc/%s/mem", argv[1]);
    int fd = open(p, O_RDONLY);
    unsigned long a = strtoul(argv[2], 0, 16);
    int n = atoi(argv[3]);
    for (int i = 0; i < n; i++) {
        unsigned int w;
        if (fd < 0 || pread(fd, &w, 4, (off_t)(a + 4 * i)) != 4) { printf("ERR\n"); return 1; }
        printf("%08x%c", w, (i % 4 == 3) ? '\n' : ' ');
    }
    putchar('\n');
    return 0;
}
