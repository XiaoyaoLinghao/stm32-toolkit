# Real ARM ELF and GNU ld MAP oracles

These two ELF/MAP pairs were linked from `oracle.S` using GNU Tools for STM32
14.3.1 (`arm-none-eabi-gcc.exe`) and binutils 2.44
(`arm-none-eabi-readelf.exe`). They are reusable software fixtures, not
evidence from a board or the user-reported firmware.

From this directory, the exact build commands were:

```text
arm-none-eabi-gcc -c -mcpu=cortex-m4 -mthumb -o oracle.o oracle.S
arm-none-eabi-gcc -nostdlib -nostartfiles -mcpu=cortex-m4 -mthumb -Wl,--build-id=none -Wl,-T,oracle.ld -Wl,-Map,oracle.map -o oracle.elf oracle.o
arm-none-eabi-gcc -nostdlib -nostartfiles -mcpu=cortex-m4 -mthumb -Wl,--build-id=none -Wl,-T,template-rendered.ld -Wl,-Map,template.map -o template.elf oracle.o
```

`oracle.o` is disposable and was removed after linking. `template-rendered.ld`
is the generated linker output from the current Toolkit template for a
FLASH region at `0x08000000` of length `0x00100000` and a RAM region at
`0x20000000` of length `0x00020000`; the test checks that the current renderer
still produces its exact bytes. The linked MAP files retain the generated
section values; their line endings and trailing whitespace were normalized
for version control.

For `oracle.elf`/`oracle.map`, readelf verifies `.isr_vector` (8), `.text` (2),
and `.data` (32) are PROGBITS; `.bss` (48), `.heap` (32), and `.stack` (1024)
are NOBITS. The MAP gives each RAM section a distinct FLASH load address,
including the NOBITS sections. Expected interval-union usage is FLASH
`0x2a` bytes and RAM `0x470` bytes. RAM gaps are excluded, while the full
`.stack` reservation counts. Counting every explicit LMA would wrongly report
FLASH `0x47a` bytes.

For `template.elf`/`template.map`, readelf resolves `__StackLimit` to
`0x20001050` and `__StackTop` to `0x20001450`. The `.stack` allocation is
exactly `0x400` bytes. The default heap is `0x1000` bytes. Both symbols lie
inside RAM and the stack begins immediately after the heap.
