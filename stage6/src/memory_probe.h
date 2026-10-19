/*
 * nabu Stage 6: read-only ABL-supplied Flattened Device Tree memory audit.
 * No device/MMIO writes and no claim that a candidate RAM region is free.
 */
#ifndef NABU_MEMORY_PROBE_H
#define NABU_MEMORY_PROBE_H
#include <stdint.h>

struct nabu_memory_report {
    uint32_t valid;               /* Full structural parse completed */
    uint32_t candidate_in_ram;    /* Contained by one advertised /memory bank */
    uint32_t fixed_conflict;      /* Overlaps reserved-memory/reg or /memreserve */
    uint32_t loaded_conflict;     /* Overlaps current Image, FDT or chosen initrd */
    uint32_t dynamic_unknown;     /* Count of reserved-memory children with size but no reg */
    uint32_t initrd_valid;        /* initrd_hi > initrd_lo */
    uint32_t ram_bank_count;      /* Number of nonempty RAM reg entries */
    uint32_t fixed_count;         /* Number of nonempty fixed reserved-memory entries */
    uint32_t memreserve_count;    /* Number of FDT /memreserve entries */
};

/* The FDT data buffer is passed as a pointer; dtb_pa is a separately supplied
 * *hypothetical* physical address for host tests or actual FDT pointer on device.
 * This parser NEVER reads candidate, Image, initrd or physical memory; only FDT.
 */
struct nabu_memory_report nabu_memory_probe(
    const void *dtb, uint64_t dtb_pa,
    uint64_t image_lo, uint64_t image_hi,
    uint64_t candidate_lo, uint64_t candidate_hi,
    uint64_t initrd_lo, uint64_t initrd_hi
);
#endif
