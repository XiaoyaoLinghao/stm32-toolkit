---
name: init-stm32-project
description: 为 STM32F4 工程生成全套 CMake/GCC 构建 + VS Code 调试配置。自动检测中文路径、已有文件冲突、工具链状态。优先读取 .stm32-project.json，若无则交互询问。
---

# init-stm32-project — STM32F4 CMake/GCC + VS Code 工程初始化

## 触发

用户输入 `/init-stm32-project`，或说"配置这个工程"、"初始化STM32工程"、"生成构建配置"、"重新生成构建配置"。

---

## 执行流程

严格按以下 4 个阶段顺序执行，每个阶段通过后才进入下一阶段。

### 阶段 0：预检（Pre-flight Checks）

#### 0.1 中文路径检测

获取当前工作区的**绝对路径**，检查是否包含中文字符（Unicode 范围 `\u4e00-\u9fff` 以及中文标点如 `（）、。`）。

**如果包含中文**：
```
⚠ 当前工程路径包含中文字符:
   {PATH}

   中文路径会导致 arm-none-eabi-gcc / CMake / PyOCD 出现以下问题:
   - GCC 可能无法正确解析 include 路径
   - CMake configure 阶段可能失败
   - PyOCD 可能无法识别 ELF 文件路径

   建议: 将工程文件夹移动到纯英文路径后重新运行 /init-stm32-project
   例如: D:\workspace\{ENGLISH_NAME}\
```

**此时停止执行，不生成任何文件。** 等待用户确认是否移动路径。

#### 0.2 已有文件检测

检查以下文件是否存在：

| 文件 | 生成条件 |
|---|---|
| `CMakeLists.txt` | 必查 |
| `.vscode/tasks.json` | 必查 |
| `.vscode/launch.json` | 必查 |
| `.vscode/c_cpp_properties.json` | 必查 |
| `.vscode/settings.json` | 必查 |
| `.vscode/extensions.json` | 必查 |
| `cmake/arm-none-eabi-gcc.cmake` | 必查 |
| `linker/*_FLASH.ld` | 必查 |
| `vendor/startup_*.s` | 必查 |
| `CMakePresets.json` | 必查 |
| `build-fw/` 目录 | 检查但不属于本 skill 管理 |

**如果部分文件已存在**，列出清单并询问：

```
检测到以下文件已存在:
  ✅ CMakeLists.txt          (2024-01-15)
  ✅ .vscode/launch.json     (2024-03-02)
  ❌ cmake/arm-none-eabi-gcc.cmake   (缺失)
  ... (列出全部 10 个文件的状态)

如何处理?
  A) 覆盖全部 — 删除旧文件，重新生成所有 10 个文件
  B) 仅补充缺失 — 只生成 ❌ 标记的文件，已有的不动
  C) 取消 — 不做任何修改
```

- 选 **A**：删除列出的所有 10 个旧文件 → 进入阶段 1
- 选 **B**：跳过已存在的文件 → 只生成缺失的 → 进入阶段 1
- 选 **C**：停止执行

**特别注意**：
- 如果 `CMakeLists.txt` 存在但不是由本 skill 生成的（无法确定来源），额外警告："现有的 CMakeLists.txt 可能由其他工具生成，覆盖后无法恢复。确认继续？"
- 如果 `build-fw/` 目录存在，提醒：CMake 缓存可能需要刷新，建议运行 `cmake --build build-fw --target clean` 或直接删除 `build-fw/` 重新 configure。

#### 0.3 工具链可用性检测

```bash
arm-none-eabi-gcc --version 2>&1 | head -1
```

- **通过** → 继续
- **未通过** → 提示"未检测到 arm-none-eabi-gcc，请先运行 /setup-stm32-env 安装工具链"，停止执行

#### 0.4 平台检测

- **Windows**：`gdbTarget` 必须用 `127.0.0.1:50000`（不可用 `localhost` — arm-none-eabi-gdb 会错误解析为文件路径，报 error 138）。提示用户确认 Zadig WinUSB 驱动已安装。
- **Linux / macOS**：`gdbTarget` 可用 `localhost:50000`。同时提示"非 Windows 环境，DAP-Link 驱动可能需要额外配置"。

---

### 阶段 1：获取工程信息

#### 方式 A：存在 .stm32-project.json

检查并验证字段是否完整：

| 字段 | 必填 | 缺失时行为 |
|---|---|---|
| `chip` | 是 | 报错"缺少 chip 字段，请重新运行 /migrate-keil 生成" |
| `defines` | 否 | 默认用 `USE_STDPERIPH_DRIVER, STM32F429_439xx` |
| `includePaths` | 是 | 报错 |
| `sources` | 是 | 报错 |
| `memory` | 否 | 根据 chip 型号查已知默认值 |
| `cpu` | 否 | 默认 `cortex-m4` |

**如果 `.stm32-project.json` 存在但字段缺失**：告知缺失了哪些字段，询问用户"是否手动补全这些字段，还是切换到交互询问模式？"

**如果 `.stm32-project.json` 中的 source 文件路径不存在于磁盘**：逐个检查，列出不存在的文件，询问用户"是否从列表中移除这些文件？"

#### 方式 B：无 .stm32-project.json — 交互询问

依次询问用户以下问题。每个问题提供默认值猜测。

**1. 芯片型号**（必填）

提供常见选项供选择：
```
请选择芯片型号:
  1) STM32F429ZGTx — Flash 1MB, SRAM 192KB, CCMRAM 64KB
  2) STM32F407ZGTx — Flash 1MB, SRAM 192KB, CCMRAM 64KB
  3) STM32F429IGTx — Flash 1MB, SRAM 192KB, CCMRAM 64KB
  4) 其他（手动输入）
```
默认猜测：如果工作区有 `*.uvprojx`，解析其 `<Device>` 字段。

**2. 宏定义**（可选，空格分隔）

默认值：`USE_STDPERIPH_DRIVER STM32F429_439xx`（根据芯片型号调整 `STM32F429_439xx` 部分）。

**3. 源文件**

提供两种方式：
```
如何指定源文件?
  A) 自动扫描 — 递归查找工作区中所有 .c 文件（排除 build-fw/、Project/、.git/）
  B) 按目录指定 — 提供包含 .c 文件的目录列表，逗号分隔
  C) 逐个指定 — 逐一列出 .c 文件路径
```

默认使用 A 自动扫描，扫描结果展示给用户确认。

扫描时**自动排除**：
- `build-fw/`、`build-fw-release/`
- `Project/`（Keil 工程目录）
- `RTE/`、`DebugConfig/`
- 包含中文括号的文件（如 `BDsafe_app（2）.c`）— 提醒用户这些是备份文件
- 开头为 `startup_` 且扩展名为 `.s` 的文件（Keil ARMCC 启动文件）

**4. Include 头文件目录**（逗号分隔）

默认值：自动扫描工作区中包含 `.h` 文件的目录，去重后列表展示给用户确认。

**5. 内存布局**

默认值：根据芯片型号查表。常见 STM32F4：
| 芯片 | Flash | SRAM | CCMRAM |
|---|---|---|---|
| STM32F429ZGTx | 0x08000000, 1024K | 0x20000000, 192K | 0x10000000, 64K |
| STM32F407ZGTx | 0x08000000, 1024K | 0x20000000, 192K | 0x10000000, 64K |
| STM32F429IGTx | 0x08000000, 1024K | 0x20000000, 192K | 0x10000000, 64K |

未知芯片型号 → 询问用户手动输入 Flash/SRAM 的 origin 和 size。

**6. 保存选择**

询问用户："是否将以上信息保存为 `.stm32-project.json`？下次运行 `/init-stm32-project` 时可直接使用，无需重新输入。"

默认：是。

---

### 阶段 2：生成文件

#### 生成顺序和目录创建

先创建必要目录（如果不存在）：`cmake/`、`linker/`、`vendor/`、`.vscode/`

然后按顺序生成以下 **11 个**文件。**生成每个文件后立即检查写入是否成功**。

#### 文件模板

**1. CMakeLists.txt** — 模板见 [附录 A](#附录-a-cmakeliststxt-模板)

**2. cmake/arm-none-eabi-gcc.cmake** — 模板见 [附录 B](#附录-b-cmakearm-none-eabi-gcccmake)

**3. linker/{CHIP}_FLASH.ld** — 模板见 [附录 C](#附录-c-linkerchip_flashld-模板)

**4. vendor/startup_{CHIP_BASE}.s** — 生成规则见 [附录 D](#附录-d-vendorstartup_chip_bases-生成规则)

**5~9. .vscode/ 目录（5 个文件）** — 模板见 [附录 E](#附录-e-vscode-文件模板)

**10. CMakePresets.json** — 模板见 [附录 F](#附录-f-cmakepresetsjson-模板)

**11. .pyocd-debug.json** — 模板见 [附录 G](#附录-g-pyocd-debugjson-模板)

> **模板变量**：
> | 变量 | 说明 | 示例 |
> |---|---|---|
> | `{CHIP}` | 芯片型号全名（保持原大小写） | `STM32F429ZGTx` |
> | `{CHIP_LOWER}` | 芯片型号全小写 | `stm32f429zgtx` |
> | `{CHIP_BASE}` | 去掉封装后缀的基础型号（取最简形式） | `stm32f429xx` |
> | `{TOOLCHAIN_BIN}` | arm-none-eabi-gcc 所在 bin 目录 | `C:/ST/STM32CubeCLT_1.22.0/GNU-tools-for-STM32/bin` |
> | `{PYOCD_PATH}` | pyocd.exe 绝对路径（`where pyocd` 获取） | `C:/Users/<user>/AppData/.../pyocd.exe` |
> | `{SVD_PATH}` | SVD 文件绝对路径 | `C:/ST/STM32CubeCLT_1.22.0/STMicroelectronics_CMSIS_SVD/STM32F429.svd` |

---

### 阶段 3：验证与输出

生成完成后执行以下验证：

#### 3.1 文件完整性检查

确认 10 个文件全部存在于磁盘，列出路径和文件大小。

#### 3.2 .gitignore 建议

检查是否存在 `.gitignore`。如果不存在，建议创建并添加：
```
build-fw/
build-fw-release/
.stm32-project.json
```

如果 `.gitignore` 已存在但缺少上述条目，建议追加。

#### 3.3 备份文件提醒

扫描工作区中是否包含带中文括号的备份文件（如 `xxx（2）.c`、`xxx（3）.c`）。如果存在，提醒：
```
⚠ 检测到以下备份文件，CMakeLists.txt 中未包含它们:
   - BDSAFE/BDsafe_app（2）.c
   - BDSAFE/BDsafe_app（3）.c
   这些文件不会参与编译。如果它们不需要维护，建议删除以减少混淆。
```

#### 3.4 输出总结

```
✅ 工程初始化完成 (chip: {CHIP})

   已生成/更新 {N} 个文件:
   ✅ CMakeLists.txt
   ✅ cmake/arm-none-eabi-gcc.cmake
   ✅ linker/{CHIP}_FLASH.ld
   ✅ vendor/startup_{CHIP_BASE}.s
   ✅ .vscode/tasks.json         (build + flash + gdbserver)
   ✅ .vscode/launch.json        (Cortex-Debug external :50000)
   ✅ .vscode/c_cpp_properties.json
   ✅ .vscode/settings.json      (GB2312, CRLF, CMake/Cortex-Debug)
   ✅ .vscode/extensions.json
   ✅ CMakePresets.json          (arm-debug / arm-release, 含 buildPresets)

   后续操作:
   1. 安装推荐插件: VS Code → Extensions → 搜索 @recommended → 全部安装
   2. Ctrl+Shift+P → CMake: Select Configure Preset → arm-debug
   3. 状态栏点 Build（或 F7）编译
   4. F5 → 一键: 编译 → 烧录 → 启动 GDBServer → 停在 main()
   5. 如需运行时变量调试，先 /setup-stm32-env 安装 pyocd-debug-mcp，再 /read-var
```

---

## 边界情况总表

| 情况 | 行为 |
|---|---|
| 路径含中文 | 警告 + 停止，建议移动到纯英文路径 |
| 部分文件已存在 | 列出清单，询问 覆盖全部 / 仅补充缺失 / 取消 |
| 全部文件已存在 | 询问是否强制覆盖全部 |
| CMakeLists.txt 非本工具生成 | 额外警告，确认后才覆盖 |
| build-fw/ 已存在 | 提醒清理缓存 |
| .stm32-project.json 字段缺失 | 列出缺失字段，询问补全或切换交互模式 |
| .stm32-project.json source 路径不存在 | 列出不存在的文件，询问移除或保留 |
| 无 .stm32-project.json | 进入交互询问 |
| arm-none-eabi-gcc 未安装 | 提示先运行 /setup-stm32-env，停止 |
| 非 Windows 系统 | gdbserver 任务用 bash 语法替代 PowerShell |
| 未知芯片型号 | 询问手动输入 Flash/SRAM 参数 |
| 目录中存在中文括号备份文件 | 提醒用户，不包含进编译 |
| .gitignore 缺失或不完整 | 建议创建/追加 |

---

## 约定

| 约定 | 说明 |
|---|---|
| `project(firmware C ASM)` | project 名固定为 `firmware`，与工程目录名无关 |
| `firmware.elf` | 产物名固定 |
| `${workspaceFolder}` | 所有 VS Code 配置使用此变量，不硬编码绝对路径 |
| `build-fw/` | 构建目录固定 |
| `50000` | 调试端口固定，gdbserver 启动前自动释放 |

---

## 附录

### 附录 A：CMakeLists.txt 模板

```cmake
cmake_minimum_required(VERSION 3.22)
project(firmware C ASM)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

# ---- MCU flags ----
set(CPU_FLAGS -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard)

add_compile_options(
  ${CPU_FLAGS}
  -Wall -Wextra
  -ffunction-sections -fdata-sections
  "$<$<CONFIG:Debug>:-O0>"
  "$<$<CONFIG:Debug>:-g>"
  "$<$<CONFIG:Release>:-Os>"
)

add_compile_definitions({DEFINES})

# ---- Sources ----
add_executable(firmware.elf
  {SOURCES}
)

# ---- Include paths ----
target_include_directories(firmware.elf PRIVATE
  {INCLUDE_DIRS}
)

# ---- Linker ----
set(LDSCRIPT ${CMAKE_SOURCE_DIR}/linker/{CHIP}_FLASH.ld)
target_link_options(firmware.elf PRIVATE
  ${CPU_FLAGS} -T${LDSCRIPT}
  --specs=nano.specs --specs=nosys.specs
  -Wl,--gc-sections -Wl,-Map=firmware.map,--cref
  -Wl,--print-memory-usage
)

# ---- Post-build: hex + bin + size ----
add_custom_command(TARGET firmware.elf POST_BUILD
  COMMAND ${CMAKE_SIZE} $<TARGET_FILE:firmware.elf>
  COMMAND ${CMAKE_OBJCOPY} -O ihex   $<TARGET_FILE:firmware.elf> firmware.hex
  COMMAND ${CMAKE_OBJCOPY} -O binary $<TARGET_FILE:firmware.elf> firmware.bin
  COMMENT "size + objcopy -> hex/bin"
)
```

- `project()` 固定为 `firmware`，产物固定 `firmware.elf`
- 源文件路径用 `${CMAKE_SOURCE_DIR}/` 前缀，按目录分组加注释
- Keil ARMCC 启动文件（`Startup_config/startup_*.s`）**不包含**，用 `vendor/startup_{CHIP_BASE}.s` 替代
- **路径包含空格时必须加引号**：CMake 的 `set()` 函数会将空格视为参数分隔符。如果路径如 `USER/Model marking/Modelmarking.c` 含有空格，必须用双引号包裹：
  ```cmake
  "${CMAKE_SOURCE_DIR}/USER/Model marking/Modelmarking.c"
  ```
  或者单独用变量处理：
  ```cmake
  set(MODEL_MARKING_DIR "${CMAKE_SOURCE_DIR}/USER/Model marking")
  set(USER_SRC ... "${MODEL_MARKING_DIR}/Modelmarking.c" ...)
  ```

### 附录 B：cmake/arm-none-eabi-gcc.cmake

固定内容，直接写入，无需任何修改：

```cmake
set(CMAKE_SYSTEM_NAME      Generic)
set(CMAKE_SYSTEM_PROCESSOR arm)
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)

set(TC arm-none-eabi-)
set(CMAKE_C_COMPILER   ${TC}gcc)
set(CMAKE_CXX_COMPILER ${TC}g++)
set(CMAKE_ASM_COMPILER ${TC}gcc)
set(CMAKE_OBJCOPY      ${TC}objcopy CACHE INTERNAL "")
set(CMAKE_SIZE         ${TC}size    CACHE INTERNAL "")

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
```

### 附录 C：linker/{CHIP}_FLASH.ld 模板

`{FLASH_ORIGIN}`、`{FLASH_SIZE_K}`、`{RAM_ORIGIN}`、`{RAM_SIZE_K}`、`{CCMRAM_ORIGIN}`、`{CCMRAM_SIZE_K}`、`{EXTSRAM_ORIGIN}`、`{EXTSRAM_SIZE_K}` 替换为实际值（EXTSRAM 默认 `0x68000000`/`1024`K）。

```ld
ENTRY(Reset_Handler)

_estack = ORIGIN(RAM) + LENGTH(RAM);
_Min_Heap_Size  = 0x200;
_Min_Stack_Size = 0x400;

MEMORY
{
  FLASH   (rx)  : ORIGIN = {FLASH_ORIGIN}, LENGTH = {FLASH_SIZE_K}K
  RAM     (xrw) : ORIGIN = {RAM_ORIGIN},   LENGTH = {RAM_SIZE_K}K
  CCMRAM  (xrw) : ORIGIN = {CCMRAM_ORIGIN}, LENGTH = {CCMRAM_SIZE_K}K
  EXTSRAM (xrw) : ORIGIN = {EXTSRAM_ORIGIN}, LENGTH = {EXTSRAM_SIZE_K}K
}

SECTIONS
{
  .isr_vector : { . = ALIGN(4); KEEP(*(.isr_vector)); . = ALIGN(4); } >FLASH
  .text : {
    . = ALIGN(4);
    *(.text) *(.text*) *(.glue_7) *(.glue_7t) *(.eh_frame)
    KEEP(*(.init)) KEEP(*(.fini))
    . = ALIGN(4); _etext = .;
  } >FLASH
  .rodata : { . = ALIGN(4); *(.rodata) *(.rodata*); . = ALIGN(4); } >FLASH
  .ARM.extab : { *(.ARM.extab* .gnu.linkonce.armextab.*) } >FLASH
  .ARM : { __exidx_start = .; *(.ARM.exidx*); __exidx_end = .; } >FLASH
  .preinit_array : { PROVIDE_HIDDEN(__preinit_array_start = .); KEEP(*(.preinit_array*)) PROVIDE_HIDDEN(__preinit_array_end = .); } >FLASH
  .init_array    : { PROVIDE_HIDDEN(__init_array_start = .); KEEP(*(SORT(.init_array.*))) KEEP(*(.init_array*)) PROVIDE_HIDDEN(__init_array_end = .); } >FLASH
  .fini_array    : { PROVIDE_HIDDEN(__fini_array_start = .); KEEP(*(SORT(.fini_array.*))) KEEP(*(.fini_array*)) PROVIDE_HIDDEN(__fini_array_end = .); } >FLASH

  _sidata = LOADADDR(.data);
  .data : { . = ALIGN(4); _sdata = .; *(.data) *(.data*); . = ALIGN(4); _edata = .; } >RAM AT> FLASH
  .bss  : {
    . = ALIGN(4); _sbss = .; __bss_start__ = _sbss;
    *(.bss) *(.bss*) *(COMMON)
    . = ALIGN(4); _ebss = .; __bss_end__ = _ebss;
  } >RAM
  ._user_heap_stack : {
    . = ALIGN(8); PROVIDE(end = .); PROVIDE(_end = .);
    . = . + _Min_Heap_Size; . = . + _Min_Stack_Size; . = ALIGN(8);
  } >RAM

  .ccmram (NOLOAD) : { . = ALIGN(4); _sccmram = .; *(.ccmram) *(.ccmram*); . = ALIGN(4); _eccmram = .; } >CCMRAM
  .extsram (NOLOAD) : { . = ALIGN(4); _sextsram = .; *(.extsram) *(.extsram*); . = ALIGN(4); _eextsram = .; } >EXTSRAM

  /DISCARD/ : { libc.a(*) libm.a(*) libgcc.a(*) }
  .ARM.attributes 0 : { *(.ARM.attributes) }
}
```

### 附录 D：vendor/startup_{CHIP_BASE}.s 生成规则

生成标准 CMSIS Cortex-M4 GCC 启动文件。文件结构：

1. `.syntax unified` / `.cpu cortex-m4` / `.fpu softvfp` / `.thumb` 声明
2. `Reset_Handler`：初始化栈指针 → 调用 SystemInit → 复制 .data 段 → 清零 .bss → 调用 `__libc_init_array` → 调用 `main`
3. `Default_Handler`：死循环 `b .`
4. `.isr_vector` 段：初始 SP + Reset_Handler + 15 个系统异常 + 芯片外设中断向量
5. 所有向量的 `.weak` + `.thumb_set` 别名指向 Default_Handler

外设中断向量表按 STM32F4 参考手册排列。参考：`https://github.com/STMicroelectronics/cmsis-device-f4`

### 附录 E：.vscode/ 文件模板

**① .vscode/tasks.json**：

> **注意**：gdbserver 任务直接用 `pyocd gdbserver`（子命令），不是 `pyocd-gdbserver`（独立 exe 不一定存在）。
> 不要在 task 里用 PowerShell 做端口清理 — JSON 转义极易出错。端口占用由 background problemMatcher 的 `endsPattern` 识别"GDB server listening on port"信号来控制任务完成；如遇端口冲突，手动 `taskkill` 即可。

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "fw: build",
      "detail": "编译固件 (CMake arm-debug preset)",
      "type": "shell",
      "command": "cmake",
      "args": ["--build", "--preset", "arm-debug"],
      "options": { "cwd": "${workspaceFolder}" },
      "group": { "kind": "build", "isDefault": true },
      "problemMatcher": ["$gcc"]
    },
    {
      "label": "fw: flash",
      "detail": "烧录固件到 {CHIP} (PyOCD + CMSIS-DAP)",
      "type": "shell",
      "command": "pyocd",
      "args": ["flash", "-t", "{CHIP_LOWER}", "${workspaceFolder}/build-fw/firmware.elf"],
      "options": { "cwd": "${workspaceFolder}" },
      "problemMatcher": []
    },
    {
      "label": "fw: gdbserver start",
      "detail": "启动 PyOCD GDBServer :50000",
      "type": "shell",
      "command": "pyocd",
      "args": ["gdbserver", "--target", "{CHIP_LOWER}", "--port", "50000"],
      "options": { "cwd": "${workspaceFolder}" },
      "problemMatcher": [
        {
          "pattern": { "regexp": "^.*GDB server listening on port.*$" },
          "background": {
            "activeOnStart": true,
            "beginsPattern": "^.*",
            "endsPattern": "^.*GDB server listening on port.*$"
          }
        }
      ],
      "isBackground": true
    },
    {
      "label": "fw: build + flash + gdbserver",
      "detail": "编译 → 烧录 → 启动 GDBServer (F5 调试前置)",
      "dependsOrder": "sequence",
      "dependsOn": ["fw: build", "fw: flash", "fw: gdbserver start"],
      "problemMatcher": []
    }
  ]
}
```

`{CHIP_LOWER}` 替换为小写芯片名，如 `stm32f429zgtx`。`{CHIP}` 保持原大小写。

**Linux/macOS**：gdbserver 任务的 `command` 和 `args` 不变（`pyocd gdbserver` 跨平台一致）。如需端口清理，可用独立脚本而非内联 shell。**② .vscode/launch.json**：

> **关键坑**：Windows 版 arm-none-eabi-gdb 会把 `localhost` 错误解析为文件路径（error 138），必须用 `127.0.0.1`。
> `pyocdPath` 为 PyOCD 可执行文件的绝对路径，可通过 `where pyocd` 获取。VS Code 扩展进程的 PATH 可能与终端不同，故显式指定。
> `armToolchainPath` 指向 arm-none-eabi-gdb 所在目录。

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Debug (PyOCD)",
      "cwd": "${workspaceFolder}",
      "type": "cortex-debug",
      "request": "launch",
      "servertype": "external",
      "gdbTarget": "127.0.0.1:50000",
      "device": "{CHIP}",
      "executable": "${workspaceFolder}/build-fw/firmware.elf",
      "armToolchainPath": "{TOOLCHAIN_BIN}",
      "pyocdPath": "{PYOCD_PATH}",
      "runToEntryPoint": "main",
      "preLaunchTask": "fw: build + flash + gdbserver",
      "svdFile": "{SVD_PATH}",
      "preRestartCommands": [
        "break main",
        "break HardFault_Handler",
        "break MemManage_Handler",
        "break BusFault_Handler",
        "break UsageFault_Handler"
      ]
    }
  ]
}
```

`{TOOLCHAIN_BIN}` 替换为 `arm-none-eabi-gcc` 所在 bin 目录（如 `C:/ST/STM32CubeCLT_1.22.0/GNU-tools-for-STM32/bin`）。
`{PYOCD_PATH}` 替换为 `pyocd.exe` 的绝对路径（通过 `where pyocd` 获取，如 `C:/Users/<user>/AppData/Local/Programs/Python/Python313/Scripts/pyocd.exe`）。
`{SVD_PATH}` 替换为 SVD 文件绝对路径。

**③ .vscode/c_cpp_properties.json**：
```json
{
  "configurations": [
    {
      "name": "{CHIP} (GCC)",
      "includePath": ["${workspaceFolder}/**"],
      "defines": [{DEFINES_JSON}],
      "compilerPath": "{TOOLCHAIN_BIN}/arm-none-eabi-gcc.exe",
      "cStandard": "c99",
      "intelliSenseMode": "gcc-arm",
      "compilerArgs": ["-mcpu=cortex-m4", "-mthumb", "-mfpu=fpv4-sp-d16", "-mfloat-abi=hard"]
    }
  ],
  "version": 4
}
```

**④ .vscode/settings.json**：
```json
{
  "files.encoding": "gb2312",
  "files.autoGuessEncoding": true,
  "files.eol": "\r\n",
  "editor.tabSize": 2,
  "editor.insertSpaces": false,
  "[c]": { "editor.tabSize": 4, "editor.insertSpaces": true },
  "[cpp]": { "editor.tabSize": 4, "editor.insertSpaces": true },
  "files.associations": { "*.h": "c", "*.s": "arm", "*.scvd": "xml" },
  "cmake.useCMakePresets": "always",
  "cmake.configureOnOpen": false,
  "cortex-debug.armToolchainPath": null,
  "cortex-debug.v1": false
}
```

**⑤ .vscode/extensions.json**：
```json
{
  "recommendations": [
    "ms-vscode.cpptools",
    "marus25.cortex-debug",
    "ms-vscode.cmake-tools"
  ]
}
```

### 附录 F：CMakePresets.json 模板

> **重要**：必须同时定义 configurePresets 和 buildPresets，否则 `cmake --build --preset arm-debug` 会报 "No such build preset"。

```json
{
  "version": 3,
  "configurePresets": [
    {
      "name": "arm-debug",
      "displayName": "ARM GCC Debug",
      "generator": "Ninja",
      "toolchainFile": "cmake/arm-none-eabi-gcc.cmake",
      "binaryDir": "build-fw",
      "cacheVariables": { "CMAKE_BUILD_TYPE": "Debug" }
    },
    {
      "name": "arm-release",
      "displayName": "ARM GCC Release",
      "generator": "Ninja",
      "toolchainFile": "cmake/arm-none-eabi-gcc.cmake",
      "binaryDir": "build-fw-release",
      "cacheVariables": { "CMAKE_BUILD_TYPE": "Release" }
    }
  ],
  "buildPresets": [
    {
      "name": "arm-debug",
      "configurePreset": "arm-debug"
    },
    {
      "name": "arm-release",
      "configurePreset": "arm-release"
    }
  ]
}
```

### 附录 G：.pyocd-debug.json 模板

此文件是 `pyocd-debug-mcp`（MCP 嵌入式调试服务器）的项目配置。生成后，Claude 可通过 MCP 协议直接使用 pyOCD 的全部调试能力（读内存、读外设寄存器、HardFault 分析、RTT 等）。

```json
{
  "target": "{CHIP_LOWER}",
  "firmware": "build-fw/firmware.elf",
  "elf": "build-fw/firmware.elf",
  "svd": "{SVD_PATH}"
}
```

- `{CHIP_LOWER}` — 小写芯片名，如 `stm32f429zgtx`
- `{SVD_PATH}` — SVD 文件绝对路径。优先使用 STM32CubeCLT 自带的：`C:/ST/STM32CubeCLT_1.22.0/STMicroelectronics_CMSIS_SVD/STM32F{编号}.svd`。若 STM32CubeCLT 未安装，则查找 pyOCD 内置 SVD（路径：`{PYOCD_SVD_PATH}`）
- `{PYOCD_SVD_PATH}` — 通过 `python -c "import pyocd; from pathlib import Path; print(Path(pyocd.__file__).parent / 'debug/svd/ST/STM32F429x.svd')"` 获取

**生成规则**：

1. 如果 `.pyocd-debug.json` 已存在且内容匹配当前芯片 → 跳过
2. 如果 `.pyocd-debug.json` 存在但芯片不匹配 → 询问是否覆盖
3. 不存在 → 自动生成

**SVD 路径查找顺序**：
1. `{STM32CubeCLT}/STMicroelectronics_CMSIS_SVD/STM32F{编号}.svd`（优先，完整）
2. pyOCD 内置 SVD（兜底，简化版）
3. 如果两者都不存在，`svd` 字段留 `""`，提醒用户 SVD 解析外设寄存器功能暂不可用（读内存功能不受影响）
