# MONITOR-UI-04 独立验收

结论：**ACCEPTED，本地软件切片**。三个用户场景闭合：按每点真实时间比较曲线、图内与工具栏缩放同步、8 条限制和跨组可达的移除入口。浏览器/视觉/真实手势与关闭重开继续 DEFERRED，不是发布验收。

## 身份与完整审查

- Full accepted base：`d1d9c36ba1b1a695ab68d6969506725dfbe360aa`。
- 最终产品 CodeHead：`19acd9bd9f944f4072490e7571563d2593f59eb3`；单独报告 head：`e6aeedabf7eda335e14384012446dc6d49490b15`，其 delta 仅 implementation.md。
- 分支 `codex/monitor-ui-04-chart-inspection`，实施者为单一 `gpt-6-sol/max`；主代理负责规范、完整差异审查与接受，另一只读 `gpt-6-sol/max` 审查者独立复核。主代理未写产品/测试。
- 独立树 `D:\codex-tmp\mu41015\review` 从干净 accepted base 切到精确 CodeHead；主代理审读完整 source/tests/guide/plan/report 差异、生成资产 manifest/index，使用逐字节重新构建核对生成 JS/CSS。API、Python、采样/缓存算法、依赖/锁文件、版本和构建配置未变。

## 发现与闭合

R1（PRODUCT）：首版 `5c55aaf07d281bc2bb8d030928d6dcf05aca525b` 的 `ui/src/chart/echarts.ts:45-46` 对所有域使用 `Math.max(1,span)`。两点相隔 500000 ns 时实际为 0..0.5 ms，却以 0..1 ms 作百分比缩放域。预期仅零/空域用退化回退，正跨度保持实际值。实现者先取得两条失败回归，再在同一分支修为 `span>0?span:1`；新增真实 ECharts SSR 检查 50–100% 窗口为 x=0.25/0.5。主代理与独立审查者复核完整首版差异和修订 delta 后关闭 R1，没有未闭合产品发现。

首次全量测试的初始化夹具问题归类为 **PRODUCT（测试夹具隔离）**：旧夹具借 no-op zoom.reset 获得浅副本，新幂等语义使其复用 initialState；改为显式浅拷贝，未改变 controller 产品代码。实现报告中的 TEST/FIXTURE 是该问题的描述标签，本验收按治理分类统一；不因此否定正确产品证据。

## 独立与实现者证据

主代理使用现有 Windows Node/npm 和锁文件匹配的依赖，TEMP/TMP/TMPDIR 和缓存位于本片短根；前后 review tracked/untracked 均干净：

| 检查 | 源身份与结果 |
| --- | --- |
| 首版关键投影/事件/缩放/选择/series/reducer/controller 10 文件 | `5c55aaf...`，83 项 exit 0；只属于首版及未变路径 |
| 最终受影响三文件（ui04-chart-projection、ui04-chart-interaction、echarts-option） | `19acd9...`，14 项 exit 0，覆盖正亚毫秒域及真实 engine |
| 最终 typecheck | exit 0 |
| 最终 verify:dist | exit 0，7 文件逐字节一致 |
| 完整 base→最终 CodeHead diff --check | exit 0 |

主代理实际命令与源 SHA 记录：`D:\codex-tmp\mu41015\verify-final\results.json`（首版）和 `verify-final2\results.json`（最终）。最终复验命令为 `npm.cmd run test -- tests/ui04-chart-projection.test.ts tests/ui04-chart-interaction.test.tsx tests/echarts-option.test.ts --cache=false`、`npm.cmd run typecheck`、`npm.cmd run verify:dist`。

实现者最终在 `run\round2-final` 执行完整 UI 42 文件/371 项、两个 typecheck、lint、build、verify:dist，全部 exit 0；主代理核对报告与日志但不冒记为自己的执行。必要失败证据在 `run\round2-red\sub-ms-red.log`。jsdom navigation 提示和 Vite 大 chunk 建议未造成失败，不能据此声称浏览器或性能通过。

## 交付边界与接续

无 push/PR/merge/tag/release 或服务更新。8765 保持 UI03，按整体授权在剩余 UI05/UI06 与集成接受后统一切换。用户授权无需再次审批；UI05/UI06 规范已独立审查、由主代理冻结后接续。清理 owner 为主代理，依赖暂保留用于后续同锁文件切片复用，最终清理见本地完成执行账本。

从 UI04 授权派发到接受约半小时，其中同时完成 UI05/UI06 设计和独立契约审查；不将并行墙钟时间冒记为精确编码工时。验证范围限受影响 UI，未运行无关发布矩阵。
