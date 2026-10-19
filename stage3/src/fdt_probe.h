/* FDT-only parser: no MMIO, writes or architecture instructions. */
#ifndef NABU_FDT_PROBE_H
#define NABU_FDT_PROBE_H
#include <stdint.h>
#include <stddef.h>
struct fdt_result {
    uint8_t valid;
    uint8_t nabu;
    uint8_t psci_02_or_newer;
    uint8_t method; /* 1=SMC, 2=HVC */
    uint8_t has_initrd_start;
    uint8_t has_initrd_end;
    uint64_t initrd_start;
    uint64_t initrd_end;
};
struct fdt_result nabu_inspect_fdt(const void *dtb);
#endif
