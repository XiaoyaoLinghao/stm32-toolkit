# Monitor 中文工作台收尾：独立验收

日期：2026-10-15。裁决：**ACCEPTED（本地代码）**。中文默认、浅色工作台继续采用已接受 UI01 实现，本轮三个交互场景闭合；浏览器视觉及真实短地址重开依用户指示保持 PENDING。本结论不表示发布验收。

- Accepted base：`4a90d7385db0b42bc2d103ba90ab41a2f89f7d05`。
- 最终产品 CodeHead：`2af7f3c2f750669b5176503f61d3f14dd11cf8d3`。
- 实现回报提交：`60761ca819bfaa4e7554b5842eae9ed7e48742b0`；相对于 CodeHead 仅增加 implementation.md，主代理已完整读取。
- 分支：`codex/monitor-ui-01-polish`，PR 无。规范、计划、集成、完整差异审查、接受及 cleanup owner 为主对话代理；单一实现 owner 和独立辅助 reviewer 均为 `gpt-6-sol/max`，实现者未自行验收。
- 独立复验源：`D:\codex-tmp\muf1015\review`，精确 CodeHead，验证前后 clean。原始脏工作目录以及 ENTRY01 树内既有未提交报告均保留，无远端或硬件操作。

## 已关闭问题

1. 文件读取失败发生在原 try 之外，旧预览仍可确认。读取现在属于同一局部状态生命周期，新选择立即撤销旧预览，失败显示中文说明且不提交。
2. 多次文件选择乱序完成导致旧文件覆盖最后选择。现在结果必须属于当前读取代次；取消、关闭和卸载使旧结果失效，同文件可重新选择。组件测试核对实际 onImport 文档，而非只核对内部计数。
3. 曲线按钮的“显示/隐藏”含义不明确。现在按钮明确说明下一步“显示曲线/隐藏曲线”，曲线选择仍由原 reducer 提供。
4. 独立审查第一轮发现同步确认防线不足：更新界面前的旧确认处理器只依赖旧 render 闭包。原实现者在同一分支补充预览代次绑定和同步确认校验；同批次选择/取消/关闭后触发旧确认的三个回归先红后绿。第二轮复核闭合，无新增产品阻塞。

主代理已逐项阅读 accepted-base→bc01 的完整计划、源码、测试、e2e 定位及生成资产引用差异，并完整复核 bc01→最终 CodeHead 修订。独立 reviewer 审查相同完整范围。资产通过独立重建逐字节核对；API/controller/reducer/group-transfer/Python/锁文件/构建配置未改变。

## 验证证据

| Owner / 精确提交 | 运行结果 | 证据 |
| --- | --- | --- |
| 实现者 / 最终 CodeHead | 双类型检查、lint、完整 UI 36 文件/304 测试、build、verify:dist 全部 exit 0 | `run/revision-final-*.txt` 与 implementation.md 的命令表 |
| 主代理 / 最终 CodeHead | 5 文件/51 项交互回归 PASS，包含两份新增测试及既有相关组件回归 | `verify-final/interaction-tests.log` |
| 主代理 / 最终 CodeHead | typecheck PASS；verify:dist 7 文件逐字节一致；完整 diff --check PASS；源树 clean | `verify-final/results.json`、typecheck.log、verify-dist.log |
| 辅助 reviewer / 最终 CodeHead | 完整源码/测试/生成映射审查无未闭合阻塞 | 本报告记录其只读审查归属；未将主代理测试归给 reviewer |

以上相对证据路径均位于 `D:\codex-tmp\muf1015`。主代理复验入口为同目录 `verify-review.ps1`，记录完整命令、工作目录、退出码、源提交及统一临时根。初始候选的 301 项实现者 PASS 和 48 项主代理 PASS 保留原归属，不代替最终修订证据。jsdom navigation 提示与既有 chunk 大小建议没有造成失败，也不代表真实浏览器证据。实现报告中的提交前测试 lint 缺陷归入 PRODUCT（测试代码），已修复。

既有后端证据因本次未改变其产品字节继续适用；没有重跑全产品发布矩阵。实现与审查并行进行，未采集可准确拆分的产品/验证/报告工时比例，不虚构比例或任务百分比。

## 运行服务与剩余边界

主代理向原执行会话 95843 发送 Ctrl-C 后，该会话 exit 1；确认旧 PID 25184 已退出、8765 端口释放，但运行记录仍存在，因此不声称完成了 Python finally 的正常清理。没有手删锁或运行记录。随后使用现有 `serve --serve-ui --json` 和相同 project/data/session 启动最终 CodeHead，现有启动流程成功取得锁并启动服务。

新执行会话 `86335`，Python PID `19304`，操作系统确认仅监听 `127.0.0.1:8765`；启动输出只保留短地址，未输出或保存 accessUrl/token。代码源为上述最终 clean review 树。证据 `service.json`。服务继续运行；没有启动浏览器或修改权限策略。

浏览器截图、axe、真实关闭重开和首次浏览器认证交付仍未验证；后续 owner 为主对话代理，在用户恢复该验证时继续。普通请求失败的整页 blockingError 行为仍属于规范明确单列的 UI02，需要冻结并批准其错误分类/清除/重试合同。本轮不把它写成已修复。发布版本 v1.0.1 未修改、未发布新版本。

## 清理结果

本轮自有依赖副本和缓存的原生 PowerShell 清理命令在执行前被自动审批拒绝，唯一原因文本为 `blocked by policy`；未重试或改用其他方式。以下八处仍保留，详见 `D:\codex-tmp\muf1015\cleanup.json`：

- `D:\codex-tmp\muf1015\impl\tools\stm32-monitor\ui\node_modules`
- `D:\codex-tmp\muf1015\review\tools\stm32-monitor\ui\node_modules`
- `D:\codex-tmp\muf1015\run\temp`
- `D:\codex-tmp\muf1015\run\npm-cache`
- `D:\codex-tmp\muf1015\run\vitest-cache`
- `D:\codex-tmp\muf1015\run\vitest-cache-revision`
- `D:\codex-tmp\muf1015\verify\npm-cache`
- `D:\codex-tmp\muf1015\verify-final\npm-cache`

源、已提交构建资产、最小失败与成功证据保留；`service-temp` 为仍运行服务使用而保留。本次没有处理以前被拒绝清理的其他运行根，也没有删除共享依赖或用户数据。
