# MONITOR-UI-06 实现回报

## 身份与范围

- Full accepted base：`3ee0bc2180047b45bbf3d2dae2dd2deed4e46e6a`；产品 CodeHead：`0edb2183c154d366d3f261a90e08d6ed54505e26`；分支 `codex/monitor-ui-06-history-freshness`，实现树 `D:\codex-tmp\mu61015\impl`。本报告在产品提交后另行提交，不记录报告自身 SHA。
- 主代理冻结的规范、计划分别为 `docs/superpowers/specs/2026-10-15-monitor-ui06-history-freshness-design.md`、`docs/superpowers/plans/2026-10-15-monitor-ui06-history-freshness-plan.md`；运行组归属补充由主代理另以 `0290f8b6` 冻结并经独立契约审查。实现者只改产品源码、相应回归、用户指南和生成 UI 资产；主代理及独立审查者负责完整差异与接受。
- 未修改 API/wire/codec、Python、导出契约、图表投影/缓存、组写规则、依赖/锁文件、版本或构建配置。没有浏览器、服务切换、安装、物理硬件或远端动作。

## 三条连通场景

1. **历史输入与结果。** HistoryPanel 本地草稿与上次成功同步范围分离。A 查询在途时可编辑 B；A 成功、失败或原操作重试后 B 不被覆盖，新的结果只有在草稿仍未修改时才同步到输入。历史在途上下文由 reducer 只读保存 `{requestId,query,navigation}`，迟到旧 ID 不能清新请求。查询、下一页、上一页共享同步 ref 锁；Controller 对显式新调用仍为 latest-wins。界面区分在途范围与已成功结果的 UTC 半开范围，失败保留旧结果，只有成功空页显示空结果。历史边界校验限于 HistoryPanel 的 `0 <= start < end <= I64_MAX`；共享 `historyInput/inputNs` 与 ExportPanel 行为未改。
2. **重试、分页与导出。** 失败查询的重试重新建立 ID/在途上下文，保留最初的范围、cursor 和筛选条件；页栈只在成功后推进。App 的真实 OperationRegion 显示普通失败并提供原操作重试；历史每行显示 UTC、观测项、值或读取错误以及轮次/序号/值序位。导出仍只使用上次成功查询范围，不提前采用在途查询或 B 草稿。
3. **实时采集时效与归属。** `lastSampleCapturedAtUtc` 只在通过身份/组/轮次守卫的样本接受路径写入；heartbeat、状态重基、断流与 gap 不伪造采集时间，binding/run 重置清空。数值行显示各自 UTC；状态栏无样本不展示假零，有样本而非 fresh 时标为“上次样本”。实时表按服务端当前轮次的组 ID/版本投影，编辑目标切换不改表归属；列表未匹配旧版本时只显示同轮次已接受的旧行。App 的单一 fresh 同时核对运行组版本和 live runId，组更新 ACK 到服务端下个状态事件之间即可标旧。图表与表共用来源行显示 runId/groupId/revision；SamplingControls 不把较新版本组名归给旧运行轮次。

## 实现者验证

全部命令从 `D:\codex-tmp\mu61015\impl\tools\stm32-monitor\ui` 使用既有 lockfile 匹配依赖执行。`TEMP/TMP/TMPDIR`、npm 缓存、适用的 Vitest 缓存和完整 stdout/stderr 均在每次运行的 `D:\codex-tmp\mu61015\run` 子目录；npm 更新通知关闭。`final1` 对应上述固定产品 CodeHead。

| 命令 | 结果 | 日志（根为 `D:\codex-tmp\mu61015\run`） |
| --- | --- | --- |
| `npm.cmd run test` | exit 0；49 文件、415 测试通过 | `final1/test/result.log` |
| `npm.cmd run typecheck` | exit 0 | `final1/typecheck/result.log` |
| `npm.cmd run typecheck:e2e` | exit 0 | `final1/typecheck-e2e/result.log` |
| `npm.cmd run lint` | exit 0 | `final1/lint/result.log` |
| `npm.cmd run build` | exit 0 | `final1/build/result.log` |
| `npm.cmd run verify:dist` | exit 0；7 文件逐字节一致 | `final1/verify-dist/result.log` |

红证据：`red/history.log` 的 5 项历史行为回归和 `red/live.log` 的 3 项采集时效回归在改动前失败；运行组补充的 `red-active/selector.log` 有 3 项预期失败，`red-active/app-live.log` 在真实 App 组版本 ACK 后仍显示 fresh 上失败。修复后新增 `ui06-*` 五个测试文件均纳入 415 项绿色矩阵。`focused4/tests.log` 覆盖历史、导出及恢复共 59 项；`active-green2/tests.log` 覆盖运行组 selectors/App 共 10 项。

首次完整 UI `prematrix/full-ui.log` 有 410 项通过、1 项旧 `components-coverage.test.tsx` 断言失败：新增空 UTC 占位后，原测试把整表 `-` 计数误当成仅类型列计数。分类为 **PRODUCT（测试契约适配）**；将断言收窄到每行 UTC 与类型单元格，未改产品显示逻辑，最终 415 项全绿。完整 UI 日志中的 jsdom navigation 未实现提示和构建的大 chunk 建议均不使检查失败。

## 待独立接受与产物

主代理须在精确 CodeHead 的独立干净树审查 accepted-base→CodeHead 全部差异并运行计划内关键验证；本报告不构成实现者自批。真实浏览器视口/交互/axe、HTTP/WS 服务、关闭重开及物理采样仍由后续 owner 取得证据，jsdom 与模拟样本不算实机 PASS。不得据此报告切换服务或更新 8765。

本轮运行子目录为 `red`、`focused1`、`focused2`、`focused3`、`focused4`、`focused5`、`prematrix`、`red-active`、`active-green`、`active-green2`、`final1`。主代理是 `D:\codex-tmp\mu61015\run` 的清理 owner；独立接受后按精确归属清理无用缓存与中间产物，保留最终证据、最小红/失败日志和源码测试。
