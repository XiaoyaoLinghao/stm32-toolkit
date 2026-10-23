"""Synthetic CMSIS Cortex-M startup fixtures for STARTUP-GCC tests.

The assembly below is an independently written conventional-module fixture.
It deliberately exercises the grammar (line continuations, Microlib boilerplate,
reserved vector words, weak aliases) without copying a vendor startup file.
"""

from __future__ import annotations

from pathlib import Path

from test_migration_plan import build_repo, git_init, git_status, snapshot_tree

STARTUP_SOURCE = "Startup/startup_synthetic.s"
GENERATED_SOURCE = "Startup/stm32tk_startup_gcc.S"
TARGET = "Legacy"
UVPROJX = "app.uvprojx"

SYNTHETIC_STARTUP = (
    "; Synthetic CMSIS startup fixture for STM32 Toolkit tests.\n"
    "; This file is authored for the grammar test and is not a vendor copy.\n"
    "\n"
    "Stack_Size      EQU     0x00001000\n"
    "\n"
    "                AREA    STACK, NOINIT, READWRITE, ALIGN=3\n"
    "Stack_Mem       SPACE   Stack_Size\n"
    "__initial_sp\n"
    "\n"
    "Heap_Size       EQU     0x00000400\n"
    "\n"
    "                AREA    HEAP, NOINIT, READWRITE, ALIGN=3\n"
    "__heap_base\n"
    "Heap_Mem        SPACE   Heap_Size\n"
    "__heap_limit\n"
    "\n"
    "                PRESERVE8\n"
    "                THUMB\n"
    "\n"
    "                AREA    RESET, DATA, READONLY\n"
    "                EXPORT  __Vectors\n"
    "                EXPORT  __Vectors_End\n"
    "                EXPORT  __Vectors_Size\n"
    "\n"
    "__Vectors       DCD     __initial_sp\n"
    "                DCD     Reset_Handler\n"
    "                DCD     NMI_Handler\n"
    "                DCD     HardFault_Handler\n"
    "                DCD     MemManage_Handler\n"
    "                DCD     BusFault_Handler\n"
    "                DCD     UsageFault_Handler\n"
    "                DCD     0\n"
    "                DCD     0\n"
    "                DCD     0\n"
    "                DCD     0\n"
    "                DCD     SVC_Handler\n"
    "                DCD     DebugMon_Handler\n"
    "                DCD     0\n"
    "                DCD     PendSV_Handler\n"
    "                DCD     SysTick_Handler\n"
    "                DCD     ADC1_IRQHandler\n"
    "                DCD     TIM2_IRQHandler\n"
    "                DCD     USART1_IRQHandler\n"
    "                DCD     EXTI0_IRQHandler\n"
    "                DCD     DMA1_Stream0_IRQHandler\n"
    "                DCD     SPI1_IRQHandler\n"
    "                DCD     I2C1_EV_IRQHandler\n"
    "                DCD     WWDG_IRQHandler\n"
    "\n"
    "__Vectors_End\n"
    "\n"
    "__Vectors_Size  EQU  __Vectors_End - __Vectors\n"
    "\n"
    "                AREA    |.text|, CODE, READONLY\n"
    "\n"
    "Reset_Handler    PROC\n"
    "                 EXPORT  Reset_Handler             [WEAK]\n"
    "        IMPORT  SystemInit\n"
    "        IMPORT  __main\n"
    "\n"
    "                 LDR     R0, =SystemInit\n"
    "                 BLX     R0\n"
    "                 LDR     R0, =__main\n"
    "                 BX      R0\n"
    "                 ENDP\n"
    "\n"
    "NMI_Handler     PROC\n"
    "                EXPORT  NMI_Handler                [WEAK]\n"
    "                B       .\n"
    "                ENDP\n"
    "HardFault_Handler\\\n"
    "                PROC\n"
    "                EXPORT  HardFault_Handler          [WEAK]\n"
    "                B       .\n"
    "                ENDP\n"
    "MemManage_Handler PROC\n"
    "                EXPORT  MemManage_Handler          [WEAK]\n"
    "                B       .\n"
    "                ENDP\n"
    "BusFault_Handler PROC\n"
    "                EXPORT  BusFault_Handler           [WEAK]\n"
    "                B       .\n"
    "                ENDP\n"
    "UsageFault_Handler PROC\n"
    "                EXPORT  UsageFault_Handler         [WEAK]\n"
    "                B       .\n"
    "                ENDP\n"
    "SVC_Handler     PROC\n"
    "                EXPORT  SVC_Handler                [WEAK]\n"
    "                B       .\n"
    "                ENDP\n"
    "DebugMon_Handler PROC\n"
    "                EXPORT  DebugMon_Handler           [WEAK]\n"
    "                B       .\n"
    "                ENDP\n"
    "PendSV_Handler  PROC\n"
    "                EXPORT  PendSV_Handler             [WEAK]\n"
    "                B       .\n"
    "                ENDP\n"
    "SysTick_Handler PROC\n"
    "                EXPORT  SysTick_Handler            [WEAK]\n"
    "                B       .\n"
    "                ENDP\n"
    "\n"
    "Default_Handler PROC\n"
    "\n"
    "                EXPORT  ADC1_IRQHandler            [WEAK]\n"
    "                EXPORT  TIM2_IRQHandler            [WEAK]\n"
    "                EXPORT  USART1_IRQHandler          [WEAK]\n"
    "                EXPORT  EXTI0_IRQHandler           [WEAK]\n"
    "                EXPORT  DMA1_Stream0_IRQHandler    [WEAK]\n"
    "                EXPORT  SPI1_IRQHandler            [WEAK]\n"
    "                EXPORT  I2C1_EV_IRQHandler         [WEAK]\n"
    "                EXPORT  WWDG_IRQHandler            [WEAK]\n"
    "\n"
    "ADC1_IRQHandler\n"
    "TIM2_IRQHandler\n"
    "USART1_IRQHandler\n"
    "EXTI0_IRQHandler\n"
    "DMA1_Stream0_IRQHandler\n"
    "SPI1_IRQHandler\n"
    "I2C1_EV_IRQHandler\n"
    "WWDG_IRQHandler\n"
    "                B       .\n"
    "\n"
    "                ENDP\n"
    "\n"
    "                ALIGN\n"
    "\n"
    "                 IF      :DEF:__MICROLIB\n"
    "\n"
    "                 EXPORT  __initial_sp\n"
    "                 EXPORT  __heap_base\n"
    "                 EXPORT  __heap_limit\n"
    "\n"
    "                 ELSE\n"
    "\n"
    "                 IMPORT  __use_two_region_memory\n"
    "                 EXPORT  __user_initial_stackheap\n"
    "\n"
    "__user_initial_stackheap\n"
    "\n"
    "                 LDR     R0, =  Heap_Mem\n"
    "                 LDR     R1, =(Stack_Mem + Stack_Size)\n"
    "                 LDR     R2, = (Heap_Mem +  Heap_Size)\n"
    "                 LDR     R3, = Stack_Mem\n"
    "                 BX      LR\n"
    "\n"
    "                 ALIGN\n"
    "\n"
    "                 ENDIF\n"
    "\n"
    "                 END\n"
)

OTHER_ASM = (
    "; Synthetic unrelated assembly fixture.\n"
    "    AREA    FILTER, CODE, READONLY\n"
    "    END\n"
)

MAIN_C = (
    "void SystemInit(void)\n"
    "{\n"
    "}\n"
    "\n"
    "volatile unsigned int initialized_value = 0x12345678u;\n"
    "volatile unsigned int zeroed_value;\n"
    "\n"
    "__attribute__((constructor)) static void synthetic_constructor(void)\n"
    "{\n"
    "    initialized_value += 1u;\n"
    "}\n"
    "\n"
    "#if defined(STM32TK_STRONG_IRQ)\n"
    "void WWDG_IRQHandler(void)\n"
    "{\n"
    "    for (;;)\n"
    "    {\n"
    "    }\n"
    "}\n"
    "#endif\n"
    "\n"
    "int main(void)\n"
    "{\n"
    "    return 0;\n"
    "}\n"
)

CPU = 'IRAM(0x20000000,0x30000) IROM(0x8000000,0x100000) CPUTYPE("{core}")\n'


def cpu_setting(core: str = "Cortex-M4") -> str:
    return CPU.format(core=core).strip()


def startup_repo(
    tmp_path: Path,
    *,
    name: str = "startup-project",
    core: str = "Cortex-M4",
    startup: str = SYNTHETIC_STARTUP,
    extra_groups: tuple[tuple[str, tuple[tuple[str, str, str], ...]], ...] = (),
    extra_files: dict[str, str] | None = None,
    gitignore: str | None = None,
) -> Path:
    groups = (
        ("Main", (("main.c", "1", "Main/main.c"),)),
        (
            "Startup",
            (("startup_synthetic.s", "2", STARTUP_SOURCE),),
        ),
        *extra_groups,
    )
    files = {"Main/main.c": MAIN_C, STARTUP_SOURCE: startup}
    files.update(extra_files or {})
    return build_repo(
        tmp_path,
        name=name,
        files=files,
        uvprojx_kwargs={
            "cpu": cpu_setting(core),
            "fpu": None,
            "groups": groups,
            "includes": "Main;Libraries/STM32F4xx_StdPeriph_Driver",
        },
        gitignore=gitignore,
    )


def two_assembly_repo(tmp_path: Path, *, name: str = "startup-two-assembly") -> Path:
    return startup_repo(
        tmp_path,
        name=name,
        extra_groups=(("DSP", (("filter.s", "2", "DSP/filter.s"),)),),
        extra_files={"DSP/filter.s": OTHER_ASM},
    )


__all__ = [
    "GENERATED_SOURCE",
    "MAIN_C",
    "OTHER_ASM",
    "STARTUP_SOURCE",
    "SYNTHETIC_STARTUP",
    "TARGET",
    "UVPROJX",
    "cpu_setting",
    "git_init",
    "git_status",
    "snapshot_tree",
    "startup_repo",
    "two_assembly_repo",
]
