/*
 * nabu Stage 3 test payload, independent of the boot kernel.
 * No MMIO, no writes: return deterministic token. Position-independent.
 */
.section .text, "ax", %progbits
.global payload_entry
payload_entry:
    movz x0, #0x4b21
    movk x0, #0x334f, lsl #16
    movk x0, #0x4255, lsl #32
    movk x0, #0x4e41, lsl #48
    ret
