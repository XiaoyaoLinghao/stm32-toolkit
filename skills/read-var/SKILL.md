---
name: read-var
description: 通过 pyocd-debug-mcp 读取 Cortex-M 目标板运行时变量并分析诊断（与 init-stm32-project 集成）
---

# read-var — 运行时变量调试方法论

**底层能力由 `pyocd-debug-mcp` 提供。本 skill 是调试策略层：决定何时读什么、如何分析数据、如何迭代诊断。**

## 前置条件

- `pyocd-debug-mcp` 已安装并注册 MCP（`/setup-stm32-env` 第 6 项）
- 项目有 `.pyocd-debug.json`（`/init-stm32-project` 第 11 个文件）
- DAP-Link 探针连接目标板，程序在运行

## MCP 工具速查

| MCP 工具 | 何时用 |
|---|---|
| `mcp__pyocd-debug__pyocd_elf_lookup(symbol="var_name")` | 查变量地址 |
| `mcp__pyocd-debug__pyocd_memory_read(address=0x..., length=4)` | 读内存（不停机） |
| `mcp__pyocd-debug__pyocd_read_symbol(symbol="var_name")` | 一步查符号+读值 |
| `mcp__pyocd-debug__pyocd_debug_sample_variable(location="addr或符号", interval=0.1, count=20)` | 批量采样 |
| `mcp__pyocd-debug__pyocd_svd_read(peripheral="GPIOA", register="ODR")` | 读外设寄存器（需 SVD） |
| `mcp__pyocd-debug__pyocd_debug_fault_analyze()` | HardFault 崩溃分析 |
| `mcp__pyocd-debug__pyocd_breakpoint_set(symbol="func")` + `pyocd_target_wait_halt()` | 设断点 + 等待触发 |

**重要**：MCP 工具的 `address`/`location` 参数同时接受整数地址和十六进制字符串（如 `"0x200000AC"`）。

---

## 三种场景工作流

### 场景 A：临时看一眼

> "speed 现在是多少？"、"CAN_received_ID 当前值是什么？"

```
1. mcp__pyocd-debug__pyocd_read_symbol(symbol="speed")  → 一步得值
2. 解析返回值，结合代码分析，回答用户
```

单次调用，即时返回。

### 场景 B：实时监控趋势

> "帮我监控 speed 的变化"、"采集 2 秒传感器数据"

```
1. 确认变量名和采样参数
2. mcp__pyocd-debug__pyocd_debug_sample_variable(location="speed", interval=0.1, count=20)
3. 拿到时序数据后，Claude 计算统计摘要（min/max/mean/range/trend）
4. 报告趋势、异常点
```

**采样参数指南**：

| 被观察过程 | interval | count | 总耗时 |
|---|---|---|---|
| 快速脉冲/跳变 | 0.1s | 20 | ~2s |
| 启动过程 | 0.05s | 40 | ~2s |
| 缓慢变化趋势 | 0.5s | 20 | ~10s |
| 长期稳定性 | 1s | 60 | ~60s |

> **LLM 延迟说明**：`sample_variable` 是阻塞调用——全部采集完才返回。Claude 在采集期间不能做其他事。不要设置过大的 count。

### 场景 C：问题导向诊断

> "电机不转了"、"传感器数据不对"、"CAN 通信断了"

**6 步诊断循环**：

```
Phase 1: 理解问题
  ├── 读相关模块源码
  ├── 梳理数据流和控制流
  └── 列出候选关键变量（3-5 个）

Phase 2: 探路
  ├── pyocd_elf_lookup() 确认变量存在 → 记录地址和大小
  └── 确认哪些变量在 SRAM 中（非寄存器）

Phase 3: 第一轮读取
  ├── pyocd_read_symbol() 读 3-5 个最关键的变量
  └── 分析数值 → 形成初步假设

Phase 4: 验证假设
  ├── 假设"队列阻塞" → 读队列长度、生产者/消费者索引
  ├── 假设"状态机卡住" → 读状态变量、定时器
  └── 可能需要 2-3 轮迭代

Phase 5: 时序确认（如需要）
  ├── 怀疑瞬态问题 → sample_variable() 采样
  └── 确认问题是否周期性

Phase 6: 报告
  ├── 诊断结论 + 证据链
  ├── 建议修复 + 具体文件和行号
  └── 如需确认：建议加什么日志或断点
```

**示例**：

> 用户："电机不转了"

Claude：
1. 读 [CAN_Controler/CANopen_Controller.c](CAN_Controler/CANopen_Controller.c) → 找到 `NMT_state`、`can_tx_queue`
2. `pyocd_read_symbol("NMT_state")` → 返回 0x7F (PRE-OPERATIONAL)
3. `pyocd_read_symbol("can_tx_queue")` → 队列长度 0
4. 诊断："CANopen NMT 卡在 PRE-OP，未进入 OPERATIONAL，PDO 被禁止。检查 NMT 主机是否发送 Start 命令"

---

## 数据结构与解码

### 标量值

嵌入式变量通常用 32 位存储：
- `u32`：无符号整数（最常见）
- `s32`：有符号整数
- `float`：IEEE 754 单精度浮点

Claude 拿到 hex 值后，需要根据代码上下文推断正确类型。模块化代码中常见模式：
- CAN/通信：`u32` ID，`u8` 或 `u32` 数据
- ADC/传感器：`u32` 原始值，可能需换算为物理量
- 定时器：`u32` tick 计数
- PWM：`u16` 占空比（0-65535）

### 结构体

大于 4 字节的变量，`pyocd_memory_read` 返回 hex dump。需要根据代码中的结构体定义手动解码字段和偏移。

### 数组

用 `pyocd_memory_read(address, length=N*elem_size)` 读取，Claude 自己解码元素。

---

## 与父级 skill 的集成

```
setup-stm32-env       →  安装 pyocd-debug-mcp
init-stm32-project    →  生成 .pyocd-debug.json
read-var              →  使用 MCP 工具进行运行时调试
```

**关系**：
- `setup-stm32-env` 安装底层能力（一次性）
- `init-stm32-project` 生成项目配置（每项目一次）
- `read-var` 使用前两者提供的工具和配置进行调试

---

## 限制

- **仅限全局/静态变量**：局部变量和寄存器中的值不可读
- **被优化掉的变量不可读**：Debug 编译 (`-O0 -g`) 缓解
- **单次读取 ~0.1-0.3s**：SWD 协议开销
- **不用于高速日志**：需要 >1kHz 采样请用 RTT 或 UART DMA
