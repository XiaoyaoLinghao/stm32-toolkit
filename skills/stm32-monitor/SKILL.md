---
name: stm32-monitor
description: 启动 STM32 实时变量监控 Web 面板。自动发现 ELF 符号和 SVD 外设，支持趋势图、预设、导出 CSV、AI 分析快照。
---

# stm32-monitor — STM32 实时变量监控面板

## 触发

用户输入 `/stm32-monitor`，或说"打开监控面板"、"实时监控变量"、"启动变量监控"、"监控电机状态"。

## 前置条件

- stm32-monitor 已安装（`pip install stm32-monitor`，Plugin setup 自动处理）
- 项目有 `.pyocd-debug.json` 或 `build-fw/firmware.elf`（`/init-stm32-project` 生成）
- DAP-Link 探针连接目标板，程序在运行

## 执行流程

### 1. 检查安装

```bash
stm32-monitor --version 2>&1 || echo "NOT_INSTALLED"
```

如果未安装：
```bash
pip install stm32-monitor
```

### 2. 检查探针状态

```bash
pyocd list 2>&1
```

- 如果看到 STM32F4 目标 → 继续
- 如果被其他进程占用（"already open"）→ 提示用户关闭 GDBServer 或其他 pyocd 进程
- 如果无探针 → 提示连接 DAP-Link

### 3. 自动发现项目配置

```bash
# 检查 .pyocd-debug.json
# 检查 build-fw/firmware.elf
# 检查 C:/ST/STM32CubeCLT_1.22.0/STMicroelectronics_CMSIS_SVD/ 下的 SVD 文件
```

### 4. 启动监控

```bash
stm32-monitor --elf build-fw/firmware.elf --target stm32f429zgtx --preset motor_status
```

如果用户指定了要监控的内容（如"监控电机"），自动选择对应预设：
- "电机" / "motor" → `--preset motor_status`
- "CAN" / "总线" → `--preset can_bus`
- "通信" / "串口" → `--preset pc_protocol`
- "全部" / "all" → 不指定 preset，用户自己选

### 5. 提示用户

```
✅ 监控面板已启动

   浏览器打开: http://localhost:8888

   功能:
   - 左侧: ELF 符号搜索 + SVD 外设浏览
   - 中间: 实时数值表格 (trend arrows)
   - 底部: ECharts 趋势图
   - 🤖 AI 分析: 导出快照 → 释放探针 → 使用 /read-var 深度分析

   与 Claude Code MCP 的关系:
   - 监控运行期间，/read-var 不可用 (DAP-Link 被占用)
   - 点击 "AI 分析" 按钮释放探针后，即可使用 /read-var
   - Ctrl+Shift+B 烧录会自动释放探针 (烧录完成后)
```

## 与其它 skill 的协作

```
/stm32-monitor          →  实时监控面板 (Web UI, 探针常驻)
         │
         ├─ 发现异常 ──→ 点击 "AI 分析" (导出快照 + 释放探针)
         │                      │
         │                      ▼
         │               /read-var (深度分析快照 JSON)
         │
         └─ 烧录新固件 ──→ Ctrl+Shift+B (自动释放探针)
                                │
                                ▼
                         /stm32-monitor (重新启动监控)
```

## 探针冲突处理

| 场景 | 处理 |
|---|---|
| 监控运行 + 用户调用 /read-var | 提示 "请先在监控面板中点击 AI 分析释放探针" |
| 监控运行 + 用户按 F5 调试 | 提示 "GDBServer 需要独占探针，请先停止监控" |
| GDBServer 运行 + 用户启动监控 | 提示 "GDBServer 占用探针，请先停止调试" |
| Ctrl+Shift+B 烧录 | 烧录进程自动接管 → 烧录完释放 → 监控需手动重启 |
