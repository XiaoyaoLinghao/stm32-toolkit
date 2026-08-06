.syntax unified
.cpu cortex-m4
.fpu fpv4-sp-d16
.thumb

.section .isr_vector, "a", %progbits
.global g_pfnVectors
.type g_pfnVectors, %object
g_pfnVectors:
  .word __StackTop
  .word Reset_Handler
  .size g_pfnVectors, . - g_pfnVectors

.section .text.Reset_Handler, "ax", %progbits
.thumb_func
.global Reset_Handler
.type Reset_Handler, %function
Reset_Handler:
  ldr r0, =main
  blx r0
  b .
.size Reset_Handler, . - Reset_Handler
