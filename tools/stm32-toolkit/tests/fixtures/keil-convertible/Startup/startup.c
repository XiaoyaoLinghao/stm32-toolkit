/* C startup used by the real ARM GNU conversion/build acceptance gate. */
#include "stm32f4xx.h"

typedef void (*isr_handler_t)(void);

extern int main(void);
void Reset_Handler(void);

__attribute__((section(".isr_vector"), used))
const isr_handler_t vector_table[] = {
    (isr_handler_t)0x20030000u,
    Reset_Handler,
};

void Reset_Handler(void)
{
    (void)main();
    for (;;) {
        __WFI();
    }
}
