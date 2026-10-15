# MONITOR-UI-02 实施计划

日期：2026-10-15。依据同日 `monitor-ui02-local-recovery-design.md` 冻结本轮已明确授权的 UI02 行为。Full accepted base：`fc9cdbafe696fa3dd95539259b11b8c000de7f2b`。本地分支 `codex/monitor-ui-02-local-recovery`，没有任何远端操作授权。

## 单一纵向切片和所有权

一个 `gpt-6-sol/max` 实现者拥有从请求到就地恢复的完整路径，不递归委派，不自行验收。允许修改 `tools/stm32-monitor/ui/src/` 中 controller、state、App、受影响组件、presentation、样式及相应 tests/e2e；允许新增有界 UI 错误策略/提示组件；只通过现有构建生成 `tools/stm32-monitor/src/stm32_monitor/ui_dist/`。实现回报为 `docs/codex/returns/MONITOR-UI-02/implementation.md`。

不得改 api/contract、api/codec、bootstrap、安全入口、Python、package/lock、构建工具/CI 或新增自动化。若需突破范围先返回主代理解决契约，不自行扩大。主代理只写规范/计划/审查文档并做集成验收。其他参与者的文件和旧树保持不动。

1. 执行前读当前 AGENTS、standard-test-procedure 的接受断点及最近 UI polish review。冻结 scope/id/error/retry 生命周期，先用行为测试覆盖现有可复现失败。
2. 实现请求代次保护、完整读取、mutation 与 follow-up GET 分离及不可变重试输入；连通工作台提示、确认/关闭、初始化重试，并接入目录、历史、导出状态。
3. 保留已批准中文浅色工作台与 UI01 的草稿/导入/导出范围行为；补充受影响单元与组件测试，生成并核对 dist。
4. 提交 CodeHead，再单独提交实现回报（记录 base、CodeHead、命令和退出码，不写回报自己的 commit）。主代理在干净独立 review 树审查完整 base→CodeHead，并安排独立只读审查；问题回同一实现者。两轮同一问题不收敛则重审设计。

## 验证矩阵和证据归属

实现 owner 在 Windows、现有 Node 24/npm 11 与 lock 匹配的已有依赖副本运行：相关测试、typecheck、typecheck:e2e、lint、完整 UI 单元、build、verify:dist。不安装依赖，不运行浏览器、网络页面读取或硬件。

必须以用户可见结果/API 调用证据验证：

- 普通失败不卸载工作台，保留 tab、图表、草稿；多个失败都可见；关闭只清当前记录；认证精确分类仍阻断。
- 所有 scope 生命周期完整；初始化错误可重试且只成功后开启一次 live；close/旧成功/旧失败无效；重复点击/确认不重复写入。
- 读取重试保留原参数；目录第二页和历史前进/后退失败可恢复；完整 groups 分页失败不截断列表；刷新不丢编辑。
- 明确写入失败经确认重试原内容，取消无请求；不确定写入只核对；写入成功后读取失败只重试 GET；导入输入可恢复。
- 导出创建/轮询/下载错误均可见且释放忙碌；重试使用原格式/范围/ID；创建成功后的任务范围不受当前表单改变影响。
- 第一轮审查的追加回归：过期上下文失败和重试被撤销；延迟组件提交不重复追加目录页；探针/采样目标切换后旧确认不产生 POST；初始化一项失败/另一项悬挂时立即可重试，迟到致命错误只作用于同一最新尝试；创建成功但完整列表刷新失败时选中 ID 仍能解析到权威回执。
- 第二轮审查重新明确会话致命状态与普通 pending 的所有权：按规范的独立 `access.blocked` 契约修正统一入口，覆盖目录及导出旧上下文的迟到致命响应。因修改共享权限阻断入口，实现者复跑完整 UI 单元、两个 typecheck、lint、build 与 dist 核对；主代理复跑关键恢复集及类型/产物核对。不得再以各 scope 特例弥补状态分裂。

主代理拥有集成与独立验收证据：在最终 CodeHead 的独立干净树检查完整差异、针对错误恢复/竞态的 UI 测试、typecheck 和 verify:dist。已无关的后端/发布/硬件证据沿用，不重跑 release matrix。浏览器证据 DEFERRED，后续 owner 为主代理，待用户恢复浏览器验证时执行。

## 环境、运行产物和服务

任务根 `D:\codex-tmp\mu21015`，实现树 `/impl`，独立审查树 `/review`，实现运行 `/run`，复核运行 `/verify`，所有 TEMP/TMP/TMPDIR/npm/vitest 缓存均限定本轮短根。只复制上一接受树的匹配 node_modules 到新树自有目录，不改共享副本；不下载。主代理为 cleanup owner，保留源码与必要证据；测试通过后清理确切自有可丢弃目录，失败保留最小诊断。此前任务被策略拒绝的清理不重试。

接受后通过公共 `stm32_monitor serve --serve-ui --json` 从新 review 树恢复 127.0.0.1:8765。只验证进程、监听和不含凭据的启动摘要；不获取页面。不得打印或落盘 token/accessUrl。先停止本轮已知旧服务并验证释放，再启动；不杀其他进程，不手工删除锁/运行记录。服务运行根保留。

采用已检索 EL-007/008 和 GL-001/004/005：统一临时根、按影响面验证、请求/生命周期先冻结、证据绑定真实代码与 owner。分类当前问题为 PRODUCT；浏览器策略仍是单独暂缓事项。

## 已接受行为的用户指南补齐

2026-10-15 用户要求“还有哪些工作没完成？继续推进”。主代理核对发现 `docs/user-guide.md` 的 Monitor 段落仍声称普通错误整页阻断，与已接受 UI02 不符。以 `62d33f15503dbaaa230670d8dc1d0750badcdfc0` 为本次文档修订基线，同一实现 owner 仅更新该指南的 Monitor 段落：就地提示/关闭与重试、原输入确认、结果未知时只读取核对、真正认证失效的处理，保留未发布候选及固定入口会话条件。不得更改产品、版本或声称浏览器实测通过。主代理独立核对完整文档差异与已接受代码；纯文档修订不重跑 UI 测试。保持同一 UI02 分支，无远端操作授权。
