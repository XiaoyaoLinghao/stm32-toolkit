# STM32 Toolkit

STM32F4 嵌入式开发的完整 Claude Code 插件工具包。

## 安装

### 方式 1：从本地安装

```bash
# 1. 安装 Python 工具
cd stm32-toolkit/tools/stm32-monitor
pip install -e .

# 2. 注册 skills 到 Claude Code
cp -r stm32-toolkit/skills/* ~/.claude/skills/

# 3. 验证
stm32-monitor --help
```

### 方式 2：作为 Claude Code Plugin（待发布）

```bash
claude plugin add /path/to/stm32-toolkit
```

## 包含的 Skill

| 命令 | 用途 |
|---|---|
| `/setup-stm32-env` | 安装 ARM GCC + CMake + PyOCD + MCP 调试服务器 |
| `/migrate-keil` | 解析 Keil `.uvprojx` → `.stm32-project.json` |
| `/init-stm32-project` | 生成 CMakeLists.txt + `.vscode/` + `.pyocd-debug.json` |
| `/stm32-monitor` | ⭐ 启动实时变量监控 Web 面板 |
| `/read-var` | 运行时读变量 + 趋势分析 + 问题诊断 |

## 工具链总览

```
新机环境:
  /setup-stm32-env      → 一次性安装所有工具链

新工程:
  /migrate-keil         → 从 Keil 工程提取配置
  /init-stm32-project   → 生成 CMake + VSCode 构建调试配置

日常开发:
  Ctrl+Shift+B          → 编译 + 烧录 (程序自动运行)
  /stm32-monitor        → Web 实时监控面板 (趋势图/预设/导出)
  /read-var             → AI 辅助变量诊断分析
  F5                    → 断点单步调试
```

## stm32-monitor 使用

```bash
# 基本启动 (自动发现 ELF 和配置)
stm32-monitor

# 指定参数
stm32-monitor --elf build-fw/firmware.elf --target stm32f429zgtx --preset motor_status

# 高刷新率
stm32-monitor --interval 200 --preset can_bus
```

启动后浏览器打开 `http://localhost:8888`：

- **左侧**：ELF 变量树 + SVD 外设浏览 → 勾选加入监控
- **中间**：实时数值表格（名称/值/Hex/趋势箭头）
- **底部**：ECharts 趋势图（多变量叠加/zoom）
- **预设**：电机状态 / CAN 总线 / PC 协议 / 系统时序 一键切换
- **AI 分析**：导出快照 JSON → 释放探针 → 交给 Claude Code 分析
