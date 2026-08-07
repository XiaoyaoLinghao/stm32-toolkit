/* Minimal STM32F4xx SPL device header (test fixture only). */
#ifndef __STM32F4xx_H
#define __STM32F4xx_H

typedef unsigned int uint32_t;
typedef unsigned short uint16_t;
typedef unsigned char uint8_t;

#if defined(__CC_ARM)
#define __NOP() __nop()
#define __WFI() __wfi()
#else
#define __NOP() __asm volatile ("nop")
#define __WFI() __asm volatile ("wfi")
#endif

#endif /* __STM32F4xx_H */
