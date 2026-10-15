# Monitor 最终本地集成与推送前计划

2026-10-16，主代理依据用户“完成所有本地开发和测试、到推送之前、不再逐项审批”的授权审定。Full accepted base：`a2ccdd2f3bfbecfd2fa1fc52f0313d7016c287c7`（UI06 已接受），产品 `0edb2183c154d366d3f261a90e08d6ed54505e26`。唯一远端输入 master SHA：`3edd82e6b8f2ebd5df88dcafde1e75f722357c3e`，2026-10-16 实施前只读 ls-remote 再核对未变，已 fetch 到隔离 store 的 refs/remotes/preflight/master。无 push、PR、远端 merge/tag/release/删除权限，无 ownership override。

主代理负责集成设计、独立完整差异审查与接受；原 gpt-6-sol/max 实现者负责本片产品/测试及本地 merge，独立只读 gpt-6-sol/max 审查者复核。分支 `codex/monitor-workbench-local-complete`，实现树 `D:\codex-tmp\mufin1015\impl`、审查树同根 review；全部新缓存、证据、临时文件在本根，主代理清理，不触碰原始脏工作区。

## 三条验收场景及非目标

1. UI01–UI06 与 ENTRY01 既有中文工作台、固定入口、就地恢复、图表、组草稿/冲突、历史/采集时效行为保留；远端新增 bootstrap 和导入卸载测试的保护意图也保留。
2. 历史错误提示说明本地实际检查的 UTC 边界；导出继续使用通用解析/先后顺序提示，保留已接受的导出校验、授权和提交行为。
3. 合并候选完整自动化检查和独立审查通过后，从精确已接受源码更新本机 8765，保留同一展示 project/data/session，记录 OS 监听和无 token 短地址；所有本地提交与证据可供后续推送审阅。

不扩充 UI/API/后端/依赖/版本/构建配置，不启动浏览器，不排查权限，不开展物理硬件或整套发布矩阵，不推送或操作远端。

## 合并与呈现合同

- 本地 merge 上述远端精确 SHA。远端相对 v1.0.1 peeled release `0f06c659f5e04aa1f8e53022eae9b5e964da2b4b` 仅 9 文件：7 份发布/验证文档、bootstrap.test.ts、groups-panel.test.tsx，没有产品源码变化。若输入不符，先返回主代理重定范围。
- 禁止以 ours/theirs 整文件丢弃测试。远端 bootstrap 拒绝测试应适配中文固定文案，仍断言 token/message/details 不泄露、hash 清除；导入卸载测试应保持读取完成前卸载后无回调、无 detached input 写入。UI-POLISH 在读取开始清空 input.value 支持同文件重选，因此后者比较捕获的卸载前状态而非要求保留原 files。保留既有 groups-import-lifecycle 回归。
- 仅补充两处手写呈现改动：zh.ts 将通用 invalidRange 恢复通用解析/先后顺序语义，新增 historyInvalidRange 承载 UI06 的 1970/int64 提示；HistoryPanel 采用后者。ExportPanel 逻辑、共享转换 helper 和后端不变。相应定向断言按实际受影响范围维护，生成资产正常构建。所有状态、错误和生命周期仍由各已接受切片冻结合同拥有，不另建状态源。

## 验证与接受

1. 实现者合并/修正后执行完整 UI unit、typecheck、typecheck:e2e、lint、build、verify:dist，固定产品 CodeHead 后另交 implementation.md，不自批。既有 lockfile 匹配依赖复制使用，不安装。锁文件 SHA256 B7830444281738261024EDB3A601FEB51D2A3603D28E1F02C47CD8067DD94448 不变。
2. 主代理在干净精确 CodeHead 审查 base→候选完整差异，复核远端 master→最终候选每项产品变化对应已接受切片；另一只读审查者独立复核。生成资源以 manifest/index 与独立重建逐字节核验。
3. 主代理定向复验 bootstrap、groups-panel、groups-import-lifecycle、UI06 历史/时效、history/export/presentation、typecheck、verify:dist。只有合并引入非 UI 产品差异才扩大受影响检查。固定入口 Python 字节未变，沿用 ENTRY01 已接受测试，不冒充本轮重跑。
4. 全部必需非 deferred 检查通过后接受。正确可修问题回原实现者，同问题两轮不收敛回到集成设计。失败按项目分类并保留最小有用证据，不把环境、报告或旧断言适配伪装为产品回归。

## 服务与交付

接受后由主代理停止已知 UI03 受管服务 session1069/PID29524，验证原 PID 退出、8765 释放，使用公共 serve 命令和过滤启动输出的 runner 从最终精确产品树启动，同一 project/data/session，不手删锁或运行记录，不打印/持久化 token。记录 source/head、PID/start、127.0.0.1:8765 监听；监听不等于 HTTP/WS/浏览器验证。活动服务源码不得被清理。

主代理清理本片及 UI06 自有缓存/复制依赖/临时构建，保留 Git、源、已跟踪 dist、最终与最小失败日志、活动服务所需文件；原始脏工作区保持。汇总本地 branch/head、已接受切片、命令与外部暂缓项。真实浏览器/视口/手势/axe/关闭后短地址重开、浏览器拦截、物理硬件和发布层继续 DEFERRED，后续 owner 为主代理及对应硬件/发布 owner。停止在任何 GitHub 修改之前。
