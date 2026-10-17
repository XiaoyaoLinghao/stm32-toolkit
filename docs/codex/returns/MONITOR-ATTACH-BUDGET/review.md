# MONITOR-ATTACH-BUDGET 验收记录

## 结论和身份

ACCEPTED。正常附加预算与超时分类修复通过独立完整差异审查，获准的一次 F429 物理续验通过，CSV 和实际数据图已交付。真实浏览器继续 DEFERRED；没有远端动作或版本发布。

- Accepted base：`0b9f3a75c6490f1f7c2706b1eef907f0fa252de6`。
- 产品 CodeHead：`3b449fe365972738389f43f6a63d34a174eacdb3`，实施报告头 `67a077880dd9805f2df54ec1dc5905b60243d683`。
- 分支：`codex/monitor-attach-budget`。主代理负责规范、完整审查、实际运行和验收；ui03_impl 实现，ui02_contract_review 独立审查，子代理均为 gpt-6-sol/max。
- 运行源码：`D:\codex-tmp\mf1017\review`，干净 detached 产品 CodeHead。原脏工作区未修改。用户本轮明确授权修复后一次实测，不授权额外重试、烧录、reset、显式 halt/resume 或远端写入。

## 软件证据和审查闭环

主代理与独立审查者审阅完整 accepted-base→产品头差异及最后纯实施报告差异。R1 关闭了 `_read_batch` 对非超时错误意外扩大的分类；仅两种已暴露的 timeout 结果保留新码，其余维持旧 provenance。规范、计划和测试流程明确不改变 debug/read.py 的逐项读取错误隔离/重试，也不把模拟失败结果测试当成真实 memory.read 超时证据。无剩余产品阻断。

实现者初版相关 Python 回归 252 PASS/1 PLATFORM skip，UI 9 PASS，双类型检查、lint、build、dist 7 文件一致。Windows 目录句柄拒绝 rename 的测试被跳过，不据此宣称该场景 PASS。R1 改变的批次分支由实现者 11 项聚焦回归覆盖。主代理在精确最终产品头运行 23 项集成检查，exit0；证据在 `D:\codex-tmp\mf1017\test-review\command.json`、`pytest.log`、`exit.txt`。无重复发布矩阵。

生成物完整比对：app/index JavaScript、HTML、manifest 在资产名称替换后保持一致，zh chunk 由已审源码重新构建并通过 7 文件 byte-identical 构建校验；其编译符号重排不当作独立源码行为。运行脚本与上一已审脚本仅变更运行根、源码根、CodeHead，主代理和独立审查者均核对；离线预检及 Windows spawn PASS。

## 本轮物理与导出证据

唯一尝试认领 UTC 2026-10-17T08:01:43.084444Z，绑定成功 08:01:49.835883Z。此约6.75秒为包括静态准备、服务启动、附加和绑定核验的总时间，不是单次附加耗时。数据支持修复后的正常连接成功，不反推上次 pyOCD 的具体慢阶段。

原工程 `D:\codex-tmp\md1016\p`、原 data/session 完整保留；probe `pyocd:91d67402fe525a5d16bf226f59ab5ecea743eb69292e95719167263ed1fcbf8c`、target STM32F429ZGTx/physicalTarget stm32f429zgtx。

Build ID `2930d788ce61e99855cd55766e19a001b88bfd4d775a5b92014c3e80839635a1`，ELF SHA256 `364655a7b7f77558d7102d95a60157b2109b689d56fcb9bfff240e108968fca9`，project HEAD `a5ef52283cb7a0794c3ee295afca62dbea657148`。实际目录确认 `cu:3a9a / App/vs10_app.c / testtime`。

新组 `95b2d3b0-9cb8-425f-b529-454918fd4ea0`，revision1；run `b0e3c03b-0448-4c0f-9c1f-3d5b82ed439a`。正常 RUNNING 采样30秒，30个 OK uint32 值，序列0..29；首值262915、末值265802，每步增加97..102。时间UTC08:01:54.565910至08:02:23.566473，样本跨度29.0005636秒，实率0.9999805659Hz，最大延迟40.7319ms；subscriber/history/deadline drops均0。

主代理与独立审查者离线核验：所有历史行的绑定、run/group/revision、selector、序号和时间稳定一致；30行CSV逐字段等于历史行，复制件与原导出字节相同；manifest数量30、字节43229、SHA256 `5bc35584941839c67a8f185ec04075083dfe7ed788bed97c206c4e89f54514ee` 一致。export ID `b624a479-2212-4533-a963-6ee335807061`。窗口为本轮首样本至末样本+1ns，导出前未过滤窗口查询确认没有其他run混入。

物理输出根 `D:\codex-tmp\mf1017\hw`：`capture-summary.json`、`capture-samples.json`、`capture.csv`、`primary-verification.json`、`capture-events.jsonl`、进程退出证明和执行卡。`testtime-actual.png`/`.svg` 由上述30个实际值生成；主代理已看图确认，无模拟值或浏览器截图冒用。

## 生命周期和服务

正常停止、sampler/observation/exporter/history/groups close均记录完成后才写PASS。捕获进程34980及worker17592的精确PID/创建时间身份均已退出，采样结束后无额外硬件访问。首次服务停止前的UTC/local DateTime断言出现ENVIRONMENT脚本错误；离线修正比较后确认原服务身份及退出，不消费物理尝试、不改变产品或重连板卡。

8765已使用新产品头公开 Monitor open 恢复，PID33724，创建UTC2026-10-17T08:02:53.741465Z，受管会话29166；监听127.0.0.1:8765，快照无probe子进程。公开入口调用系统浏览器打开；没有读取浏览器/Monitor HTTP或绕过策略。当前采样停止、探针已释放，演示组及历史仍在。详见 `D:\codex-tmp\mf1017\service-restored.json`。

## 保留产物与清理限制

实现者及主代理的可归因测试清理命令均在执行前被自动策略拒绝：`blocked by policy`，未提供细分规则；未换工具或重试绕过。保留的准确目录见 `D:\codex-tmp\mf1017\result.md`。源码工作树供运行和回退，日志/命令/退出码、实测数据、图和CSV是保留证据；原工程、用户组、历史及共享依赖未删除。
