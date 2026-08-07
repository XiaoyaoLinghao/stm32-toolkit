/* common.c - naturally convertible Keil fixture source. */
#include "stm32f4xx.h"

__irq void systick_isr(void)
{
    __nop();
    __wfi();
}

__asm("nop");

__attribute__((section(".common.data"))) int shared_value;
__attribute__((at(0x20000000))) int pinned_value;

int common_work(void) { return 0; }
