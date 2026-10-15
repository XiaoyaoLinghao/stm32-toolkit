# Monitor 中文工作台收尾计划

日期：2026-10-15。本计划落实用户本轮“继续完成 Monitor 的界面优化和剩余修复，按之前批准的中文默认、浅色专业工作台方案推进，浏览器拦截暂时不管”的授权，属于已批准 MONITOR-UI-01 的 S2 交互收尾，不扩展 UI-02 错误恢复状态机。

## 责任、基线与范围

- Governing specification：`docs/superpowers/specs/2026-10-12-monitor-ui-design.md`；固定入口保留 `2026-10-15-monitor-fixed-entry-design.md` 已接受行为。
- Full accepted base：`4a90d7385db0b42bc2d103ba90ab41a2f89f7d05`；其中产品字节与已接受 `0bbca0538489def23675a93b9834d6c2812bf7b5` 相同，之后均为文档提交。
- 规范、计划、集成及验收 owner：主对话代理；实现 owner：一个有界 `gpt-6-sol/max` 子代理；独立完整差异审查：主代理，另有只读 reviewer 协助。
- 分支：`codex/monitor-ui-01-polish`；实现树 `D:\codex-tmp\muf1015\impl`；PR 无，未授权任何远端操作。不存在主代理产品实现例外。
- 原始 master 工作目录的 tracked/untracked 旧改动不动；ENTRY01 分支唯一未提交的 browser-verification.md 记录保留在原树；当前运行服务源 men1015/review 不改动。以上分支均为本地候选，未推送或发布。
- 运行根 `D:\codex-tmp\muf1015`；主代理为 cleanup owner。源、有效证据、共享依赖不删，测试临时输出在完成后按归属清理。

## 三个用户场景与冻结行为

1. 实时数值表：显示中的曲线按钮明确表示下一步“隐藏曲线”，隐藏中的曲线表示“显示曲线”。按钮调用相同 series toggle，选中状态仍由已有 reducer 提供；不新建图表状态、订阅或采样实例。
2. 导入观测组：选择新文件即废弃旧可确认预览；读取期间显示中文状态，不能确认旧文件。读取失败、JSON 无效或 schema 无效均给出现有中文错误；不触发 onImport，不残留旧预览。成功预览仅由用户确认后通过既有 onImport 提交。
3. 连续选择与关闭：最后一次有效文件选择拥有读取结果；较旧读取无论成功或失败都不能覆盖当前预览/错误。关闭、取消或卸载使在途读取失效；重新打开不恢复已废弃预览，也不能被旧回调重新打开。文件框应能重新选择同一文件；旧读取的 finally 不得清空新一轮文件输入。请求生命周期只存在于 GroupPanel 展示状态，不进入公共模型或后端。

状态所有权：已有 reducer 继续拥有组/草稿/采样/曲线选择；GroupPanel 独占导入 UI 的 idle、reading、preview/error 生命周期及读取代次；presentation/zh.ts 是新增中文文案的唯一来源。依赖仍为组件→现有解析器/回调，无 API、协议或持久化改变。一个实现者拥有这些连通修复，不并行拆分写入。

非目标：不改变普通 API 失败的 blockingError 契约；不做 UI-02、token/cookie/端口改造、浏览器策略排查、浏览器替代访问、硬件、安装、发布或依赖升级。中文浅色工作台布局继续使用已接受实现。

## 实现所有权

允许修改：`ui/src/components/GroupPanel.tsx`、`LiveTable.tsx`、`ui/src/presentation/zh.ts`，对应 `ui/tests/**` 和仅因标签改变受影响的 `ui/e2e/**`，以及通过现有构建生成的 `src/stm32_monitor/ui_dist/**`。路径均相对于 `tools/stm32-monitor/`。实现回报写 `docs/codex/returns/MONITOR-UI-POLISH/implementation.md`。

不改 app/controller/reducer/API/codec/group-transfer/Python/依赖锁/构建配置。新发现超出范围的问题先返回主代理，不自行扩展。实现代理不是唯一参与者，保留他人改动，不递归委派，不自行验收。

## 验证与接受

实现者先用可控 FileReader 的组件回归证明：旧预览后读取失败、两次选择乱序成功、旧失败晚到、关闭/取消及卸载后的回调无效、同文件重选与新读取中的确认保护。不要只验证内部计数或 CSS；断言可见中文、可确认的内容和实际提交参数。曲线测试覆盖同一用户在显示/隐藏两方向的动作与当前选择状态。

Windows 现有 Node/npm 与匹配 lockfile 的本地依赖副本；不得下载或安装。TEMP/TMP/TMPDIR、缓存及日志绑定本轮短根。按标准测试流程读取现有接受断点，复用与本次无关的后端 PASS。

实现者运行相关组件测试、`npm run typecheck`、`npm run typecheck:e2e`、`npm run lint`、完整 UI unit、`npm run build` 和 `npm run verify:dist`。因改动限于 UI，75 项已有后端证据仍适用，不重跑发布或硬件矩阵。保留命令、退出码、stdout 与提交绑定。

主代理在最终 CodeHead 的独立干净树审查完整 accepted-base→CodeHead 差异，执行风险相关组件测试及资产一致性检查；实现者不得自批。纯代码失败必须修复；同一问题两轮不收敛则回到设计。

用户已明确搁置浏览器拦截，本轮不执行浏览器/截图/axe/真实关闭重开。该部分保持 PENDING，后续 owner 为主对话代理在用户恢复该验证时执行；本轮 local code acceptance 不等于视觉或发布验收。

采用 EL-007/008：统一临时根、PASS 绑定真实执行证据；GL-004/005：按影响面验证，区分环境与产品错误。当前未发现需扩大验证范围的风险。
