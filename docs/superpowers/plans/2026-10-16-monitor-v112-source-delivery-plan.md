# Monitor v1.1.2 版本同步与授权推送计划

Full accepted base：`b257c7e2ebb757c5228d5176d813e14573c4403e`；规范见同日 monitor-v112-source-delivery-design.md。主代理依据用户明确版本/推送及持续本地授权审定执行，无额外审批停顿。实施者与只读审查者均 gpt-6-sol/max；主代理接受并执行最终 push。分支 `codex/monitor-workbench-local-complete`，无 PR，无 ownership override。

## 所有权与步骤

1. 实现者在既有 clean 隔离树 `D:\codex-tmp\mufin1015\impl` 单独实现。产品白名单：`.claude-plugin/plugin.json`，两包 pyproject，Toolkit `__init__.py`、`generation/managed_files.py`，UI package.json/package-lock.json，bin 的两个 cmd 与 setup-stm32-env.ps1，skills/setup-stm32-env/SKILL.md，tools/release/build_0900_artifacts.py/release_0900_policy.json，schemas/stm32-release.schema.json。只同步产品版本与必要1.0.1旧版白名单，不改变运行行为或依赖图。主代理只写本规范/计划、review/delivery文档，不改产品。

   独立契约审查补充：setup 的 release builder/policy 两个 SHA256 常量随最终 Git blob/archive 字节同步，保留原 trust gate。实施者从最终暂存/提交字节求 hash，主代理独立复算；既有 test_setup_trust_anchors_match_archived_release_files（按源码实际节点名）继续覆盖，archive prefix 改为当前1.1.2，不把 checkout CRLF当归档字节。不新增锚点或放宽校验。
2. 实现者拥有相应当前版本测试适配及旧版1.0.1回归：Toolkit test_plugin_layout/test_setup_runtime/test_generation、release/test_0900_artifacts，Monitor test_package_boundary/test_cli/test_models/test_exports。最终定点搜索发现的 CLI/build/migration/MCP/runtime/service 当前版本断言可适配并运行受影响节点；不得全库盲替。旧版本 fixture 保持历史意图。新增测试须针对一致性/兼容实际风险，优先扩展已有参数化测试，不新建通用validator。
3. 实现者同步 README.md、README_zh-CN.md、CHANGELOG.md、docs/user-guide.md、docs/testing/windows-deployment-and-ide-preflight.md、docs/release-status.md 的当前候选说明和兼容限制。历史报告、旧发布事实保持。生成 ui_dist 仅在正常构建实际变化时跟踪。
4. 实施前已阅读标准测试流程当前断点与 STM32TK-101/execution.md 最新记录；该历史实机/发布授权不延续。本轮输出统一 `D:\codex-tmp\mv11216`，解释器为既有 Python3.12，Node/npm与既有依赖；TEMP/TMP/TMPDIR、pytest basetemp/cache、node/npm缓存明确绑定到短子目录。主代理清理。复制依赖来自既有源，不安装；原始脏工作区与活动服务树不写。

## 比例验证与精确归属

- 实现者运行当前版本及兼容的 Toolkit/Monitor 相关软件节点，至少覆盖 package/runtime/protocol身份、旧1.0.1 Check/Repair检测/事务保护、旧1.0.1 generatedBy/managed manifest、release builder/schema一致性、旧导出版本拒绝与当前导出成功。可先运行这些现有模块再补定点断言；不跑完整硬件/发布矩阵。使用现有测试的隔离 fake bundle/venv，不部署用户运行时。
- UI完整417项基线回归、两项typecheck、lint、build、verify:dist；package-lock三方依赖图逐项相等。UI代码不变时生成资源应保持字节一致，任何差异先解释而非自动接受。
- 实现者固定 CodeHead 后单独提交 `docs/codex/returns/MONITOR-V112/implementation.md`，记录实际命令/完整退出码/源码及证据，不写报告自身SHA、不自批。
- 主代理在 `D:\codex-tmp\mv11216\review` 的干净精确 CodeHead 完整审查 accepted-base→CodeHead，另一只读审查者复核。主代理独立运行版本一致性、关键旧版兼容/导出边界节点、UI typecheck/verify:dist，核对未改依赖图、API/schema与既有功能；报告文字变化不触发重跑。
- 必需代码/测试发现闭合后接受，浏览器、物理、安装发布资格记DEFERRED并由后续主代理/发布owner接续。同一问题两轮不收敛重审设计。

## 推送与清理

主代理接受后再次只读核对 GitHub master/目标分支及认证权限。执行非强制、单一显式 refspec push：本地 `codex/monitor-workbench-local-complete` 到同名远端分支；不推tags或额外分支。远端存在意外更新或非快进时停止覆盖并先核对，禁止force。成功后 ls-remote/API读取确认远端HEAD精确等于本地已审查最终HEAD，报告链接和SHA；不隐式创建PR、合并master或发Release。

随后清理本次归属明确的缓存/依赖副本/临时项目，只保留源、Git、最终日志与必要失败证据、活动服务文件。已被策略拒绝的旧目录不重试。本轮只记新的服务/推送/清理证据，不改旧报告事实。版本切片交付周期与实际检查时长以命令记录为准，不以任务百分比衡量进度。
