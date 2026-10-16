# Monitor 连接响应与实时提示修复规范

2026-10-16。Full accepted base：`dcd0a21f605782929051c26773a01e18c02ff55f`，已核对远端交付分支同 SHA。用户已授权后续 Monitor 本地开发、测试和服务更新无需重复审批；本轮修复用户报告的连接成功却显示 `MONITOR_RESPONSE_INVALID`，以及重复实时视图重置提示。版本保持 1.1.2，无新远端动作授权。

主代理拥有状态重建、规范、计划、集成、完整差异审查和接受。单一 gpt-6-sol/max 实现者拥有本切片产品代码、测试、生成资源与实现报告；另一个 gpt-6-sol/max 审查者独立复核，不允许作者自行接受。无 ownership override。工作分支 `codex/monitor-connect-response`，隔离实现树 `D:\codex-tmp\mufin1015\impl` 从上述干净 base 分出；原工作区与原交付分支保留。当前服务来源 `D:\codex-tmp\mv11216\review`，原产品 CodeHead `42669f7bfedbb2b197aad33efca9ad8e84cdd0ac`，直到接受新候选才更新。

## 三条用户场景

1. 普通连接和重新连接收到当前 Python `DebugFirmwareBinding.to_dict()` 的合法成功响应后，前端接受完整 binding，不误报写入结果未知；畸形、缺字段、未知字段仍拒绝。
2. 连续连接身份或采样轮次切换后，工作台仍正确清空旧实时数据，但相同重置提示不累积成多行。事件缺口提示仍保留；重复同一状态不清空已有有效样本。新轮次的合法样本仍可进入实时数值和采样率摘要。
3. 被接受的前端资源经既有构建机制进入 Monitor 服务；更新 8765 时保留既有演示工程、固件、观测组和历史数据库。已有 CSV/JSONL 历史导出入口保持。

## 冻结合同和状态所有权

Python `DebugFirmwareBinding` 为连接成功响应唯一源头，已发布序列化始终包含 `svdReadableRegions`。前端 `DebugFirmwareBinding` 增加必需的 `readonly MemoryRegionBinding[]` 字段；严格 guard 以既有 MemoryRegionBinding 规则校验非空数组。不得通过去掉后端字段、放宽 exact 校验、optional/null 容错或忽略失败来掩盖契约错位。connect/reconnect 共用相同 guard，release 合同不变。

既有 Python wire fixture 生成器产生当前模型与协议的真实序列化，前端回归消费该输出；不能仅依赖旧手写成功响应。使用合成身份，不能把本机实机身份提交为公共测试 fixture。生成 fixture、已提交 fixture、客户端及工作台测试保持一致。

实时状态仍归 reducer 管理。仅在 notice 插入层按 `kind + text` 去重，保留首条稳定标识；身份变化、bindingEpoch/runId、事件序号、revision、gap、样本身份校验和真实数据重置规则均不变。普通重置与事件缺口文本不能互相吞掉。此次用户截图不足以证明采样器失败，不能将显示无样本推断成设备故障或引入自动重连/重采。

## 边界和证据

实现范围限于 UI API 类型/guard、reducer 提示插入、受影响既有 fixtures/tests、构建生成的 ui_dist 及本切片报告。若查到另一独立样本接收缺陷，先将证据返回主代理再确定范围，不边实现边扩张。不改变硬件协议、firmware、持久数据、导出格式、认证/权限、版本号或依赖图，不新增工具框架。

遵循 `docs/testing/standard-test-procedure.md`。新证据全部为离线软件检查；浏览器仍因既有策略限制而暂缓，不能绕过限制抓取页面；不连接、复位、烧录或采样板卡。旧物理采样仅作已存在的历史证据，不计为新候选实机 PASS。服务更新采用原公开 open 入口及同 project/data/session；关闭旧服务会释放当前连接，随后由用户界面重新连接，不自动触碰板卡。

所需证据：当前 Python 生成 wire→TS guard→connect/reconnect 客户端成功路径；缺失/空/null/畸形及额外字段拒绝；反复状态切换去重、真实数据重置、同状态保持样本、gap 提示保留；受影响 UI 回归、typecheck、lint、build、verify:dist；主代理及独立审查者审查 accepted-base 到最终产品 CodeHead 全差异。无需完整 Toolkit 发布矩阵。
