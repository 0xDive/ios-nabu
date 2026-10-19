/*
 * Xiaomi Pad 5 Stage 3: FDT -> ramdisk -> ARM64 test payload -> PSCI reset.
 * ~10 s auto reboot suggests successful payload token; ~27 s fallback.
 * No storage access, framebuffer writes or fixed physical memory writes.
 */
#include <stdint.h>
#include <stddef.h>
#include "fdt_probe.h"

#define MAGIC_BYTES 8U
#define MAX_SCAN (64U * 1024U * 1024U)
#define MAX_INITRD (64U * 1024U * 1024U)
#define PAYLOAD_OFFSET 64U
#define MAX_PAYLOAD 256U
#define TOKEN 0x4e414255334f4b21ULL
#define PSCI_VERSION 0x84000000U
#define PSCI_SYSTEM_RESET 0x84000009U

static uint8_t payload_execution_area[MAX_PAYLOAD] __attribute__((aligned(64)));

static uint32_t le32(const volatile uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static uint64_t le64(const volatile uint8_t *p) {
    return (uint64_t)le32(p) | ((uint64_t)le32(p + 4) << 32);
}
static int magic_match(const volatile uint8_t *p) {
    static const uint8_t magic[8] = { 'N','A','B','U','3','P','A','Y' };
    for (unsigned i = 0; i < MAGIC_BYTES; ++i)
        if (p[i] != magic[i]) return 0;
    return 1;
}
static uint32_t crc32_bytes(const volatile uint8_t *p, uint32_t n) {
    uint32_t crc = 0xFFFFFFFFU;
    for (uint32_t i = 0; i < n; ++i) {
        crc ^= p[i];
        for (unsigned j = 0; j < 8; ++j)
            crc = (crc >> 1) ^ ((0U - (crc & 1U)) & 0xEDB88320U);
    }
    return ~crc;
}
static uint64_t get_frq(void) {
    uint64_t x;
    __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(x));
    return x;
}
static uint64_t get_cnt(void) {
    uint64_t x;
    __asm__ volatile("mrs %0, cntvct_el0" : "=r"(x));
    return x;
}
static int delay_s(unsigned sec) {
    uint64_t f = get_frq();
    if (f < 1000000U || f > 1000000000U) return 0;
    uint64_t start = get_cnt();
    while ((uint64_t)(get_cnt() - start) < f * sec)
        __asm__ volatile("yield");
    return 1;
}
static uint64_t psci(uint32_t fn, uint8_t method) {
    register uint64_t a0 __asm__("x0") = fn;
    if (method == 1) {
        __asm__ volatile("smc #0" : "+r"(a0) : :
            "x1", "x2", "x3", "x4", "x5", "x6", "x7", "x8", "x9",
            "x10", "x11", "x12", "x13", "x14", "x15", "x16", "x17", "memory");
    } else {
        __asm__ volatile("hvc #0" : "+r"(a0) : :
            "x1", "x2", "x3", "x4", "x5", "x6", "x7", "x8", "x9",
            "x10", "x11", "x12", "x13", "x14", "x15", "x16", "x17", "memory");
    }
    return a0;
}
static void reset_after(unsigned seconds, uint8_t method) {
    if (delay_s(seconds)) (void)psci(PSCI_SYSTEM_RESET, method);
    for (;;) __asm__ volatile("wfe");
}
/* Verify raw initrd content, copy code only into the Image's own aligned BSS. */
static uint64_t lookup_entry(uint64_t initrd_lo, uint64_t initrd_hi) {
    if (initrd_hi <= initrd_lo || initrd_hi - initrd_lo > MAX_INITRD)
        return 0;
    /* Banks from nabu's Android DTB. Fail closed if initrd is elsewhere. */
    int bank0 = initrd_lo >= 0x80000000ULL && initrd_hi <= 0xBCC00000ULL;
    int bank1 = initrd_lo >= 0xC0000000ULL && initrd_hi <= 0x200000000ULL;
    if (!bank0 && !bank1) return 0;
    uint64_t span = initrd_hi - initrd_lo;
    if (span < PAYLOAD_OFFSET + 4U) return 0;
    if (span > MAX_SCAN) span = MAX_SCAN;
    for (uint64_t off = 0; off + PAYLOAD_OFFSET + 4U <= span; ++off) {
        const volatile uint8_t *p = (const volatile uint8_t *)(uintptr_t)(initrd_lo + off);
        if (!magic_match(p)) continue;
        if (le32(p + 8) != 1U || le32(p + 12) != PAYLOAD_OFFSET ||
            le32(p + 24) != 0U || le64(p + 28) != TOKEN) continue;
        uint32_t size = le32(p + 16);
        if (size < 4U || size > MAX_PAYLOAD || (size & 3U) ||
            off + PAYLOAD_OFFSET + size > span) continue;
        if (crc32_bytes(p + PAYLOAD_OFFSET, size) != le32(p + 20)) continue;
        for (uint32_t i = 0; i < size; ++i)
            payload_execution_area[i] = p[PAYLOAD_OFFSET + i];
        return (uint64_t)(uintptr_t)payload_execution_area;
    }
    return 0;
}

void diag_main(void *dtb) {
    struct fdt_result r = nabu_inspect_fdt(dtb);
    if (!r.valid || !r.nabu || !r.psci_02_or_newer || !r.method)
        for (;;) __asm__ volatile("wfe");
    uint64_t v = psci(PSCI_VERSION, r.method);
    uint32_t ma = (uint32_t)(v >> 16), mi = (uint32_t)v & 0xffffU;
    if (!((ma == 0 && mi >= 2 && mi <= 9) || (ma == 1 && mi <= 9)))
        for (;;) __asm__ volatile("wfe");

    /* MMU must be off before trying to execute copied payload. */
    uint64_t sctlr;
    __asm__ volatile("mrs %0, sctlr_el1" : "=r"(sctlr));
    if (r.has_initrd_start && r.has_initrd_end && !(sctlr & 1U)) {
        uint64_t entry = lookup_entry(r.initrd_start, r.initrd_end);
        if (entry) {
            __asm__ volatile("dsb sy; ic iallu; dsb sy; isb" ::: "memory");
            typedef uint64_t (*entry_t)(void);
            uint64_t received = ((entry_t)(uintptr_t)entry)();
            if (received == TOKEN) reset_after(10U, r.method);
        }
    }
    reset_after(27U, r.method);
}
