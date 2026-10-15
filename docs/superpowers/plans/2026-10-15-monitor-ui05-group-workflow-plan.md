# MONITOR-UI-05 实施计划

Full accepted base：`acf6953221f87b0e7951e5c0db4d9a57a381313e`。规范为同日 `monitor-ui05-group-workflow-design.md`，已独立审查并由主代理审定。一个 gpt-6-sol/max 实现者，一个独立审查者，主代理负责完整差异审查和接受。用户整体授权覆盖规范审定、实现、测试和本地服务更新，停止在任何远端修改前；无 ownership 例外。

1. 独立契约审查通过，从已接受 UI04 完整 SHA 建立 `codex/monitor-ui-05-group-workflow`，工作根 `D:\codex-tmp\mu51015`，实现树 `impl`，独立树 `review`。无 PR。TEMP/TMP/TMPDIR 与日志/缓存限定该根，主代理清理。锁文件一致时复用已安装依赖，不安装。
2. 先补用户行为红回归：同组点击不丢稿、切组取消/确认、新稿无采样旧目标、删除确认后无孤立可写 ID、版本冲突恢复只 GET、旧列表迟到不覆盖 ack、保存后列表失败不重复 POST、不可采样寄存器不能加入。
3. 实现唯一编辑基线和导航状态，打通组件→reducer→controller，保留现有写 family/request 生命周期。补多操作重复点击、切换后旧重试、同 ID 新 revision、dirty refresh、删除源孤立稿直接 Save 被拒绝及另存、同 revision 名称冲突后改名新提交、确认目标消失、打开删除确认后 revision/编辑 generation 改变使旧确认失效等边界；再完成目录/导入中文呈现。不要平行写共享 app/reducer。
4. 实现者先跑相关 group/catalog/controller/recovery/reducer/app 以及新增回归，再执行两个 typecheck、lint、完整 UI unit、build、verify:dist。共享 state/controller 是完整 UI 回归的风险理由，不触发无关后端/发布矩阵。保留命令、退出码、产品源身份与必要红日志，清理不再需要的中间产物。
5. 固定 CodeHead，单独报告 commit 写 accepted base 与 CodeHead（不写报告自身 SHA）。主代理在独立干净树复核完整 base→CodeHead，运行关键 group/controller/recovery 回归、typecheck、verify:dist；只读审查者并行审完整 diff。修订返回原实现者，同一问题两轮不收敛重审契约。

接受条件：四条用户场景连通；脏稿无静默丢失，组状态/写确认不存在竞态覆盖，冲突和未知写结果不自动重发；全部必需非 deferred 检查通过；完整差异独立审查无未闭合发现。浏览器和硬件待验收单列，不改变其 DEFERRED 状态。服务最终在 UI06 和集成验收后统一更新。

2026-10-16 独立预审 R1 补充：在实际 App/Preact 中同事件输入 B 后点击尚未重绘的 Save（提交 A），覆盖 create/update、后续列表失败。ACK 必须落地服务端身份/版本与 canonical baseline，同时保留 B 为 dirty；不同 generation 仍不得改当前稿。状态行为修订后重跑完整 UI、两个 typecheck、lint、build 与 verify:dist。

同轮 R1 覆盖：冲突后直接再次 Save/Delete/Import 不触网；GET失败仍不可写；关闭提示/导航/另存不绕过列表门禁；刷新成功后同revision改名新提交可行；UI禁写但编辑和刷新可用。
