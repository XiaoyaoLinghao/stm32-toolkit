/* main.c - naturally convertible Keil fixture source. */
#include "stm32f4xx.h"

__irq void early_init(void) { __nop(); }

int main(void) { return 0; }
