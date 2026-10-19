ENTRY(image_start)
SECTIONS
{
  . = 0;
  .text : { KEEP(*(.text.header)) *(.text*) }
  . = ALIGN(16);
  .rodata : { *(.rodata*) }
  . = ALIGN(16);
  .data : { *(.data*) }
  . = ALIGN(16);
  bss_start = .;
  .bss : { *(.bss*) *(COMMON) }
  . = ALIGN(16);
  bss_end = .;
  . = . + 0x8000;
  . = ALIGN(16);
  stack_top = .;
  . = ALIGN(4096);
  image_end = .;
  /DISCARD/ : { *(.comment*) *(.note*) *(.eh_frame*) *(.llvm_addrsig*) }
}
