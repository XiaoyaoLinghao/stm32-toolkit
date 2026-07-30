---
name: migrate-keil
description: 解析 Keil uVision 工程(.uvprojx)，提取芯片/源文件/宏定义/头文件路径，转换 ARMCC→GCC 语法，输出 .stm32-project.json 供 init-stm32-project 使用。
---

# migrate-keil — Keil 工程信息提取 + ARMCC→GCC 语法转换

## 触发

用户输入 `/migrate-keil`，或说"迁移这个Keil工程"。

## 前置条件

工作区中存在 `*.uvprojx` 文件。如果没有，提示用户这不是 Keil 工程。

## 执行流程

### 步骤 1：解析 .uvprojx

读取 `*.uvprojx`（XML），提取以下信息：

| 提取项 | XML 路径 | 示例值 |
|---|---|---|
| 芯片型号 | `<Device>` | `STM32F429ZGTx` |
| CPU 类型 | `<Cpu>` 中 `CPUTYPE("...")` | `Cortex-M4` |
| 内存布局 | `<Cpu>` 中 `IRAM(...) IRAM2(...) IROM(...)` | `IRAM(0x20000000,0x30000)` |
| 宏定义 | `<Cads>/<VariousControls>/<Define>` | `USE_STDPERIPH_DRIVER,STM32F429_439xx` |
| Include 路径 | `<Cads>/<VariousControls>/<IncludePath>` | `..\Common;..\Main;...` |
| 源文件列表 | `<Groups>/<Group>/<Files>/<File>/<FilePath>` | `..\Common\common.c` |

### 步骤 2：转写路径

Keil 路径格式 `..\Common\common.c` → 工程根相对路径 `Common/common.c`。

Include 路径格式 `..\Common` → `Common`（去掉 `..\` 前缀，`\` 转 `/`）。

### 步骤 3：检查 ARMCC → GCC 语法兼容性

扫描以下文件，如有 ARMCC 特有语法，当场修改：

| ARMCC 语法 | GCC 改写 |
|---|---|
| `__asm void FUNC(void) { ... }` | `__attribute__((naked)) void FUNC(void) { __asm volatile(...); __asm volatile("BX LR"); }` |
| `__attribute__((at(0x20000000)))` | `__attribute__((section(".mempool_sram")))`（需配合 linker） |
| `__irq` | 不需要（GCC 向量表自动处理） |
| `__nop()` | `__asm volatile("NOP")` |
| `__WFI()` | `__asm volatile("WFI")` |
| `__wfi()` | `__asm volatile("WFI")` |

**重点检查文件**：
- `Common/common.c` — 检查 `__asm`、`__nop()`、`__WFI()`
- `MALLOC/malloc.c` — 检查 `__attribute__((at(`
- `Main/string.h` — 如果是 ARM 自定义库，改为 `#include_next <string.h>` 包装

**修改后务必告知用户改了哪些文件**，让用户可以在 Keil 中同步验证。

### 步骤 4：写入 .stm32-project.json

在工作区根目录生成 `.stm32-project.json`：

```json
{
  "chip": "STM32F429ZGTx",
  "cpu": "cortex-m4",
  "defines": ["USE_STDPERIPH_DRIVER", "STM32F429_439xx"],
  "includePaths": ["Common", "Main", "Startup_config", "..."],
  "sources": ["Common/common.c", "Main/main.c", "..."],
  "memory": {
    "flash":  { "origin": "0x08000000", "length": "0x100000" },
    "sram":   { "origin": "0x20000000", "length": "0x30000" },
    "ccmram": { "origin": "0x10000000", "length": "0x10000" }
  }
}
```

> 内存值从 `<Cpu>` 标签提取。IRAM → sram, IRAM2 → ccmram, IROM → flash。如果 IRAM2 长度为 0，ccmram 设为 null。

### 步骤 5：输出并引导

完成后输出：

```
✅ Keil 工程解析完成
   芯片:   STM32F429ZGTx (Cortex-M4)
   源文件: 53 个
   宏定义: USE_STDPERIPH_DRIVER, STM32F429_439xx
   Include 路径: 34 个
   语法修改: Common/common.c (__nop, WFI), MALLOC/malloc.c (at→section)

已生成: .stm32-project.json

下一步: 运行 /init-stm32-project 生成构建调试配置
```
