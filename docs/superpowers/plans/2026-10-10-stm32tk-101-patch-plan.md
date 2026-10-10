# STM32 Toolkit v1.0.1 实施与交付计划

状态：APPROVED / 用户于 2026-10-10 要求开始实施，并新增 master 历史内容清理。

依据：[补丁规格](../specs/2026-10-10-stm32tk-101-patch-design.md)。
完整 accepted base：`694c825d29a55a53052a148efa4cc6720c315a04`。
本计划现可派发实现；具体进展以本轮执行记录为准。远端尚未改变。

## 1. 责任与执行次序

主代理负责规格、集成、所有公共 schema/类型/lockfile 决策、完整差异审查和最终验收。
每切片一个 `gpt-6-sol / max` 实现者，禁止自我批准或递归委派。实现和独立审查分离。
所有产品写入、实现测试和用户技能改动由实现者完成；主代理只写规格/计划/验收文档。
产品写入按 A、B、C、D 顺序集成与验收。已核实 A 与 B 无产品文件交叉，故 B 可在独立工作树提前并行实现；
B 不修改 A 的 context/CLI/MCP/workflows/migration 文件及 test_context.py，跨路径验证放入其自有生成器测试。
C、D 待前序集成后实施，避免公共返回及版本资源争用。
新增 E 为用户已授权的历史清理与用户指南，可在独立工作树与 A 并行；先冻结下面清单和替代文档，
E 不修改产品运行代码、版本资源、技能或 A/B/C 所有文件，D 在 E 集成后只核对版本与最终行为一致性。
各切片的具体实施分支从上一个被主代理接受的 full SHA 创建，派发前把该 SHA 写入切片开工记录，不能使用浮动 HEAD。
如某切片超出一至三个工作日，先缩减/重设计边界，不递归拆成文件任务。

| 切片 | 完成后可用的行为 | 唯一写入责任范围 |
| --- | --- | --- |
| A / 项目诊断与入口 | 子目录 Keil 可发现；doctor 不启动 GUI；迁移拒绝准确可操作 | Toolkit detection/context/doctor/tool_support、keil 发现/基线和 migration 诊断；对应测试；migrate/build 技能 |
| B / 配置与构建 | 保留未托管编辑器文件并构建；栈符号与 NOBITS 统计正确 | generation/configure/managed_files、build/map_file/identity、两个模板副本；对应测试；configure 技能 |
| C / 观测与 Monitor 可用性 | 具体 SVD/绑定/目标失败原因；flash 运行状态不误导；UI 有安全恢复提示 | debug/svd/firmware、probe flash/handoff/pyocd 诊断、hardware_workflows；Monitor UI/bootstrap 及 launcher 提示；受影响测试；flash/monitor 技能 |
| D / 统一版本与交付 | 1.0.0 可受控升级到统一 1.0.1 | 元数据、setup/launcher、release builder/policy、UI lockfile、generation producer 兼容、最终文档版本核对及受影响测试 |
| E / 当前仓库入口 | README 与故障指引完整，过期资料退出当前树 | 下列冻结历史路径、双语 README、CHANGELOG、docs/user-guide.md、保留路径的 Windows preflight 文档；删除旧工具专属测试/fixtures |

实现者只修改本切片具名职责相关文件；新文件/公共字段/跨责任区改动先返回主代理决定。
共享文件的后续修改必须基于已接受前一切片，不覆盖其他人的更改。不得把原脏工作区的改动顺带纳入。

## 2. 切片 A：项目诊断与入口

1. 复用同一个根内递归 `.uvprojx` 候选发现函数，落实规格中的排除、确定性、歧义和 reparse 边界。
2. context/detection、inspect、convert 的零/单/多候选结论一致；显式参数不丢失，plan/apply 重检。
3. doctor GUI 工具静态探测，unknown 如实保留；说明 Probe registry 与 hardware 未探测含义。
4. 迁移阻断中补 UTF-8、startup、tracked/untracked、已有 manifest 的说明和相对路径；保留 blocker。
   baseline 只证明历史产物存在可解析，不能认证本次构建。
5. 技能完整展示同一 uvprojx/targetName 的 inspect → plan → apply。输出不含私有工程或探针标识。

验收：以普通磁盘 fixture 从公开 Python/CLI/MCP 路径验证 nested/single/multi/explicit/ignored/reparse；
GUI 分支证明 process runner 从未收到 CubeMX/VS Code 启动请求；失败不产生写入。
重点既有测试：`test_context.py`、`test_detection.py`、`test_keil_inspect.py`、`test_keil_baseline.py`、
`test_migration_plan.py`、`test_migration_apply.py`、`test_doctor.py` 及受影响 CLI/MCP 用例。

## 3. 切片 B：配置与构建

1. 将 `preserved-unowned` 加入固定编辑器目标计划，排除 write destinations/managed records；
   保留已有 ownership 及 drift 保护，保证 fresh replan 和失败回滚不碰 preserved 文件。
2. 验证混合场景：部分 editor 已托管、部分未托管、部分不存在；配置后 context/build 的托管校验有效。
   必要 CMake collision、编辑器目录/链接、类型改变、旧计划/用户已改托管文件继续拒绝。
3. 修复两处 linker 模板栈符号高低；保留默认容量和 native linker 原样。
4. ELF evidence 传递 NOBITS 属性；VMA/LMA 分开统计，保留区间并集、重复/重叠处理及范围拒绝。
5. 更新 configure 技能及内存含义说明；明确 CubeMX regeneration 对未知路径仍有独立限制。

验收：真实临时文件及其前后 hash/类型证明 editor 保留；实际 configure → managed manifest → build/context 路径通过。
使用可定位的 ELF+MAP fixture 覆盖 `.data` 双驻地、`.bss`/NOLOAD 显式 LMA、段间空隙、段内保留、重叠和 overflow；
不能以重写期望值代替 oracle。模板需实际链接或 ELF 符号证据证明 StackLimit < StackTop 与保留区一致。
重点测试：`test_generation.py`、`test_build_map.py`、`test_build_runner.py`、`test_firmware_identity.py`、`test_context.py`。
未取得原报告 ELF/MAP 则不声称复现其精确数字；新增合成 fixture 只证明已命名规则。

## 4. 切片 C：调试与 Monitor

1. SVD 错误提供实际首个越界寄存器/地址/宽度/可信范围；保留全文件选择和逐请求校验。
2. 身份错误列具体失配字段和 ELF 内容是否相同；保持原身份比较、旧 receipt 拒绝。
3. target unsupported 给出请求值和离线查支持列表方法；不猜映射。flash 外层结果明确 targetState unknown/runVerified false，
   receipt 字节格式和硬件操作序列不变；不 reset/run/重试，不改 recovery 授权。
4. Monitor launcher 的环境错误说明与完整调用示例对齐；保持受管 Python、前台生命周期和严格 Host。
5. UI 缺 fragment、服务拒绝/网络失败的固定提示与可执行恢复说明，继续清除 fragment、防止秘密进入输出。
6. 技能明确 recovery 是显式受控策略、程序运行未验证、Fault 单独授权、Ctrl-C 清理及浏览器关页含义。

验收：原拒绝测试继续通过；外层诊断字段通过 CLI/MCP/相关 IPC 后仍保留，错误不泄漏私密值。
fake/backend 检查 flash 没有新增 reset/resume/state RPC，禁止将其写作硬件结论。
UI 针对缺/错 token 和拒绝分支运行现有 Vitest，检查真实 DOM 不含 token；受影响安全 E2E 在已有环境可用时执行。
重点测试：`test_svd.py`、`test_debug_firmware.py`、`test_debug_handoff.py`、`test_flash.py`、`test_pyocd_backend.py`、
`test_hardware_workflows.py`、`test_cli_hardware.py`、`test_mcp_hardware.py`；Monitor `test_auth.py`、UI bootstrap/main/security。
本切片不需要访问板卡才能证明合同保持；关于报告的实际 attach 失败根因仍是外部待证，不宣称已修复实机运行。

## 5. 切片 D：整理与 1.0.1 交付

版本文件清单：`.claude-plugin/plugin.json`、两个 `pyproject.toml`（含 Monitor 精确 Toolkit 依赖）、
Toolkit `__init__.py`、UI `package.json`/lockfile 顶层项目版本、两个 `bin/*.cmd` 的 runtime 目录、
`bin/setup-stm32-env.ps1` 的当前/旧版白名单/内嵌校验/可信 hash、release builder/policy。
对生成器 producer 兼容表新增 1.0.0，同时保留 0.9.0；不能伪造原 project generatedBy。

1. 升级代码只使用既有事务，验证 Check → 经授权的 Repair → Check、用户数据保留、旧目录 quarantine；
   多旧版/未知未来版、同版本不同来源、降级、被锁 promotion/状态失败保留原拒绝与回滚边界。
2. 整理双语 README、新增一份面向用户的配置/故障说明、一个 CHANGELOG；保留历史出处。
   按用户新增要求审计并清理 master 工作树中过时历史内容。删除前核对当前代码、测试、打包与文档引用；
   用短的现行合同/开发/验证入口替代仍有必要的分散历史说明，精确清单由主代理在写入前冻结。
   保留 Git 历史，不改 v1.0.0 资产；不预写“v1.0.1 已发布”。
3. 使用已有 release builder、精确 wheelhouse/UI 输入和固定 CodeHead 打包；核对全部输出、SBOM/许可和 hash。
   修改 builder/policy 后重算 setup 可信 hash，再冻结最终代码与构建身份。
4. 在一次最终集成/发布层执行适用检查；已改变的产品不能照搬 RC4 覆盖率数字/例外。
5. 准备具体 GitHub 交付材料后再请求远端动作授权；成功后逐项记录 push/PR/merge/tag/Release 身份与下载校验。
   v1.0.0 标签和资产保持不变，GitHub about 可建议描述“Agent-neutral STM32 development toolkit: Keil migration, reproducible builds, probe debugging and Monitor”。
   建议 topics：`stm32`、`embedded`、`mcp`、`cmake`、`pyocd`；不自动创建 22 个重复 issue 或改历史 issue。

重点既有验证：`test_setup_runtime.py`、`test_plugin_layout.py`、`test_package_boundary.py`、
release `test_0900_artifacts.py`，UI typecheck/build/verify:dist，以及实际受管 runtime 的版本与入口检查。
本计划批准并不自动授权修改用户已有 runtime；本地构建、离线 fixture 验证先行，必要安装另给具体候选与目录。

### 5.1 E 历史清理冻结清单与验收

删除选择从远端 base `694c825d29a55a53052a148efa4cc6720c315a04` 的 tracked tree 计算，
不匹配本轮新文件或原脏工作区。380 个旧 docs 与三个旧进度文件退出当前树：

- `docs/openclaw/**`、`docs/codex/lessons/**`。
- `docs/codex/returns/**` 中该 base 的所有文件；保留本轮新增 `STM32TK-101/**`。
- `docs/superpowers/specs/**` 和 `docs/superpowers/plans/**` 中该 base 的全部历史文件；保留本轮新增 2026-10-10 101 规格/计划。
- `docs/testing/2026-10-08-rc4-local-handoff.md`、`.superpowers/sdd/**` 中三个 tracked progress 文件。

同时退役仅用于旧资格流程的12个工具，以下路径均相对 `tools/release/`：
`gates_0600.json`、`performance_0600.json`、`path_contract_0600.ps1`、`run_0502_windows_gates.ps1`、
`run_0600_candidate.ps1`、`run_0600_final.ps1`、`run_0600_gates.py`、`run_0600_hardware.ps1`、
`run_0600_quick.ps1`、`verify_0502_release.py`、`verify_0600_feasibility.py`、`verify_0600_release.py`。

成组删除仅服务这些工具的 Toolkit 测试：`tests/test_0502_release_gate_helper.py`、
`tests/test_0502_release_gate_controller.py`、`tests/release/test_acceptance_feasibility_0600.py`、
`tests/release/test_gate_catalog_0600.py`、`tests/release/test_gate_controller_0600.py`、
`tests/release/test_release_verifier_0600.py`。可删除 `tests/release/fixtures/` 下的
`0502/**`、`coverage/**`、`npm-audit-v11-zero.json`、`native-outcomes/fixture.py`、
`native-outcomes/ctest-pipe/**`、`native-outcomes/playwright-1.56.1-list.json`、
`native-outcomes/pytest-8.4.2-junit.xml`、`native-outcomes/vitest-4.1.10.json`。
明确保留 native-outcomes 的 `ctest-4.3.1-junit.xml`、`ctest-4.3.1-output.txt`、
`ctest-4.3.1-failure-output.txt`，它们仍服务现行 host/CTest bridge 测试。

主代理先建立 `docs/architecture.md`、`docs/development.md`、`docs/release-status.md`、
`docs/testing/release-qualification.md` 并更新标准测试流程和 AGENTS 入口；E 不改这些治理文件。
E 补齐双语 README、CHANGELOG、用户指南与既有路径的 Windows 部署指南；命令必须对照真实 parser/技能，
1.0.1 仍标 in development，未实现的目标行为标版本边界，最终 D 再对齐实际接受结果。

保留当前 release builder/policy、许可证、ui_dist、setup/launcher、全部当前产品和所需测试/fixture。
无 Git 历史重写、archive 镜像、远端操作、新验证器或 CI。验收为准确删除清单、剩余代码/测试/文档引用闭合、
当前打包输入完整、相关 host/CTest 和 release artifact 回归。删除旧专属门禁不降低当前发布资格门槛。

## 6. 验证层、责任和终止条件

| 层级 | 证据所有者 | 环境/所需结果 |
| --- | --- | --- |
| 切片软件 | 各切片实现者；主代理独立复核 | Windows CPython 3.12，现有固定依赖；受影响行为/拒绝与回归 PASS；完整 diff |
| 集成 | 主代理调度，独立验证者执行并署名 | A→B→C→D 同一候选；公开接口连通、旧工程/数据兼容；保留真实日志/退出码 |
| 发布 | 主代理作为发布所有者 | 固定 CodeHead、包和全部版本一致；现有资格门槛及每项复用适用性有具体结论 |
| 外部实机 | 后续具名硬件操作所有者，当前未派发 | 原报告工程、实际固件/板卡/探针和明确授权；如需执行，先填标准流程执行卡；不得用 fixture 代替 |
| GitHub | 主代理在具名授权后执行 | 当前 master/tag 二次核对；具体 PR/版本/资产；禁止强推覆盖和无授权删除 |

每次测试从被测工作树根执行，明确设置 `PYTHONPATH` 指向该树 Toolkit/Monitor src；
使用已有 Python 3.12 解释器和已核实依赖，不临时安装工具。示例命令是模板，实际完整命令在开工记录中固化：

```powershell
$env:TEMP = 'D:\codex-tmp\tk101\t'
$env:TMP = $env:TEMP
$env:TMPDIR = $env:TEMP
$env:PYTHONDONTWRITEBYTECODE = '1'
# 进入被测工作树根，PYTHONPATH 同时指向该树两个 src，节点选择按上面的切片范围。
python -m pytest -o addopts= -p no:cacheprovider --basetemp D:\codex-tmp\tk101\b <selected-test-paths>
```

不得并行共用 basetemp/data/cache；每实际运行分配独立短子目录，先核对最终 staging 路径长度。
完整 stdout/stderr、命令、退出码、CodeHead 保存到本轮证据目录。PASS 属于实际执行者与精确版本。
失败先分类 PRODUCT/INFRASTRUCTURE/ENVIRONMENT/PLATFORM/HARDWARE/REPORT；不得为 ACL/路径问题随意修改产品。
相关必要检查通过后不重复扩测。每次运行结束清理归属明确的一次性产物，保留所需最小失败证据和最终报告。

主代理在另一个干净 worktree 检查每切片 accepted-base→CodeHead 全部差异，以及最终总体基线→最终候选差异。
报告记录 accepted base 和 report commit 之前的 CodeHead，不写自身最终 SHA。
同一问题两轮不收敛则返回设计；覆盖率/报表工作连续两切片超过产品工作须暂停作治理判断，禁止重新开启旧停止路线。
没有完整软件证据则不接受代码；缺必需实机证据为 SOFTWARE_COMPLETE_HARDWARE_PENDING；未获发布准入则不发布。

## 7. 本轮准备交付与下一步

- 已完成：当前远端/版本/权限/脏工作区盘点、报告逐项静态核查、规格和计划草案。
- 尚未完成：任何产品修复、测试执行、版本号更新、安装、实机验证、远端提交或 v1.0.1 发布。
- 当前授权：用户已批准规格和计划，开始切片 A；同时独立审计新增历史内容清理范围，不与产品实现争用文件。
