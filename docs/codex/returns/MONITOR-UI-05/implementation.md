# MONITOR-UI-05 实现回报

## 身份和范围

- Full accepted base：`acf6953221f87b0e7951e5c0db4d9a57a381313e`；批准规范与计划分别为 `docs/superpowers/specs/2026-10-15-monitor-ui05-group-workflow-design.md` 和 `docs/superpowers/plans/2026-10-15-monitor-ui05-group-workflow-plan.md`。
- 产品 CodeHead：`24c550be5ae6061671ba922dd86c7bc243ac51a6`；分支 `codex/monitor-ui-05-group-workflow`；实现树 `D:\codex-tmp\mu51015\impl`。前一产品候选 `dd907667ec6f6ace9cf7176d2f152e7714123bfb` 留在同一分支，R1 修订单独提交。本回报在产品提交之后另行提交，不记录报告自身的 SHA。
- 一个 `gpt-6-sol/max` 实现者负责 UI、状态、控制器、回归、生成资产及用户指南；主代理和独立审查者负责完整差异审查与接受。本轮没有浏览器、服务切换、安装、硬件、push、PR 或其他远端动作。未改 API/wire/codec、Python、依赖/锁文件、版本或构建配置。

## 四条连通场景

1. **草稿与导航。** reducer 持有单一编辑基线和 generation；点当前组保留脏稿，切组、新建或载入最新版本先确认放弃。目标在确认前消失时保留原稿并提示。列表读写期间 reducer 和界面均锁住编辑与选择；明确发起写入可先退休较早的列表读取，迟到结果不能覆盖写入确认。删除确认绑定显示的 ID、revision 和编辑 generation；导航、新建、刷新、另存以及同事件旧按钮点击不能把旧确认升级到新目标。
2. **保存、删除与运行标签。** 新稿没有已保存的下次采样目标。服务端保存 ACK 先更新组、身份、revision 与 canonical baseline，再进行可能失败的列表 GET；服务端删除 ACK 立即移除目标并清空对应编辑器；导入 ACK 立即合入返回组，后续 GET 失败只重试读取。创建/更新期间若 App 尚未重绘而较新的输入已经排队，ACK 保留较新可编辑内容为 dirty，同时采用 ACK 的 ID/revision；下一次保存使用新 revision。不同 generation 的迟到 ACK 只更新组列表。采样区分别显示下次已保存目标与服务端当前运行组，改稿不改变当前运行。
3. **冲突恢复。** `MONITOR_GROUP_CONFLICT`、`MONITOR_GROUP_NOT_FOUND`、`MONITOR_IMPORT_CONFLICT` 只提供组列表 GET 核对，绝不自动重发写入。冲突在派发失败前同步建立控制器写门禁；失败提示关闭、导航、另存和 GET 失败不能清门禁。只有完整、当前的组 GET 返回数组且 reducer 已采纳同一数组、清除 `groupsNeedRefresh` 后，保存/删除/导入才可再次发送。其间编辑、导航、导入预览和刷新仍可用，界面持续解释刷新要求。刷新后原组缺失或版本变化则拒绝旧 ID 更新；用户可载入最新版或另存为新组并核对名称。同 revision 的名称冲突刷新后允许用户改名并发起新的提交。当前 controller 成功初始化后 `initialized` 不再回退，因此冲突后不存在同 controller 的重新初始化清门禁路径；新 controller 初始门禁为关，既有 controller 只由成功且已采纳的组 GET 清门禁。
4. **目录与导入。** 空查询由显式“搜索/加载”发送；变量、寄存器各自的结果绑定当前身份与查询，旧查询行仅可查看而不能加入草稿。服务端 `sampleable:false` 的寄存器不能添加，并显示 access/readAction 原因。导入预览列出组名、数量及不覆盖说明；确定性输入错误、版本/名称冲突和结果未知分别提供不同恢复。全局 `MONITOR_REQUEST_INVALID` 文案保持适用于非组操作，组输入建议只在组恢复范围出现。

## 实现者验证

从 `D:\codex-tmp\mu51015\impl\tools\stm32-monitor\ui` 使用已有本地 lockfile 匹配依赖运行，没有下载或安装。每项检查的 `TEMP`、`TMP`、`TMPDIR`、npm cache 和适用的 Vitest cache 均在 `D:\codex-tmp\mu51015\run` 的该项子目录，npm 更新通知关闭。下表对应最终产品源码、测试与 dist 字节；完整 stdout/stderr 保存在所列日志。

| 命令 | 结果 | 日志（根为 `D:\codex-tmp\mu51015\run`） |
| --- | --- | --- |
| `npm.cmd run test` | exit 0；44 文件、398 测试通过 | `r1-final/test/result.log` |
| `npm.cmd run typecheck` | exit 0 | `r1-final/typecheck/result.log` |
| `npm.cmd run typecheck:e2e` | exit 0 | `r1-final/typecheck-e2e/result.log` |
| `npm.cmd run lint` | exit 0 | `r1-final/lint/result.log` |
| `npm.cmd run build` | exit 0；625 模块 | `r1-final/build/result.log` |
| `npm.cmd run verify:dist` | exit 0；7 文件逐字节一致 | `r1-final/verify-dist/result.log` |

另有最终组、恢复、App 定向复验 `npm.cmd run test -- --run tests/ui05-group-workflow.test.ts tests/ui05-group-ui.test.tsx tests/app-errors.test.tsx tests/recovery.test.ts tests/recovery-ui.test.tsx`，exit 0、5 文件/57 测试，日志 `r1-focused-final/focused.log`。完整 UI 日志含 jsdom 的 navigation 未实现提示，构建含 Vite 大 chunk 建议，均未使检查失败。

红证据：最初 `red/ui05-red.log` 和 `red/ui05-ui-red.log` 分别复现组行为及 UI 的四项预期失败；`red2/focused.log` 复现旧查询仍可加入和导航锁中的取消；`red3/presentation.log` 复现共享错误码被误称为组请求。R1 的 `r1-red/app-queued.log` 在真实 App/Preact 同事件输入 B→旧 Save 上复现创建与更新两项 ACK 覆盖；`r1-red-conflict/conflict-gate.log`、`r1-red-queued-conflict/queued-conflict.log` 复现冲突后直接再次写入和成功 GET 尚未被 reducer 采纳前写入。修正后上述回归均包含在最终绿色矩阵。

既有测试语义调整有明确原因：`app-errors.test.tsx`、`catalog-chart.test.tsx`、`recovery-ui.test.tsx` 在输入后显式点击“搜索/加载”，并检查旧查询结果不能加入；`controller-coverage.test.ts`、`controller.test.ts` 先把欲提交的草稿置入编辑状态，再断言只能提交当前 generation 的草稿；`groups-panel.test.tsx` 检查删除回调带 ID/revision/generation；`reducer-coverage.test.ts` 改为未知目标不清稿、空选择刷新不自动选择首组；`recovery.test.ts` 将已编辑后的旧写重试判为失效，由新提交发送当前稿，并以 generation 验证迟到 ACK 不能改当前编辑器。读请求防重及迟到过滤、写家族互斥、未知写结果只 GET 核对和成功写入后 GET 失败只重试 GET 均继续由完整回归覆盖；未删除这些保护或改写 UI03 的状态读取恢复路径。首次完整 UI 运行仅因旧测试仍预期“输入即搜索”失败，分类为 **TEST/旧交互断言**，修订该断言后 391 项通过；R1 状态修订后重新完整运行 398 项通过。

## 待独立接受与产物

主代理须在精确 CodeHead 的独立干净树审查 accepted-base→CodeHead 的全部差异，运行计划中的独立关键复验，并判定接受；本报告不是实现者自批。真实浏览器、页面视觉/尺寸、axe、短地址重开、真实 HTTP/WS 和物理采样没有本轮证据，仍由既定后续 owner 处理；模拟与 jsdom 不算这些层的 PASS。服务按 UI06/集成验收后计划处理，不能根据本报告切换。

实现者创建的运行子目录为 `red`、`red2`、`red3`、`dev1`、`dev2`、`dev3`、`dev4`、`dev5`、`final1`、`final2`、`final3`、`r1-red`、`r1-red-conflict`、`r1-red-queued-conflict`、`r1-focused-ack`、`r1-focused-gate`、`r1-focused-final` 和 `r1-final`。`r1-final` 是最终有效矩阵，R1 红日志及首次测试语义失败日志保留最小诊断依据。主代理是 `D:\codex-tmp\mu51015\run` 的清理 owner；独立验收后只按精确归属路径清理不再需要的缓存与中间产物，保留有效日志、必要失败证据及源码/测试/可复用 fixture。
