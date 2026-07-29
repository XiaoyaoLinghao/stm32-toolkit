---
name: setup-stm32-env
description: 检查并安装 STM32F4 GCC 开发环境：编译器、构建工具、PyOCD、VS Code 插件、DAP-Link 探针、pyocd-debug-mcp。纯环境操作，不涉及任何工程代码。
---

# setup-stm32-env — STM32F4 开发环境安装（一次性）

## 触发

用户输入 `/setup-stm32-env`，或说"配置STM32开发环境"、"安装STM32工具链"。

## 执行流程

逐项检查以下 6 项，每项给出通过/未通过状态。未通过的提示安装方法。全部完成后输出总结表。

### 1. 编译器 (arm-none-eabi-gcc)

```bash
arm-none-eabi-gcc --version 2>&1 | head -1
```

- 预期：版本 ≥ 10.0
- 未通过：引导用户下载 STM32CubeCLT
  - 下载地址：https://www.st.com/en/development-tools/stm32cubeclt.html
  - 默认安装路径：`C:/ST/STM32CubeCLT_1.22.0/`

### 2. 构建系统 (CMake + Ninja)

```bash
cmake --version 2>&1 | head -1
ninja --version 2>&1
```

- 未通过：`pip install cmake ninja`

### 3. 烧录/调试工具 (PyOCD + CMSIS-Pack)

```bash
pyocd --version 2>&1
pyocd pack show 2>&1 | findstr -i stm32f429
```

- 未通过：
  ```bash
  pip install pyocd
  pyocd pack install stm32f429zgtx
  ```

### 4. VS Code 插件

```bash
code --list-extensions 2>&1 | findstr "cpptools\|cortex-debug\|cmake-tools"
```

| 插件 ID | 用途 | 必须 |
|---|---|---|
| `ms-vscode.cpptools` | C/C++ IntelliSense | 是 |
| `marus25.cortex-debug` | ARM Cortex 调试 | 是 |
| `ms-vscode.cmake-tools` | CMake 状态栏 Build/Debug | 推荐 |

- 未通过：告知用户在 VS Code 中 `Ctrl+Shift+X` 搜索安装

### 5. DAP-Link 探针

```bash
pyocd list 2>&1
```

- 预期：看到 STM32F429ZGTx 目标
- 未通过：检查 USB 数据线（非充电线）、Zadig WinUSB 驱动

### 6. pyocd-debug-mcp（Claude 嵌入式调试 MCP 服务器）

**说明**：`pyocd-debug-mcp` 是一个 MCP 服务器，让 Claude 能直接通过 MCP 协议调用 pyOCD 的全部调试能力（读内存、读外设寄存器、HardFault 分析、RTT、断点等）。它是 `read-var` skill 的底层能力提供者。

```bash
uv --version 2>&1
```

- **uv 未安装**：
  ```bash
  pip install uv
  ```

```bash
uv pip list 2>&1 | findstr "pyocd-debug-mcp"
```

- **pyocd-debug-mcp 未安装**：
  ```bash
  uv pip install "pyocd-debug-mcp[svd] @ git+https://github.com/konbakuyomu/pyocd-debug-mcp.git"
  ```

**MCP 注册**（Claude Code）：

```bash
claude mcp add pyocd-debug -- uv --directory <pyocd-debug-mcp-path> run pyocd-debug-mcp
```

或者手动在 `.claude/settings.local.json` 中添加：

```json
{
  "mcpServers": {
    "pyocd-debug": {
      "command": "uv",
      "args": ["--directory", "<pyocd-debug-mcp-path>", "run", "pyocd-debug-mcp"]
    }
  }
}
```

其中 `<pyocd-debug-mcp-path>` 是 `pyocd-debug-mcp` 的安装路径（通过 `uv pip show pyocd-debug-mcp` 查找或使用 `uv tool dir`）。

## 输出格式

全部检查完毕后，输出表格：

```
环境检查结果:
  ✅ arm-none-eabi-gcc   13.2.1  (C:/ST/STM32CubeCLT_1.22.0/)
  ✅ cmake               3.28.1
  ✅ ninja               1.11.1
  ✅ pyocd               0.45.1  (pack: stm32f429zgtx)
  ✅ VS Code 插件         cpptools / cortex-debug / cmake-tools
  ✅ DAP-Link            STM32F429ZGTx 已连接
  ✅ pyocd-debug-mcp     已安装 + 已注册 MCP

全部通过，环境就绪。
```

## 工具链生态总览

安装完成后，这四个 skill 形成完整链路：

```
setup-stm32-env       →  安装全部工具
migrate-keil          →  解析 Keil 工程 → .stm32-project.json
init-stm32-project    →  生成 CMake/VSCode 配置 + .pyocd-debug.json
read-var              →  运行时调试（通过 pyocd-debug-mcp）
```
