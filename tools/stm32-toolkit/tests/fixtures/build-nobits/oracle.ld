ENTRY(Reset_Handler)

MEMORY
{
  FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 0x00100000
  RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 0x00020000
}

SECTIONS
{
  .isr_vector 0x08000000 : { KEEP(*(.isr_vector)) } > FLASH
  .text 0x08000040 : { *(.text*) } > FLASH
  .data 0x20000000 : AT(0x08000100) { *(.data*) } > RAM
  .bss 0x20000080 (NOLOAD) : AT(0x08000200) { *(.bss*) } > RAM
  .heap 0x200000c0 (NOLOAD) : { . += 0x20; } > RAM
  .stack 0x20000100 (NOLOAD) : AT(0x08000300)
  {
    __StackLimit = .;
    . += 0x400;
    __StackTop = .;
  } > RAM
}
