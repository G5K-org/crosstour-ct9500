/* memdump <phys_addr_hex> <len>: physischen Speicher (/dev/mem) nach stdout.
 * Für Screenshots des tatsächlich angezeigten HiFB-Puffers (EXTEND-Modus, Dreifachpuffer). */
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>
int main(int argc, char **argv)
{
    if (argc < 3) { fprintf(stderr, "memdump <addr> <len>\n"); return 1; }
    unsigned long a = strtoul(argv[1], 0, 16), n = strtoul(argv[2], 0, 0);
    unsigned long pg = a & ~0xFFFUL, off = a - pg;
    int fd = open("/dev/mem", O_RDONLY | O_SYNC);
    if (fd < 0) { perror("/dev/mem"); return 1; }
    unsigned char *m = mmap(0, n + off, PROT_READ, MAP_SHARED, fd, pg);
    if (m == MAP_FAILED) { perror("mmap"); return 1; }
    fwrite(m + off, 1, n, stdout);
    return 0;
}
