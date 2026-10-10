ENTRY(Reset_Handler)

_Min_Heap_Size = 4K;
_Min_Stack_Size = 1K;

MEMORY
{
  FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 0x00100000
  RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 0x00020000
}

SECTIONS
{
  .isr_vector :
  {
    KEEP(*(.isr_vector))
  } > FLASH

  .text :
  {
    *(.text*)
    *(.rodata*)
    KEEP(*(.init))
    KEEP(*(.fini))
    . = ALIGN(4);
    _etext = .;
  } > FLASH

  .ARM.extab :
  {
    *(.ARM.extab* .gnu.linkonce.arm.extab.*)
  } > FLASH

  .ARM.exidx :
  {
    *(.ARM.exidx* .gnu.linkonce.arm.exidx.*)
  } > FLASH

  .data :
  {
    _sdata = .;
    *(.data*)
    . = ALIGN(4);
    _edata = .;
  } > RAM AT> FLASH
  _sidata = LOADADDR(.data);

  .bss :
  {
    _sbss = .;
    *(.bss*)
    *(COMMON)
    . = ALIGN(4);
    _ebss = .;
  } > RAM

  .heap (NOLOAD) :
  {
    . = ALIGN(8);
    __end__ = .;
    end = __end__;
    __HeapBase = .;
    . += _Min_Heap_Size;
    __HeapLimit = .;
  } > RAM

  .stack (NOLOAD) :
  {
    . = ALIGN(8);
    __StackLimit = .;
    . += _Min_Stack_Size;
    __StackTop = .;
  } > RAM
}
