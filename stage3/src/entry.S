/* Minimal AArch64 Linux Image entry for nabu diagnostic.
 * ABL is expected to enter with x0 pointing to FDT.
 */
.section .text.header, "ax", %progbits
.global image_start
image_start:
    b   entry
    .word 0
    .quad 0
    .quad image_end
    .quad 0xa
    .quad 0
    .quad 0
    .quad 0
    .ascii "ARM\x64"
    .word 0

.section .text, "ax", %progbits
.global entry
entry:
    msr daifset, #0xf
    mov x19, x0
    msr spsel, #1
    adr x1, stack_top
    mov sp, x1
    adr x1, bss_start
    adr x2, bss_end
1:  cmp x1, x2
    b.hs 2f
    str xzr, [x1], #8
    b 1b
2:  mov x0, x19
    bl diag_main
3:  wfe
    b 3b
