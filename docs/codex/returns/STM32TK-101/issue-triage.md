# 2026-10-10 问题清单核查与 v1.0.1 处置

状态：静态核查完成，用户于 2026-10-10 批准实施；本表为基线分类，实际测试及接受结果见执行记录。
基线：`694c825d29a55a53052a148efa4cc6720c315a04`。
来源报告 SHA256：`ef8b0cb66d76f9d3088162baf9e50b093e9c2ff288dab58c833b671dd60372ae`。

下表 `TK` 指 `tools/stm32-toolkit/src/stm32_toolkit/`，`MON` 指 `tools/stm32-monitor/`。
行号为本基线定位。用户报告观察、代码能确认的事实、拟修范围分别处理。

| # | 代码核查与证据 | 拟议 v1.0.1 处置 |
| --- | --- | --- |
| 1 | TK `keil/uvprojx.py:211-260` 与 `detection.py:74-95` 均只查根目录；显式路径可用 | 修复：根内安全递归候选发现共用，歧义显式选择 |
| 2 | TK `migration/rules.py:446-460` 拒绝非 UTF-8；旧 0303/H1 合同也明确限制。resolved finding 集合用于消除重复分类，不等于实现转换 | 保留编码边界，改善前置诊断和项目自有适配指南；GB 自动猜测/转码不纳入补丁 |
| 3 | TK `migration/planner.py:410-423` 阻断 ARM assembly；H1 已排除通用 startup generator | 保留 blocker，明确项目自有 GNU/C startup 和向量/初始化核对要求；不能从旧 vendor 产物推断 Toolkit 通用模板退化 |
| 4 | TK `generation/configure.py:1152-1176` 实际拒绝覆盖，并非“必然覆盖” | 新的窄保护规则：仅未托管普通 editor 文件 preserve；必需构建文件仍拒绝冲突 |
| 5 | TK `probe/flash.py:578-647` 无 reset/run/运行后置；recovery 规格明确保持 halted。OBSERVE resume-verify 要求 running | 外层结果/错误说明运行未验证；不自动 reset 或放宽 OBSERVE。报告实机根因仍待实际证据 |
| 6 | TK `debug/svd.py:1039-1098` 全 SVD 范围校验，缺寄存器详情；`hardware_workflows.py:1703-1738` 在 binding 前选择。2026-08-27 production-svd 规格及标准流程已有说明，缺的是易发现的用户指南 | 保留全文件选择合同，补失败路径/地址/宽度/范围和 SVD 工程内路径说明 |
| 7 | TK `probe/handoff.py:881-929` 比较多项 provenance，不只是 buildId；`build/identity.py:743-758` 含 input snapshot | 保留绑定保护，错误列失配字段及 ELF 是否同内容；内容寻址 rebind 另行设计 |
| 8 | TK `pyocd_backend.py:960-986` 使用 explicit target；`doctor.py:109-165` registry 是 Probe 租约目录 | 提示请求目标及离线支持列表核对方法；纠正 registry 因果解释，不自动映射型号 |
| 9 | TK `build/map_file.py:283-288` 对不同 LMA 统计，`build/identity.py:682-700` 未传 NOBITS 属性 | 修复可确认的 NOBITS 显式 LMA 误计路径；原报告数字须 ELF/MAP 才能复现 |
| 10 | TK `build/map_file.py:316-325,354-385` 已按区间并集，非最高地址跨度；报告 .stack 自身包含大预留 | 不错误释放 section 内保留空间；补 allocated/reserved 与运行时使用区别及回归 |
| 11 | TK `context.py:157-175` 发现受 #1 影响；context 不做实际探针枚举；build 标志含当前管理状态 | 修复 Keil 一致性，明确 hardware 未探测和 readiness 含义；不制造最近探针缓存 |
| 12 | migration Git clean 包括 untracked 是恢复/冲突保护，不自动知道哪些本地文件可忽略 | 保留拒绝，区分 tracked/index/untracked 并提示用户审阅 Git ignore；不自动忽略、stash、删除 |
| 13 | Keil baseline 读历史 AXF/MAP 不证明本次编译、工具链或授权来源 | 明确 available 仅为历史产物发现，不能凭 mtime 升格可信证据 |
| 14 | TK `doctor.py:25-34,189-217` 对 CubeMX 执行版本进程；`tool_support.py:357-395` 已有静态版本路径 | 直接修复：复用静态读取，取不到为 unknown，GUI 零启动 |
| 15 | `skills/migrate-keil/SKILL.md:15` apply 示例丢 uvprojx/targetName；TK `workflows.py:193-228` apply 重做 inspect | 修复技能完整参数链与能力解释；保留 planId 验证 |
| 16 | recovery 为显式修改策略，并非所有旧固件必需；原 flash 成功不证明 running | 补准确恢复/失败/运行状态和 Fault 指引，不强制 recovery 或承诺自动恢复 |
| 17 | configure skill 已提 unowned-collision 但缺处置；安全拒绝本身正确 | 跟随 #4 新规则解释 preserved editor 与仍阻断构建文件，不建议删原文件绕过 |
| 18 | MON `src/stm32_monitor/cli.py:83,91,224-235` 已消费 data-root；`bin/stm32-monitor.cmd:4-14` 先需 env 定位解释器；open 前台是合同 | 改 launcher 错误及技能示例；现有 Ctrl-C 清理说明。后台/stop 新协议不在补丁 |
| 19 | MON `src/stm32_monitor/auth.py:86-111`/`service.py:408-414` 严格 Host 为安全合同；UI `src/bootstrap.ts:12-30` 错误过泛 | 保留 127.0.0.1；修复无秘密 UI 恢复提示，补正确标签入口 |
| 20 | TK `generation/configure.py:266,331-357` 是生成阶段约束；project_model containment 和 SVD 内容校验不能单靠 schema | 写清阶段约束；不把生成规则偷偷变成全局 loader 不兼容限制；schema 副本一致 |
| 21 | linker 模板 __StackTop 低、__StackLimit 高，确实颠倒；默认大小属于已有边界 | 修正符号并验证链接；不增加堆栈字段，特定项目容量用既有 native linker |
| 22 | 九固定目标与 editor 文件冲突；managed parser/build/context 并不要求五 editor 记录必须存在 | 同 #4 保留用户 editor；不 merge/adopt，不扩大 CubeMX regeneration 闭域 |

报告 §五的 debug 元数据触发 configure/build/receipt 刷新属于现行全输入身份合同。
本补丁提供诊断与正确步骤，不声称已经取消重建/重烧。内容等价复用需要独立的身份/授权设计。

额外确认的发布问题：当前 README 仍写 v1.0.0 未发布，与实时 GitHub Release 不符；
1.0.1 还须更新 runtime launcher、Repair 的 1.0.0 白名单、generation producer 兼容、release utility/policy 的可信 hash。
仅改 pyproject/plugin 版本会破坏现有用户的升级路径。

新增功能后置清单：显式非 UTF-8 迁移支持、GNU startup 来源适配、堆栈配置、allow-untracked、SVD 按请求选择、
ELF 等价绑定、目标型号建议、显式 reset/resume、Monitor 后台/stop，以及保留编辑器文件的 CubeMX regeneration 适配。
这些不是已修复事项，也不能在发布说明中列为完成。

完整合同与验证责任见[规格](../../../superpowers/specs/2026-10-10-stm32tk-101-patch-design.md)和
[实施计划](../../../superpowers/plans/2026-10-10-stm32tk-101-patch-plan.md)。

## 实施后逐项结论

下表是软件与文档处置，不把未提供的原工程、ELF/MAP、板卡或运行日志当成本轮复现证据。
实现头、审查范围、命令及失败归属详见[执行记录](execution.md)和 B/C/E/D 实现报告；最终发行准入另见
[发布状态](../../../release-status.md)。

| 报告项 | 已完成处置 | 验证边界或仍待证事项 |
| --- | --- | --- |
| 1 | 根内安全递归 Keil 发现，共享给 detect/context/inspect/convert | 多候选明确拒绝；Junction 不越界；不可枚举不是“无工程” |
| 2 | 明确 UTF-8 限制和工程自有编码适配步骤 | 未新增自动猜编码或转码；原拒绝是现有边界 |
| 3 | 通用 ARMCC 汇编与 startup 分开说明，保留 blocker | 指令/段/符号/调用约定需工程适配；startup另核对向量和初始化 |
| 4 | configure 保留五个未托管普通编辑器目标文件 | 不读写/收编；目录/链接/构建文件冲突及 managed drift仍拒绝 |
| 5 | flash 外层结果明确 postFlash 未验证 running；失败给最后已知状态 | 原现场 attach失败根因仍需原板卡证据；不新增reset/resume |
| 6 | SVD越界错误给首个寄存器路径/地址/宽度/可信区域 | 保持所选文件全部解析寄存器校验；用户指南补齐选择步骤 |
| 7 | mismatch给具体身份字段及经过验证的ELF内容比较 | 不放宽完整provenance，不复用/改写旧receipt |
| 8 | target-unsupported给请求target和离线支持列表核对方式 | registry仍是Probe租约目录；不自动猜器件或安装pack |
| 9 | ELF传递NOBITS类型，MAP加载区统计排除无文件内容段 | 真实ELF/MAP fixture与公开build验证；原报告数值未复现 |
| 10 | 保留区间并集统计，补allocated/reserved与运行峰值区别 | section内部预留不能算空闲；运行峰值需实体测量 |
| 11 | context与发现一致，显式标当前readiness和硬件未探测 | 没有制造探针缓存或宣称硬件已连接 |
| 12 | Git dirty诊断区分tracked/index/untracked，补处置引导 | 保留迁移保护；不自动ignore/stash/delete |
| 13 | baseline明确仅历史产物可解析 | 不凭mtime或文件存在升级为本次构建证据 |
| 14 | doctor与setup Check都不启动CubeMX/Code；扩展not-probed | 静态版本缺失为unknown；marker用例证明GUI命令未执行 |
| 15 | migrate Skill传递同一uvprojx/targetName/planId，解释capability | 公开迁移→配置→构建fixture回归保持 |
| 16 | 补recovery、halted、Fault及运行态前置说明 | recovery不是通用自动补救；未宣称实机自动恢复 |
| 17 | configure Skill与指南解释preserved editor和仍阻断项 | 不建议删除用户文件来绕过保护 |
| 18 | launcher解释环境变量/CLI根区别，补前台open/Ctrl-C步骤 | 不新增daemon或stop/restart协议 |
| 19 | UI区分无token、401/403、其它服务错误、连接失败的安全提示 | token不回显；127.0.0.1 Host限制不放宽；UI与security E2E验证 |
| 20 | 文档明确loader与configure阶段约束 | 不改变schema全局兼容性；保留唯一约束来源 |
| 21 | 两个模板改为StackTop高、StackLimit低 | readelf和链接fixture核对；不新增堆栈容量字段 |
| 22 | 与4同一preserve合同，应用结果返回data.preservedPaths | 既有managed记录和CubeMX regeneration闭域规则保持 |

额外交叉审查修正：setup技能旧GUI探测说明、build技能丢失已批准clean参数、1.0.0升级/producer兼容、
各发行身份与可信hash，以及四份无现行依赖的旧技能草稿。当前树共退出417个历史文件；完整Git历史保留。
