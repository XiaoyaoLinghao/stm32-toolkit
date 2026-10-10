.syntax unified
.thumb
.cpu cortex-m4

.section .isr_vector,"a",%progbits
.word 0x20020000
.word Reset_Handler

.section .text.Reset_Handler,"ax",%progbits
.global Reset_Handler
.type Reset_Handler, %function
.thumb_func
Reset_Handler:
  bx lr

.section .data.payload,"aw",%progbits
.space 0x20, 0x5a

.section .bss.reserved,"aw",%nobits
.space 0x30
