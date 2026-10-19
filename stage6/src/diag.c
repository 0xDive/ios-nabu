/*
 * Stage 6: read-only ABL-supplied FDT memory audit, distinguish outcome
 * using four PSCI automatic-reboot delays. No framebuffer, UFS, DMA, MMIO
 * or physical memory writes beyond our own Image's stack/BSS.
 *
 * 8 seconds:  static candidate fits a RAM bank, no FDT/known collision,
 *             and no explicitly unresolved dynamic reservation.
 * 16 seconds: same static checks pass, but dynamic carveouts unresolved.
 * 24 seconds: candidate outside an advertised bank OR known collision.
 * 32 seconds: malformed/unsupported FDT, missing initrd or unexpected MMU.
 *
 * Important: NONE of these proves ABL runtime memory is free for XNU.
 */
#include <stdint.h>
#include <stddef.h>
#include "fdt_probe.h"
#include "memory_probe.h"

#define PSCI_VERSION 0x84000000U
#define PSCI_SYSTEM_RESET 0x84000009U
#define CANDIDATE_START 0x100000000ULL
#define CANDIDATE_END 0x1F0000000ULL

extern uint8_t image_start[];
extern uint8_t image_end[];

static uint64_t cntfrq(void)
{
    uint64_t x;
    __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(x));
    return x;
}

static uint64_t cntvct(void)
{
    uint64_t x;
    __asm__ volatile("mrs %0, cntvct_el0" : "=r"(x));
    return x;
}

static void wait_seconds(unsigned n)
{
    uint64_t hz = cntfrq();
    if (hz < 1000000ULL || hz > 1000000000ULL)
        for (;;) __asm__ volatile("wfe");
    uint64_t start = cntvct();
    while ((uint64_t)(cntvct() - start) < hz * n)
        __asm__ volatile("yield");
}

static uint64_t psci(uint32_t fn, uint32_t method)
{
    register uint64_t x0 __asm__("x0") = fn;
    if (method == 1) {
        __asm__ volatile("smc #0" : "+r"(x0) : :
                         "x1", "x2", "x3", "x4", "x5", "x6", "x7", "x8",
                         "x9", "x10", "x11", "x12", "x13", "x14", "x15",
                         "x16", "x17", "memory");
    } else {
        __asm__ volatile("hvc #0" : "+r"(x0) : :
                         "x1", "x2", "x3", "x4", "x5", "x6", "x7", "x8",
                         "x9", "x10", "x11", "x12", "x13", "x14", "x15",
                         "x16", "x17", "memory");
    }
    return x0;
}

static void reset_after(unsigned seconds, uint32_t method)
{
    wait_seconds(seconds);
    (void)psci(PSCI_SYSTEM_RESET, method);
    for (;;) __asm__ volatile("wfe");
}

void diag_main(void *dtb)
{
    struct fdt_result id = nabu_inspect_fdt(dtb);
    if (!id.valid || !id.nabu || !id.psci_02_or_newer || !id.method) {
        for (;;) __asm__ volatile("wfe");
    }

    uint64_t version = psci(PSCI_VERSION, id.method);
    uint32_t major = (uint32_t)(version >> 16);
    uint32_t minor = (uint32_t)(version & 0xffffU);
    if (!((major == 0 && minor >= 2 && minor <= 9) ||
          (major == 1 && minor <= 9))) {
        for (;;) __asm__ volatile("wfe");
    }

    /* If MMU is on, do not interpret the FDT's physical addresses as
     * the physical address of our Image or FDT pointer.
     */
    uint64_t sctlr;
    __asm__ volatile("mrs %0, sctlr_el1" : "=r"(sctlr));
    if (sctlr & 1U)
        reset_after(32U, id.method);
    if (!id.has_initrd_start || !id.has_initrd_end ||
        id.initrd_start == 0 || id.initrd_end <= id.initrd_start)
        reset_after(32U, id.method);

    struct nabu_memory_report mem = nabu_memory_probe(
        dtb, (uint64_t)(uintptr_t)dtb,
        (uint64_t)(uintptr_t)image_start,
        (uint64_t)(uintptr_t)image_end,
        CANDIDATE_START, CANDIDATE_END,
        id.initrd_start, id.initrd_end);

    if (!mem.valid || !mem.initrd_valid || !mem.ram_bank_count)
        reset_after(32U, id.method);

    if (!mem.candidate_in_ram || mem.fixed_conflict || mem.loaded_conflict)
        reset_after(24U, id.method);

    if (mem.dynamic_unknown)
        reset_after(16U, id.method);

    reset_after(8U, id.method);
}
