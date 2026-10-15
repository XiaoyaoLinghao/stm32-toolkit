# MONITOR-UI-03 独立验收

结论：**ACCEPTED，本地 UI03 软件切片**。浏览器、视觉和真实关闭重开验证继续 **DEFERRED**；不是发布或硬件验收。

## 身份与责任

- Accepted base：`261f49027dc1050b35720717a41efba687c72a32`。
- 最终产品 CodeHead：`92c537835dbbad9b09096da003e77d2a4ff6a11d`；单独实现回报 head：`dd97cc24c393ddf2e4f6db005620259711722cc0`。回报 delta 只修改 implementation.md，已核对最终产品身份与 355 项测试证据。
- 主对话代理拥有规范、计划、集成、完整差异审查与验收；单一 `gpt-6-sol/max` 实现代理拥有产品和测试；独立只读 `gpt-6-sol/max` 审查代理复核完整差异。主代理没有实现产品代码。
- 分支 `codex/monitor-ui-03-live-recovery`，无 PR；没有远端动作或发布。原始工作区未提交状态保留。用户批准的本地服务切换在独立验收后执行。
- 主代理在干净独立树 `D:\codex-tmp\mu31015\review` 审阅 accepted-base 到首轮候选的全部源码、测试、指南和规划文档，再审阅最终修订；未变字节沿用同轮已完成的审查。生成资产通过独立同源 rebuild 逐字节核对。

## 用户场景与发现闭环

1. socket 构造期间显示正在连接，实际 onopen 才显示已连接。连接状态与保留值的新鲜度分开；心跳和普通状态读取不将旧值标新。
2. 断流保留工作台、草稿和历史；显式重新连接通过身份核对 GET 和原游标恢复一个订阅。检查/连接可取消，旧回调和迟到响应失效；普通错误可就地重试完整意图，认证或会话变化明确阻断。该流程没有探针/采样 POST。
3. 事件缺口有中文提示与手动刷新。每次 GET 包含本次开始的 gap/state 代次，新缺口或新 live 状态使旧 GET 仅结算请求，不覆盖更新状态。写入成功后的失败刷新只重试 GET。

首轮候选 `478ebe11f881f408f8e423609333139c20cd92b4` 为 REVISION_REQUIRED：通用 read 重试闭包复用了旧状态代次并绕过实时恢复忙碌守卫。主代理和独立审查者分别确认同一根因，记录在 `D:\codex-tmp\mu31015\round1-review.md`。原实现者添加四项先失败的回归，再使状态重试重新经过 refreshStatus；最终修订覆盖 gap/state 更新、Preact 提交前 checking/connecting 守卫、取消后重试和成功写后只读重试。两名审查者确认产品发现已关闭，无未解决产品阻断项。

## 最终独立验证

Windows、既有 Node/npm、锁文件匹配的依赖副本；未下载或安装。主代理对精确最终 CodeHead 执行，前后 tracked/untracked 状态均干净：

| 命令/检查 | 结果 |
| --- | --- |
| `npm run test -- tests/ui03-live-recovery.test.ts tests/ui03-recovery-ui.test.tsx tests/reducer.test.ts tests/live.test.ts tests/live-coverage.test.ts tests/recovery.test.ts tests/recovery-ui.test.tsx tests/controller.test.ts tests/controller-coverage.test.ts tests/app-errors.test.tsx --cache=false` | exit 0，10 文件 / 123 项 |
| `npm run typecheck` | exit 0 |
| `npm run verify:dist` | exit 0，7 文件逐字节一致 |
| `git diff --check <base> <CodeHead>` | exit 0 |
| 范围与回报核对 | API wire/codec、bootstrap、Python、版本、依赖/锁文件、构建配置没有修改；报告最终提交仅修改文档 |

主代理完整命令、时间和源身份见 `D:\codex-tmp\mu31015\verify-final\results.json` 及同目录三份日志。实现者另外在最终产品字节执行完整 UI（40 文件 / 355 项）、两项 TypeScript 检查、lint、build、verify:dist，均 exit 0；原始日志在 `run/round2-final`。主代理已核对日志，但不将实现者证据记为自己的执行。jsdom navigation 提示和 Vite chunk 大小建议未造成失败；它们不构成浏览器或性能验收。

首轮独立 119 项、typecheck、dist PASS 属于首轮产品，不替代最终复验。四项修复前失败记录保留在 `run/round2-red/ui03-live-recovery.log`。

## 服务与清理

独立接受后，主代理经原受管会话 78460 停止旧 PID 23916，确认进程退出及 8765 端口释放，然后以现有公共 `stm32_monitor serve --serve-ui --json` 启动最终 CodeHead 的 review 源。新受管会话 1069、PID 29524 在 `127.0.0.1:8765` 监听，启动摘要确认 `http://127.0.0.1:8765/`。保留相同项目、DataRoot 和 session；未手动删除锁/运行记录，没有打印或保存 token/accessUrl。无凭据证据见 `D:\codex-tmp\mu31015\service.json`。服务使用精确产品提交，不因验收文档提交改变运行源。

主代理清理 23 个本轮自有依赖副本、缓存、临时目录和中间产物路径，无失败；全部删除目标及父级均验证在任务根内且无 reparse point，记录见 `cleanup.json`。保留源码、Git、跟踪 dist、最终命令证据、首轮审查记录、修复前最小失败证据及运行中的 service-temp；未重试其他任务此前被拒绝的清理。清理后 review 工作树仍干净，8765 仍由同一新 PID 监听。

从批准账本提交（10:22:07 UTC）到新服务监听确认（10:46:25 UTC）约 24 分钟；首版实现及实现者检查约 15 分钟，独立审查、修订及最终独立复验约 7 分钟，服务切换约 2 分钟。该墙钟阶段比例约 15:7:2，阶段内存在并行工作，不冒充纯编码/验证/报告的精确工时。未扩大到发布矩阵，也未引入新的验证工具。

浏览器拦截排查、页面读取、axe、截图、视口和关闭后短地址重新打开仍 DEFERRED 给主代理，未将模拟测试或进程监听当作真实 HTTP/WS、页面交互或物理采样证据。
