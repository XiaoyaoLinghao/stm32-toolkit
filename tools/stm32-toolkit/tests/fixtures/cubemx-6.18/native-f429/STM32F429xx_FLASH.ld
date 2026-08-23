ENTRY(Reset_Handler)
MEMORY
{
  RAM (xrw) : ORIGIN = 0x20000000, LENGTH = 192K
  CCMRAM (xrw) : ORIGIN = 0x10000000, LENGTH = 64K
  FLASH (rx) : ORIGIN = 0x8000000, LENGTH = 2048K
}
SECTIONS
{
  .text : { *(.text*) } >FLASH
  .data : { *(.data*) } >RAM AT> FLASH
  .bss : { *(.bss*) *(COMMON) } >RAM
}
