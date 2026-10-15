# MONITOR-UI-04 实现回报

## 身份与边界

- Full accepted base：`d1d9c36ba1b1a695ab68d6969506725dfbe360aa`；批准的规范与计划为 `docs/superpowers/specs/2026-10-15-monitor-ui04-chart-inspection-design.md`、`docs/superpowers/plans/2026-10-15-monitor-ui04-chart-inspection-plan.md`。
- 产品 CodeHead：`5c55aaf07d281bc2bb8d030928d6dcf05aca525b`；分支 `codex/monitor-ui-04-chart-inspection`；实现树 `D:\codex-tmp\mu41015\impl`。本回报在产品提交后单独提交，不记录报告提交自身的 SHA。
- 一个 `gpt-6-sol/max` 实现者负责批准的 UI 产品、回归、生成资产和指南；主代理拥有完整差异审查与独立验收。本轮没有浏览器、服务切换、安装、硬件、push 或其他远端动作。controller/API/wire/codec、后端、组编辑、历史/导出、依赖/锁文件、版本与构建配置未改。

## 三个连通场景

1. **各曲线按自身时间比较。** 图表从所有可见曲线的真实时间点取最早 ns 作共同起点，先以 bigint 求差再转相对毫秒。每条曲线将自己的 X 与数值成对交给 ECharts value 轴；晚加入、不同长度、同刻重复记录不会借用另一曲线下标。人工 gap 的空时间和 0ns 不参与时间域，读取空值保持 null，segment 改变和间断保留断线。轴标注相对时间与起点 UTC；tooltip 以 DOM `textContent` 展示每条记录的原始 UTC、数值和 ns，用户标签不作为 HTML 拼接。
2. **图内与工具栏同一缩放。** `datazoom` 的完整合法百分比经标准化传给现有 reducer.zoom，顶层配对字段优先，否则从 batch 取首个有效配对；非法值不改变窗口。宽度限于 1–100 个百分点，按钮按两端各 10 点缩放并保持中心，边缘时平移；最窄/全幅按钮禁用。相同范围在组件与 reducer 中幂等，更新图表走静默 `setOption`，handler 读取最新回调与范围并在卸载时解绑、拒绝迟到事件。新样本、隐藏/返回实时视图仍使用 reducer 范围，既有绑定/轮次及缺口重置保留。
3. **8 条选择可见且可释放。** 数值区显示已选数量、列表与逐项移除；即使已选项不在当前组表格，仍可移除。满 8 条时未选行的“显示曲线”禁用并显示中文原因；已选行可隐藏，移除后可以添加。图表区分无选择、等待样本和只有采集时间而无数值三种空状态。ECharts 图例仅作说明，关闭其独立点击隐藏。既有 reducer 的 8 条同步守卫和每条 600 点缓存算法未改。

## 实现者验证

从 `D:\codex-tmp\mu41015\impl\tools\stm32-monitor\ui` 使用已有 Node `v24.18.0` 与 lockfile 匹配的本地依赖副本运行，没有下载或安装。每项检查的 `TEMP`、`TMP`、`TMPDIR`、npm cache 和适用的 Vitest cache 均指向其 `D:\codex-tmp\mu41015\run` 子目录，npm 更新通知关闭。下表是最终产品源码、测试和 dist 字节的有效证据，日志保留完整 stdout/stderr。

| 命令 | 结果 | 日志（均位于 `D:\codex-tmp\mu41015\run`） |
| --- | --- | --- |
| `.\node_modules\.bin\vitest.cmd run` | exit 0；42 文件、369 测试通过 | `final4/test/test.log` |
| `.\node_modules\.bin\tsc.cmd -p tsconfig.json` | exit 0 | `final4/typecheck/typecheck.log` |
| `.\node_modules\.bin\tsc.cmd -p tsconfig.e2e.json` | exit 0 | `final4/typecheck-e2e/typecheck-e2e.log` |
| `.\node_modules\.bin\eslint.cmd src tests` | exit 0 | `final4/lint/lint.log` |
| `.\node_modules\.bin\vite.cmd build` | exit 0 | `final4/build/build.log` |
| `node scripts/verify-dist.mjs` | exit 0；7 文件逐字节一致 | `final4/verify-dist/verify-dist.log` |

先写的四个测试文件在旧实现上产生 9 个预期行为失败（`run/red/ui04-red.log`，exit 1），涉及时间坐标、有限域、缩放、图内事件、上限/移除和空状态。实现后，波形投影、真实 ECharts SSR 非同起点、zoom、选择、series/reducer 的定向复验为 8 文件 / 52 项通过（`run/focused3/focused3.log`）；补充排列顺序、8×600 投影与 SSR 后的双文件复验为 9 项通过（`run/focused4/focused4.log`）。既有 `series.test.ts` 同时验证采样与历史的 8×600 原缓存上限。首次完整 UI 运行有一项测试夹具隔离失败：`controller-coverage.test.ts` 用空效果 `zoom.reset` 制造初始状态副本，新幂等语义使其复用 `initialState` 并泄漏手动改动。分类为 **TEST/FIXTURE**，夹具改为显式浅拷贝；没有改 controller。定向 18 项及随后完整 369 项均通过。最终 UI 日志仅有 jsdom 的 navigation 未实现提示；构建仅有 Vite 大 chunk 建议，均未导致失败。

## 待独立验收与产物

主代理须在精确 CodeHead 的干净树审查 accepted-base→CodeHead 全部差异并执行计划内独立关键复验；本报告不是实现者自批或本地服务更新指令。真实浏览器手势、页面视觉/尺寸、axe、短地址关闭重开、真实 HTTP/WS 与物理采样均无本轮证据，继续由既定后续 owner 处理，模拟与 SSR 不算这些层的 PASS。

本实现者创建的运行子目录为 `red`、`dev1`、`focused2`、`focused3`、`controller-fixture`、`final`、`final2`、`focused4`、`final3`、`final4`；`final4` 为有效最终证据，`red` 与 `final` 保留最小失败分类依据。主代理是 `D:\codex-tmp\mu41015\run` 的清理 owner；完成独立审查后可按精确归属路径清理不再需要的缓存与旧中间产物，保留有效日志和所需诊断，不删除源码、测试或可复用 fixture。
