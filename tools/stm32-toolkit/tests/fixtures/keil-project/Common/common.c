/* common.c — ARMCC constructs exercised by the inspection scanner */
#include "stm32f4xx.h"
#include <stdint.h>

#define SAMPLE_DELAY 1000u

__irq void systick_isr(void)
{
    __nop();
    __WFI();
    __wfi();
    __asm("nop");
}

#pragma arm section code=".common"
#pragma import(__use_no_semihosting)
#pragma O3

__attribute__((section(".common.data"))) int shared_value;
__attribute__((at(0x20000000))) int pinned_value;

/* comment-only tokens: __irq __nop() __WFI() __asm { __at(0) */
const char *snippet = "string tokens: __irq __nop() __WFI() __asm { __at(0)";
