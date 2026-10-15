# MONITOR-UI-04 波形查看实施计划

日期：2026-10-15。状态：**拟议，待批准**。对应同日 `monitor-ui04-chart-inspection-design.md`。Full accepted base：`d1d9c36ba1b1a695ab68d6969506725dfbe360aa`，产品继承 UI03 `92c537835dbbad9b09096da003e77d2a4ff6a11d`。

## 账本与启动条件

- 当前阶段为规划。主代理拥有架构、规范、计划、集成、完整差异审查与验收；两个只读审计分别检查波形/历史和组编辑，不承担设计领导或实现任务。
- 分支 `codex/monitor-ui-04-chart-inspection`，规划/实现树 `D:\codex-tmp\mu41015\impl`；由接受基线新建且初始干净。运行 UI03 的 `mu31015/review` 不作开发树。原始工作区的旧改动保留。
- 按项目 AGENTS.md 的 Delivery workflow 第 2 条：“After user approval of both specification and plan”，批准后才由主代理派发一个 `gpt-6-sol/max` 实现代理。当前请求只授权梳理规范与计划，尚未派发实现。
- 无 PR、push/PR mutation/merge/tag/release/close/远端删除权限；无主代理产品实现例外。实现代理不自行接受、不递归委派，不覆盖他人改动。
- 本轮只形成文档，不重复产品测试。后续完成实现和独立验收后，是否切换 8765 以当时用户对 UI04 的授权为准；不把 UI03 的单次切换授权自动沿用。

## 一个连通切片，一个实现 owner

三条场景必须共同闭合：正确时间坐标 → 图内/工具栏缩放同步 → 8 条选择限制与移除入口。它们共享图表状态和视图更新，不拆成并行写代理。

实现者可写（相对 tools/stm32-monitor）：

- `ui/src/chart/echarts.ts` 和必要的纯时间投影 helper；`chart/zoom.ts` 只限合法范围标准化/幂等，`chart/series.ts` 的样本、drop 与缓存算法不改。
- `ui/src/components/LiveChart.tsx`、`ChartZoomControls.tsx`、`LiveTable.tsx`，以及一个按需新增的已选曲线呈现组件。
- `ui/src/app.tsx` 的图表/曲线连接、`state/selectors.ts` 的纯显示派生、`state/reducer.ts` 的 zoom 幂等与原选择上限守卫。`state/model.ts` 仅允许必要的内部派生展示类型，不新增权威存储或改持久化/传输模型。
- `ui/src/presentation/zh.ts` 与相关 `styles.css`，对应 `tests/**` 和确因新文案/轴表示受影响的既有 `e2e/**` 源；不新增 browser runner 或测试平台。
- 通过现有构建生成的 `src/stm32_monitor/ui_dist/**`；`docs/user-guide.md` 的 Monitor 波形段；`docs/codex/returns/MONITOR-UI-04/implementation.md`。

主代理独占本规范/计划/阶段清单和最终 review.md。controller/API/wire/codec、后端、组编辑、历史/导出、依赖/锁文件、版本、构建/发布配置不在实现范围。超出边界的发现回主代理，不顺带修复 UI05。

## 实施顺序

1. 读取当前 AGENTS、标准测试流程和 UI03 接受断点；确认 accepted base、分支、干净状态与既有工具/依赖身份。只复用可用的锁文件匹配依赖，不下载或安装。
2. 先补会失败的用户行为回归：A 先采、B 后加入；gap 的 0ns 不能拉长轴；图内 zoom 后新数据重绘仍用新范围；连续放大到最小窗口不回到全幅；8 条已满时第九条不再静默无效；切组后可移除不在当前表里的已选项。
3. 按规范将时间投影接入现有 ECharts adapter，保留 bigint 元数据和空点语义；再连通 datazoom → onZoom → reducer → 图表/工具栏，关闭图例独立选择，补中文起点/单位和空状态。
4. 完成已选项区与数量/禁用解释，保留 reducer 防线和既有连接/采样路径。更新指南，按现有流程构建 dist。
5. 固定产品 CodeHead，单独提交实现回报（写 full accepted base 与 CodeHead，不写报告自身 SHA）；主代理在独立干净 review 树审查完整 base→CodeHead 并执行定向复验。发现回原 owner；同一问题两轮未收敛则重审契约。

## 比例验证与证据 owner

| 层次 | Owner / 环境 | 需要证明的行为 |
| --- | --- | --- |
| 投影与模型 | 实现者 / 现有 Windows Node、Vitest | 不同起点/长度按自身时间坐标；晚选曲线；同时间重复点；正负 int64 边界；gap/segment/null 不连成值或 1970 点；无/单点有限域；原数据不变、8×600 边界保留 |
| 图表生命周期 | 实现者 / 可控实例与已有 ECharts SSR | 顶层及 batch zoom、缺失/非法值、相同范围幂等、更新不回环、最新回调、卸载解绑/迟到事件无效；setOption/新点/resize/隐藏恢复不清合法 zoom；连续放大、1%/100% 边界、近边缘窗口、非法值保留原范围；真实 engine 解释相对坐标和缩放，SSR 不等于浏览器手势 |
| 用户操作 | 实现者 / 组件测试 | 0/8、8/8、移除后再加、所选项不在当前表时可移除、中文禁用解释、无数据提示、图例不另藏曲线；工具栏操作与同一范围一致 |
| 受影响回归与生成资产 | 实现者 / 同一最终源码字节 | 定向 `echarts-option`、`catalog-chart`、`live-table-interaction`、`zoom`、`series`、`reducer` 及新增回归；再 typecheck、typecheck:e2e、lint、完整 UI unit、build、verify:dist。共享 chart/app/reducer 的影响触发完整 UI，不触发无关后端/发布矩阵 |
| 独立接受 | 主代理 / 精确 CodeHead 的干净独立树 | 完整 diff、关键图表/选择/生命周期回归、typecheck、verify:dist；逐一核对实现者日志与代码身份，不冒记他人 PASS |
| 真实浏览器/视觉/无障碍、硬件、发布 | 后续主代理/对应集成 release owner | 继续 DEFERRED，见阶段清单；纯代码失败不能因此延期 |

已有 `tests/echarts-option.test.ts` 提供真实 SSR engine，`catalog-chart.test.tsx`、`live-table-interaction.test.tsx`、`zoom.test.ts`、`series.test.ts` 和 `reducer.test.ts` 提供组件/模型缝。当前测试含同起点的 category 轴断言，改为行为验证，不能仅把旧断言文本改成新实现结构。不为颜色/间距写镜像测试。保留命令、退出码、源身份和最小诊断。

## 产物、节奏与完成条件

所有新执行根位于 `D:\codex-tmp\mu41015`，impl/review/run/verify 分工明确；TEMP/TMP/TMPDIR、npm 与适用缓存均绑定短子目录。主代理是清理 owner；每次检查结束后清理不再需要的自有产物，保留源码、fixtures、最终证据与必要失败诊断，不清理其他任务或已被拒绝的历史路径。

按三个用户场景及连通的数据/交互路径记录进度，不使用任务百分比。记录实施、验证、审查/报告时间；若连续两片验证/报告明显超过产品工作且无风险理由，暂停扩展验证并回顾治理。本片只做计划中影响面检查，预计为一个 1–3 工作日以内的有界切片，非交付承诺日期。

完成条件：三条场景具有代码和有意义回归；共享状态/时间契约一致；生成资产一致；全部必需非 deferred 检查通过；独立审查无未闭合发现。浏览器暂缓与本地验收结论并列记录；产品提交不代表发布。

## 规划审查记录

本轮两个只读代码审计与主代理源码复核形成剩余事项清单；独立 `gpt-6-sol/max` 审查者随后审阅三份规划文档及接受基线对应源码。主代理补充连续放大到相等端点会回到全幅的既有路径，并在 S2 冻结最小窗口和确定的事件字段优先级；独立审查复核无未解决歧义，结论为 **READY_FOR_APPROVAL（规范与计划）**。

这仅表示规划可提交用户审批，不是用户已批准或产品已接受。没有派发实现、修改产品、运行测试/SSR/浏览器或更新 8765。下一阶段所列回归是待实现的验证要求，不是已运行的 PASS。
