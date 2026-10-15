# MONITOR-UI-05 独立审查与接受

2026-10-16；结论 **ACCEPTED**。主代理拥有规范、计划、完整差异审查和接受，产品及实现测试由单一 gpt-6-sol/max 实现者完成；独立 gpt-6-sol/max 只读审查者复审。无产品 ownership override，无远端权限。

- Full accepted base：`acf6953221f87b0e7951e5c0db4d9a57a381313e`。
- 最终产品 CodeHead：`24c550be5ae6061671ba922dd86c7bc243ac51a6`；实现报告提交 `e92fb4d384db7efc1dc96ef586617f077fab96f8`。
- 实现分支 `codex/monitor-ui-05-group-workflow`；独立审查树 `D:\codex-tmp\mu51015\review` 精确 detached CodeHead、前后干净。没有 PR、push 或其他远端动作。

## 完整差异和闭合发现

主代理与独立审查者读取了 accepted-base→最终产品的全部手写源码、测试、指南与规范计划差异，并完整复核首轮候选 `dd907667ec6f6ace9cf7176d2f152e7714123bfb`→最终修订。生成资源依据源代码、manifest/index 引用及独立逐字节重建核验。未改 Python/API/wire/依赖/锁文件/版本/构建配置；锁文件 SHA256 仍为 B7830444281738261024EDB3A601FEB51D2A3603D28E1F02C47CD8067DD94448。

1. **PRODUCT，queued ACK 覆盖草稿，已闭合。** 旧 App Save 闭包可能在新输入 B 已派发而未重绘时提交 A；只比较 generation 的 ACK 会覆盖 B。最终 controller.ts:351 捕获不可变 submittedDraft，reducer.ts:106 在同 generation 下保留较新 editable 字段、推进 ACK 的 ID/revision 并采用 canonical baseline；不同 generation 仅 upsert。App/Preact create/update 红回归证明原先失败，最终保留 B 为 dirty，后续 GET 失败也不丢稿，下一次更新使用正确 revision。
2. **PRODUCT，冲突后旧 revision 可再次写入，已闭合。** 原先 Save 可绕过刷新按钮重发。controller.ts:57、157、190 的同步 fence 在 fail dispatch 前建立，只在完整 current GET 的数组已进入 reducer 且 groupsNeedRefresh=false 后放行；reducer.ts:99、198 维持单一 UI 标记。关闭提示、导航、另存、失败 GET 和尚未重绘均不能解锁。组件禁写但保留草稿编辑与刷新入口。queued/direct、create/delete/import、GET失败及成功后改名的新提交均有回归。
3. **PRODUCT，通用错误误归因为组错误，已闭合。** MONITOR_REQUEST_INVALID 亦用于探针/采样/导出，全局中文提示已改为通用请求无效；组建议按 recovery scope 呈现，presentation 回归通过。

原测试中“输入即搜索”、空选择自动选择首组、改变草稿后仍重放旧写等断言已按批准合同调整，保护意图没有删掉。实现报告将旧交互断言失败写作 TEST；主代理按项目分类归为 PRODUCT（测试契约适配），与后端、权限或物理环境失败无关。文档末尾多余空行属 REPORT，由主代理在接受文档提交中清理，不改产品字节。

## 证据与接受范围

实现者在最终产品字节运行完整 UI **44 文件 / 398 测试**、两个 typecheck、lint、build、verify:dist，均 exit 0；7 个资源逐字节一致，证据 `D:\codex-tmp\mu51015\run\r1-final\<check>\result.log`。R1 红日志在 r1-red、r1-red-conflict、r1-red-queued-conflict；具体命令见 implementation.md。

主代理在独立精确 CodeHead 运行 `D:\codex-tmp\mu51015\verify.ps1`：组工作流/UI、导入生命周期、恢复、controller/reducer、App 与 presentation 共 **11 文件 / 139 测试**；`npm.cmd run typecheck` 和 `npm.cmd run verify:dist` 全部 exit 0。命令、时间、源码 SHA 和日志路径在 `D:\codex-tmp\mu51015\verify-final\results.json`。测试未改源码，独立树保持干净。

四条用户场景已连通，R1 无未闭合产品发现；主代理据上述独立证据接受。真实浏览器、视觉/视口/手势/axe、HTTP/WS、短地址关闭重开以及物理采样继续 DEFERRED，由既定后续主代理/硬件 owner 承接；jsdom 与构建不计作这些层的 PASS。8765 暂保留 UI03，UI06 和最终集成接受后统一切换。清理由主代理负责，依赖副本先移交 UI06 后清除；保留最终证据与最小失败依据，不触碰原始脏工作区。
