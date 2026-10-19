/*
 * Stage 6 read-only boot-time FDT survey. This never loads or jumps to XNU.
 * No arbitrary memory writes. Status signalled by PSCI reset delay only.
 */
#include <stdint.h>
#include "survey.h"
#include "fdt_probe.h"
#define PSCI_VERSION 0x84000000U
#define PSCI_SYSTEM_RESET 0x84000009U
#define CANDIDATE_START 0x100000000ULL
#define CANDIDATE_END   0x1024D0000ULL
static uint64_t timer_freq(void) { uint64_t v; __asm__ volatile("mrs %0,cntfrq_el0":"=r"(v));return v; }
static uint64_t timer_tick(void) { uint64_t v; __asm__ volatile("mrs %0,cntvct_el0":"=r"(v));return v; }
static int wait_seconds(uint32_t s) {
    uint64_t f=timer_freq();if(f<1000000U || f>1000000000U) return 0;
    uint64_t start=timer_tick();
    while((uint64_t)(timer_tick()-start) < f*s) __asm__ volatile("yield");
    return 1;
}
static uint64_t psci_call(uint32_t id,uint8_t method) {
    register uint64_t x0 __asm__("x0")=id;
    if(method==1) __asm__ volatile("smc #0":"+r"(x0)::"x1","x2","x3","x4","x5","x6","x7","x8","x9","x10","x11","x12","x13","x14","x15","x16","x17","memory");
    else __asm__ volatile("hvc #0":"+r"(x0)::"x1","x2","x3","x4","x5","x6","x7","x8","x9","x10","x11","x12","x13","x14","x15","x16","x17","memory");
    return x0;
}
void diag_main(void *dtb) {
    struct fdt_result id=nabu_inspect_fdt(dtb);
    if(!id.valid || !id.nabu || !id.psci_02_or_newer || !id.method) {
        for(;;) __asm__ volatile("wfe");
    }
    uint64_t version=psci_call(PSCI_VERSION,id.method);
    uint32_t major=(uint32_t)(version>>16),minor=(uint32_t)(version&65535U);
    if(!((major==0 && minor>=2 && minor<=9) || (major==1 && minor<=9))) {
        for(;;) __asm__ volatile("wfe");
    }
    struct survey_result r=survey_fdt(dtb,CANDIDATE_START,CANDIDATE_END);
    uint32_t delay=40U;
    if(r.fdt_valid && r.candidate_inside_dram && r.ramdisk_present) {
        if(r.fixed_overlap || r.ramdisk_overlap || r.fdt_self_overlap || r.reserve_table_overlap)
            delay=28U;
        else if(r.dynamic_unresolved)
            delay=16U;
        else
            delay=8U;
    }
    if(wait_seconds(delay)) (void)psci_call(PSCI_SYSTEM_RESET,id.method);
    for(;;) __asm__ volatile("wfe");
}
