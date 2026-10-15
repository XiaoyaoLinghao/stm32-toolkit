# Monitor 中文工作台实施计划（已批准）

2026-10-15 用户明确授权“可以开始实施”。本计划开始执行；第一切片认证和监听行为仍按规范保持既有契约。

切片：MONITOR-UI-01。对应规范：`2026-10-12-monitor-ui-design.md`。
Accepted base：`0f06c659f5e04aa1f8e53022eae9b5e964da2b4b`（v1.0.1）。

## 批准前已完成

- 发布标签和 Release 冻结源核对；脏工作区与发布基线分离。
- 发布版前端结构、样式、语言、状态与历史时间展示审查。
- 4 个用户场景、非目标、状态所有权、中文与错误语义、响应式验收规范。
- 可交互设计预览，使用示例数据，不连接硬件/后端。

本轮设计检查：独立 `gpt-6-sol/max` 只读审查提出的导出范围、notice 中文化和 S4 证据归属三项歧义均已修订并复核闭合。预览脚本经 Node 语法解析通过；内置浏览器因 webview attach 超时及 request-header policy 加载失败未能进入页面，因此没有浏览器渲染/交互 PASS，也没有产品或硬件测试结果。预览检查服务已停止；设计预览保留供对话展示。

## 启动条件与隔离

依据项目 AGENTS.md Delivery workflow 第 2 条，在用户批准规范和计划后才能派发实现代理。视觉方向的偏好回复不单独视为批准实现。

主代理在 `D:\codex-tmp` 下准备全新独立 Git 存储和 worktree，起点为上述完整 SHA；每次 implementation review 使用同一 accepted base 的干净隔离树。当前 `D:\workspace\stm32-toolkit` 有旧改动，始终保留。

计划分支：`codex/monitor-ui-01-zh-workbench`。没有本切片 PR。无 push、PR mutation、merge、tag、release、close 或远端删除权限。当前目录写权限受限；不能因此把所有实现塞入脏工作区，也不能自动申请/宣称更高权限。

v1.0.1 后的两份 UI 测试补充是后续集成时需要比较的内容，不把它们默认为发布包来源；如需更换实现基线，由主代理记录新的精确 SHA 和原因并修订计划。

## 单一实现责任

实现模型：`gpt-6-sol`，reasoning effort `max`，一个有界实现子代理，不递归委派。主代理负责设计决策与完整差异审查，不直接写产品代码。

实现代理不是代码库唯一参与者，必须保留其他人的改动，不能回滚他人文件。以下 ownership 在隔离树中生效：

| 文件范围 | 允许变更 |
|---|---|
| `tools/stm32-monitor/ui/index.html` | zh-CN 与标题 |
| `tools/stm32-monitor/ui/src/bootstrap.ts` | 仅启动/认证失败的展示文案；保留 token/路径/认证行为 |
| `tools/stm32-monitor/ui/src/app.tsx`、`styles.css`、`components/**` | 工作台组合、交互、样式、中文、可访问性 |
| `tools/stm32-monitor/ui/src/presentation/**`（新目录） | typed 中文字典、错误和数值展示函数 |
| `tools/stm32-monitor/ui/src/chart/echarts.ts` | 主题/标签等展示选项，保留数据/缩放语义 |
| `tools/stm32-monitor/ui/tests/**`、`e2e/**` | 适配中文并增加必要契约/用户路径回归 |
| `tools/stm32-monitor/src/stm32_monitor/ui_dist/**` | 仅通过既有构建流程生成 |
| `docs/user-guide.md`（Monitor 段落）、`docs/codex/returns/MONITOR-UI-01/implementation.md` | 更新用户操作及受范围限制的实现回报 |

API/types/codec、reducer/controller 的协议和行为、Python、lockfile、版本、CI/工具配置不在可写范围。若确有 presenter 之外的用户文案或布局状态必须迁移，先把具体文件和行为交给主代理修订所有权；不得自行改协议、状态机或引入第二个 state store。

## 实施顺序（同一切片）

1. **确认基线与映射**：记录 clean status/full SHA，列出所有现有 UI 能力到新入口的映射，核对中文文案来源，明确图表/组表单的保活策略。
2. **中文和展示层**：集中常量、状态/错误翻译、中文 aria、UTC 标签和精确数值格式；保留原始机器字段。先验证未知状态/错误和 bigint 边界。
3. **实时工作台**：项目/设备顶栏、观测侧栏、主要采样动作、图表与数值表；复用 controller；加入布局 resize 与无数据/断流状态。
4. **历史/导出与详情**：按需显示，保持查询范围/游标/导出绑定和草稿；补充日期错误提示、异常详情、键盘焦点逻辑。
5. **验证与构建**：按下面矩阵执行；生成并核对 ui_dist；检查所有旧功能入口可达。
6. **返回和审查**：实现报告记录 accepted base、CodeHead、命令与结果、残留问题、临时产物清理；报告不能引用自己的最终提交 SHA。最终 head 在返回消息提供。主代理审查 accepted-base 到 final-head 的完整 diff，给出单一 verdict。

同一问题两轮不收敛时停止补丁循环，由主代理重审交互/接口，不扩展成层层子任务。

## 验证计划

所有 PASS 必须由指定 owner 在返回代码提交和具体环境实跑；本计划不是测试结果。

| 层次 | Owner / 环境 | 要求 |
|---|---|---|
| 静态与单元 | 实现代理 / Windows、既有 pinned Node/npm 工具链 | 在 ui 目录执行 `npm run typecheck`、`npm run typecheck:e2e`、`npm run lint`、`npm test`；中文词条、未知错误、精确时间/数值和布局状态保留使用有意义断言 |
| 无障碍 | 实现代理 / 既有 Playwright + 浏览器 | `npm run test:e2e:windows -- e2e/accessibility.spec.ts`；人工键盘检查面板/对话框焦点、中文名称、200% 缩放。现有 `test:a11y` 单元文件仅为 scaffold，不能拿它代表浏览器 a11y 通过 |
| 用户路径 | 实现代理 / Windows、既有 Playwright 浏览器与 Python fake_runtime fixture | 以 `npm run test:e2e:windows -- e2e/workflow.spec.ts` 为基础覆盖 S1–S3 及 S4 的已有错误呈现，并只补缺失交互；确认请求序列不变、页切换不重复订阅、UTC 语义以及规范规定的导出范围预填/手工编辑行为。默认 1280×720 / 1024×768，新增尺寸采用运行配置，不默认改共享配置 |
| S4 异常状态 | 实现代理 / 组件与 reducer fixture | 既有 fake_runtime 不产生自发断连、身份变化或 PAUSED_BLOCKED；这三种转换用现有结构的 typed fixture + reducer/组件测试验证中文、旧值失效、控件状态和阻断呈现。浏览器可用拦截响应/断流的受控 fixture 验证对应画面，明确标注“模拟响应”。不以正常 workflow.spec 的 PASS 代表这些状态已实机或原 fake-runtime 通过 |
| 视觉与尺寸 | 实现代理 / 实际浏览器 | 1440×900、1366×768、1024px、768px、320px；实时/历史、空/加载/错误/暂停/受阻；检查图表尺寸与文字不重叠 |
| 生成资产 | 实现代理 / 同一隔离树 | `npm run build`、`npm run verify:dist`；检查生成目录完整差异，无手改 bundle |
| 独立 acceptance | 主代理 / clean review worktree、同一 CodeHead | 完整 diff + 风险相关类型/构建与代表性用户路径复核；不可把实现者结果写成主代理独立运行 |
| 包装与发布 | 后续 release owner / 最终候选包 | wheel/ZIP 嵌入 UI、全量 release 门槛、覆盖率门槛等留在 release；本切片不继承 v1.0.1 一次性覆盖率例外 |
| 物理硬件 | 后续硬件/集成 owner / 用户指定板卡与探针 | 真实连板/实际采样率按目标证据另行验证；本轮 fixture/预览不声称物理 PASS |

新增 UI 周期风险只触发已有相应性能检查；不默认重跑全产品 release coverage。若已有必要依赖/浏览器不可用，明确分类 ENVIRONMENT 并记录未验项；不偷偷安装工具，也不把纯代码失败 DEFERRED。

## 运行产物与清理

主代理是本切片 cleanup owner。所有运行根登记在 `D:\codex-tmp` 内，使用短子目录。子进程 TEMP/TMP/TMPDIR、npm cache（若使用）、Playwright 输出、Vite 缓存和 coverage 均绑定本次根。

每次运行保留最小可定位结果/必要失败证据，完成验证后只删除归属清楚的临时输出。设计规范、预览、有效源码、复用 fixtures、用户已有脏状态和共享缓存不删除。不得恢复已经废弃的旧 worktree 路径。

## 接受与退出条件

第一切片保留既有 blockingError 全页阻断行为，仅中文化与改善诊断可读性；一般请求失败的局部恢复纳入后续 MONITOR-UI-02，另行冻结错误分类与重试/清除契约。不得在 UI-01 报告中把这一既知问题写成已解决。

- 4 条用户路径闭合，中文默认与主要视觉缺陷解决。
- 现有功能无隐性移除、数据与连接行为无回归，生成资产一致。
- 所有必需非 deferred 检查通过，独立 complete-diff review 无未闭合产品阻塞。
- 明确列出实际浏览器验证、模拟验证与后续物理验证的边界。
- 提交在本地不等于发布；后续每类远端动作独立授权。
