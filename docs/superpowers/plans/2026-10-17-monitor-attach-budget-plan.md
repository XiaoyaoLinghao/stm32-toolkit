# Monitor 附加超时修复实施计划

Accepted base：`0b9f3a75c6490f1f7c2706b1eef907f0fa252de6`。规范：[设计](../specs/2026-10-17-monitor-attach-budget-design.md)。当前用户修复及一次续验授权、既有本地开发无需重复审批适用于本计划。主代理负责接受；不得由实现者自审或执行远端动作。

## 1. 单一实现者的纵向修复

ui03_impl 独占产品实现及测试：Toolkit probe/client.py、monitor_observation.py 和对应测试；Monitor probe_session.py、runtime.py 的目录超时映射、相关 runtime/probe-session 测试；UI presentation/zh.ts、失败卡/中文映射测试和必要 ui_dist 生成物。不得更改全局服务或 worker 时限、锁、协议模式、依赖锁文件或其他行为。主代理独占本规范、计划、最终审查报告。测试流程若需记录本次状态/时限条款，由主代理更新并交审。

先补能证明差异的测试，再按设计修复。优先选低耗时但实际经过请求编码及 Service 生命周期的测试，不能仅镜像常量。每次命令保存 argv、exit 和完整输出。Python TEMP/TMP/TMPDIR、pytest basetemp/cache 与 UI 缓存都指向 D:\codex-tmp\mf1017 的独占子目录；不污染旧工作树或依赖。复用本机现有依赖，不安装。

## 2. 实现层验证

实现者运行 test_probe_client、test_monitor_observation、Monitor test_probe_session、涉及连接失败状态的 runtime 测试，以及既有 ProbeService/worker attach deadline、queued expiry、cancellation、cleanup 回归的相关节点。UI 运行相关 failure/operations/Chinese tests、typecheck、build、verify-dist；不运行浏览器。保留清晰结果，不扩大到发布矩阵。

单独产品提交后记录完整 CodeHead；实现报告写在 docs/codex/returns/MONITOR-ATTACH-BUDGET/implementation.md，仅引用 accepted base 和报告前 CodeHead，不把自身最终 SHA 写入自身报告。

## 3. 独立审查与集成

主代理从返回提交创建精确 HEAD 的干净隔离 review 工作树，审完整 accepted-base-to-final-head 差异；ui02_contract_review 独立只读审查同一差异。主代理运行针对新合同及生命周期的精选集成验证，不重复全部实现套件。阻断修正返回同一实现者和分支；同问题两轮不收敛则重做设计。

## 4. 获准的一次物理续验

实现者在 D:\codex-tmp\mf1017\hw 准备上一已审 capture.py/.ps1 的新副本，只改根路径、精确 review CodeHead 和必要日志路径，保留一次尝试锁、身份验证、错误清理、CSV 窗口与行级绑定校验。主代理和审查者先审脚本差异，离线语法/预检/Windows spawn 通过后方可运行；不能复用已消费 mh1017 attempt。

主代理执行：停止当前自有 8765 服务并证实相关 PID/创建身份退出；确认端口空闲后使用新候选一次正常 OBSERVE 连接，30 秒/1000ms 采样，新建独立演示组，停止/flush/close。无任何显式 reset/halt/resume/flash 或额外重连。总脚本140秒取消预算与180秒进程硬界保持；超时仍属失败，不用延长总预算换 PASS。

复用原 project D:\codex-tmp\md1016\p、data D:\codex-tmp\md1016\data、session monitor-demo-20261016；精确 build/ELF/probe 身份来自旧执行卡并在新卡复核，不能仅依赖旧实测结论。第一异常停止，保留最小失败证据。清理未知则阻断新硬件。

## 5. 交付与收尾

物理成功后主代理独立分析值、身份、时间、丢弃及 CSV，使用现有 ECharts/sharp 生成真实数据 PNG/SVG。恢复8765为已接受候选源码，保持原工程和历史；服务恢复本身不重连探针。提供中文结果、波形和 CSV 链接，明确真实浏览器暂缓。

清理所有不再需要且归属明确的本轮测试目录；保留源码、日志/退出证据、实测CSV/图、执行卡与用户数据。自动策略拒绝的清理路径保留并报告，不绕过。GitHub push/PR/tag/release 均不在本次授权。
