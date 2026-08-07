    .syntax unified
    .cpu cortex-m4
    .fpu fpv4-sp-d16
    .thumb

    .section .isr_vector, "a", %progbits
    .align 2
    .globl __isr_vector_base__
    .type __isr_vector_base__, %object
__isr_vector_base__:
    .word 0x20020000
    .word Reset_Handler
    .space 56
    .size __isr_vector_base__, . - __isr_vector_base__

    .section .text
    .align 2
    .globl Reset_Handler
    .thumb_func
    .type Reset_Handler, %function
Reset_Handler:
    ldr r0, =0
    bl main
    b .
    .size Reset_Handler, . - Reset_Handler
