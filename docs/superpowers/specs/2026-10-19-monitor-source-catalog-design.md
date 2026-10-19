# Monitor 源码变量目录实施规格

2026-10-19，用户明确“变量类的你继续完成”，本规格把[此前调查](2026-10-19-monitor-source-catalog-discovery.md)冻结为后续实施合同；沿用用户对Monitor开发/测试/审查/本机服务更新的授权，不另设派生计划审批停点。Accepted base：`1c320d9dc102ca11a280b97e210517ac5a852b63`。主代理负责规格、集成、验收和部署；`source_catalog_impl`为唯一实现/测试者，另由`source_catalog_review`独立审查，均gpt-6-sol/max。分支`codex/monitor-source-catalog`，无PR、远端动作、安装或所有权例外。

## 四个可运行场景

1. 打开项目后，变量页默认加载源码目录，无需连接探针或手输变量名。按实际参与编译的项目文件→函数/作用域收纳声明，显示总数、已加载数、覆盖编译单元数和分页。查询可匹配名称、文件、函数。当前F429工程的testtime、文件static和函数内gpio/now均可找到；没有样本不生成数值。
2. 全局、文件static、静态局部、自动局部和参数都列出；“源码存在”与“可定位且可解码采样”分开。自动局部/参数标明需要运行栈帧；同名或未匹配DWARF等对象给准确原因，不能静默消失，也不能从源码猜地址。仅当前目录身份和活动绑定一致且通过旧读引擎验证的叶对象可加入原观测组草稿。
3. 可定位的全局结构体/数组按需展开已有读取语法支持的成员/元素；叶对象通过原lookup与读取限制。聚合根不可直接当标量采样；深层/大数组有界分页和截断提示，不生成无界DOM。加入后原保存、采样、数值、波形和CSV路径保持一致。
4. 源码、构建、ELF或探针绑定变化时目录身份失效。仍可浏览源码并显示差异，但禁用不再证明有效的加入操作；旧响应、游标、子项和选择校验不能污染新目录。部分编译单元失败必须显式显示覆盖不完整，允许本区重试，不整页阻断。原固件变量目录和寄存器功能可继续使用。

非目标：安装工具、编译/烧录固件、停核/栈帧调试、扩展同名变量Watch语法、宏常量目录、未参与构建的条件分支、外部系统头文件声明、C++完整支持、改采样/访问授权/历史/导出或版本、浏览器/新硬件验证、远端动作。首个支持集是本机Windows/Python3.12、STM32 GNU Arm C项目、已安装Clang兼容前端；其他语言/引擎失败必须明确覆盖边界。

## 已验证引擎与输入

本机已有`C:\ST\STM32CubeCLT_1.22.0\st-arm-clang\bin\starm-clang.exe`（ST Arm Clang21.1.1）。只读离线能力检查：当前Ninja项目21个实际C编译命令，21/21语法检查及JSON AST生成成功；AST合计331.5MB、单元最大54.1MB，生成共约5.59s。该证据只是源码解析，不是实机/采样或本产品实现PASS。pycparser无法直接覆盖GNU/CMSIS扩展，不作为降级语法剥除器。

新增唯一的编译器感知适配器负责源码声明发现，复用现有DWARF/读引擎。工具发现优先明确配置/已知Clang和ST安装路径及PATH，版本探测；不下载、不运行用户提供的任意可执行文件。优先使用现有Ninja `-t compdb`的只读有效命令；没有现成构建时从已验证manifest的sources/includes/defines/compileOptions和既有C模板规则生成解析参数，标明输入来源，不能宣称复用了不存在的实际命令。

命令采用直接argv，无shell；Windows命令拆分使用系统命令行规则。丢弃对象输出、依赖输出、链接、插件、响应文件和其他可能写入/执行扩展的参数；仅明确允许的语言/目标/ABI/宏/包含路径及解析有关选项传给Clang，显式`-fsyntax-only -Xclang -ast-dump=json`。未知会影响声明语义的选项不得静默忽略，记录该单元不支持。所有源/包含/命令目录经现有project边界校验；不能执行CMake配置、构建或项目脚本。

编译器条件集成澄清：主代理实测实际GCC的`__GNUC__=14`，ST Clang为4并定义`__clang__`，因此直接由Clang预处理不能证明实际GCC分支。对于本支持集，适配器必须先用受信任的现有GNU Arm GCC按有效命令执行有界`-E`，保留line markers（禁止`-P`），再将预处理C交Clang只做语法树解析；两阶段各有唯一职责，不伪造内建宏、不剥除C语法。AST的presumedLoc/line-marker映射回真实项目文件，不能把临时预处理文件当用户源位置。两阶段都受上述选项/时间/输出总预算约束，预处理单元额外上限32MiB。测试须包含`__GNUC__`/`__clang__`条件分支，原直接Clang的21单元能力证据不替代此保真检查。

保持v1 engine字段不变，name明确命名GNU Arm GCC预处理与Clang AST两个阶段，version包含两者实际版本。catalogId/缓存键纳入两个受信工具的解析后身份、版本及分阶段argv指纹，任一变化不得复用旧目录/选择资格。

AST逐单元处理，stdout增量有界读取，不能先无限capture再检查：每单元最多80MiB、单元30s、总120s/1GiB、最多256个C单元、100000条声明。超过预算明确失败/覆盖不完整。临时输出仅在本轮独占根，完成后清理。子进程取消/关闭只收回自己拥有的子进程；运行在非事件循环线程，不能阻塞采样/状态服务。索引缓存只有一个所有者、最多两个输入版本；同输入并发请求合并，完整索引原子发布，取消后仍受固定预算且关闭可终止自己子进程。

Clang位置字段会省略重复file/line，适配器必须跟踪输出文件上下文并由源字节offset映射行列，处理spelling/expansion位置；不能把上一文件或编译单元当成每个局部的声明文件。只纳入项目内源/头文件的非隐式VarDecl/ParmVarDecl。记录文件、位置、名称、类型、storage、函数及词法作用域；声明ID由这些稳定身份构造，禁止使用Clang进程地址id。跨单元相同声明可合并并保留translationUnits，头文件static/类型变体不能误标为一个唯一可读实例。

## 身份与可采样性唯一来源

源码身份复用`load_project_model`和`snapshot_project_inputs`。离线构建身份复用`load_fresh_firmware_facts`，ELF读取复用`DwarfCatalog.from_elf`及预期size/SHA和模型可读区域；本端点不调用Observation.revalidate/list_variables或任何探针API。可比较活动observation的内存binding，但这不是新物理核对。

DWARF增加不可变的源码归属投影，解析decl_file/line/column、CU及函数/作用域，按现有规范处理specification/abstract_origin并有界防循环。原lookup、bare-name冲突规则和公共Watch语法不变。仅名称相同或CU相同不能启用加入；无法唯一证明源声明对应调试对象时给未匹配/歧义原因。未找到条目不能一概声称“被优化掉”。

如果DWARF定位到头文件extern声明而定义在C文件，允许用Clang明确的previousDecl/redeclaration链证明它们是同一实体，再与一个唯一源码归属的DWARF实体关联；不能只按裸名把不同文件static或阴影局部合并。缺少该证明时仍显示准确不可用原因。

可采样叶须唯一源归属、稳定地址、已有标量decode类型、原lookup和读范围/大小限制；结构体成员和常量数组下标仅用原`.member`/`[index]`语法，拒绝位域、未知/越界和不支持类型。聚合展开最大深度6、每次分页最多100、单根最多4096个后代；达到界限显式标记还有/截断，不能宣称已展示全部叶。

`canAdd`只表示当前目录的本地ELF证明和已登记活动binding身份一致，不能冒充物理固件PASS。源码快照、有效构建/ELF、逻辑项目/目标和活动binding身份任一不符、未连接或覆盖不完整时，canAdd=false且有原因。原group API仍接受旧WatchItem，采样开始仍走旧物理身份/读计划门禁；本切片只严格约束新目录的加入动作。

## 新公共合同与状态归属

保持旧`/api/v1/catalog/variables`、`/registers`、Toolkit CatalogPage/VariableDescriptor及WatchItem不变，新增同一鉴权/查询白名单下的只读接口：

- `GET /api/v1/catalog/source-variables`，operation `monitor.catalog.source_variables`；query为`query`、`cursor`、`limit`（1..100，默认100）、可选`parentId`和该展开所属`catalogId`。初页以声明为根，子页返回同一目录下该聚合对象的子项；游标绑定catalogId/query/parent。
- data包含`schemaVersion:1`、`catalogId`、`identity`（workspace/session/logicalProject/target、sourceSnapshotSha256、可空buildId/elfSha256、bindingEpoch）、`engine`（名称/版本/输入来源）、`coverage`（complete、totalUnits、parsedUnits、问题列表和truncated）、`total`、`items`、`nextCursor`。各条包含稳定`id`/`parentId`、`name`、`typeName`、相对`file`、`line`/`column`、`scope`及storage、translationUnits、可空`selector`、`canAdd`、`reason`、`expandable`及截断信息。类型中明确nullable与枚举，UI严格校验，不把声明ID放进selector。
- `GET /api/v1/catalog/source-selection`，operation `monitor.catalog.source_selection`，query为`catalogId`、`id`、`selector`；离线重新核对输入/构建/活动binding和该条可用性，成功返回`{catalogId,item:WatchItem}`，否则返回可重试的目录身份变化/不可用错误。UI只有此成功且当前目录仍匹配才加入原草稿；不得借此访问硬件或自动保存。

字段精确化：identity使用`workspaceId/sessionId/logicalProjectId/targetDevice/sourceSnapshotSha256/buildId/elfSha256/bindingEpoch`，后者沿用十进制wire bigint；engine为`{name,version,inputKind:"compdb"|"manifest"}`。coverage为`{complete,totalUnits,parsedUnits,issues:[{unit:string|null,code,message}],truncated}`，total为当前query/parent下的条目总数。条目`scope`为`{kind:"global"|"file_static"|"static_local"|"local"|"parameter"|"member"|"element",function:string|null,path:string[]}`，storage为`"none"|"static"|"extern"|"register"|"thread_local"`；line/column为正整数或null（未知位置不得获得源码归属证明），file为经过校验的项目相对路径。reason为null或`probe_required/source_mismatch/firmware_unavailable/frame_required/debug_entry_missing/ambiguous_symbol/unsupported_type/unsupported_location/read_range_denied/aggregate/coverage_incomplete/limit_reached/source_attribution_unproven`之一。selector为既有Watch语法字符串或null，不能由id替代。expandable/truncated/canAdd均为boolean。字段上下界和可空性两端共用同一fixture，拒绝重复id、坏父子关系和不匹配catalogId。

响应仍满足既有1MiB上限。query大小、路径、游标及身份错误统一返回有限可诊断错误，不能把任何请求路径/编译stderr/主机绝对路径原样反射到页面。缺引擎用`MONITOR_SOURCE_ENGINE_MISSING`；超限/解析问题用`MONITOR_SOURCE_INDEX_FAILED`或显式partial coverage；身份/旧游标用`MONITOR_SOURCE_CONTEXT_CHANGED`，选择不可用用`MONITOR_SOURCE_SELECTION_UNAVAILABLE`。部分结果只在coverage明确时返回，不是全量PASS。

Runtime/源码索引提供者拥有索引和快照/归属事实；reducer拥有页面、已接受目录身份、子页、pending/failure和草稿，controller拥有请求id/退休/安全重试。App只有展示选择。新source状态不重用要求连接的旧catalog binding key；用状态中的workspace/session/project/bindingEpoch上下文封口，响应再携带完整catalogId。上下文改变退休旧source/children/selection请求并清空旧加入资格，旧响应不可重新启用按钮。source选择成功还须复核当前目录代次及当前草稿仍允许添加。

上述客户端上下文必须包含完整可见身份：连接布尔值、probeId、firmware的build/ELF/input/git/target身份以及workspace/session/project/epoch，不能只用四段key。即使epoch未变，断开或替换固件也必须拒绝迟到page/children/selection；controller门禁与reducer采用均检查该上下文。异步加入还携带开始时的groupGeneration，消费者拒绝已切换/重载到另一草稿的旧成功；单纯同草稿名称编辑不丢弃。展示回调另有上下文代次，不能因迟到加入打开新的历史/寄存器界面上的旧抽屉。

默认变量页展示源码目录并自动加载首个有界页面，加载期间只本区域等待，不阻断实时工作台；提供手动刷新、文件/作用域折叠、查询和清晰分页计数。保留“固件可采样变量”旧目录作为显式切换及无Clang时的可用入口。寄存器仍按外设分组。切换视图保留组草稿/导入/历史/导出；暂时离开不能造成旧source请求覆盖新上下文。

## 验收与集成

实现者验证Clang适配器的真实离线C fixture和当前21单元工程；覆盖文件省略位置、头文件/宏位置、同名static、函数参数/自动/静态局部、条件编译、结构体/数组、无DWARF/歧义/类型/范围不可用、源码/ELF/活动binding变化、部分失败/超限、旧游标、注入选项拒绝与取消清理。真实项目AST检查是离线证据，不是采样验证。跨后端DTO→service→真实UI client使用同一封套fixture，不能只各自mock证明接通。

UI验证未连接自动发现、文件/作用域搜索/收纳、分页、展开、有原因的禁用、加入前校验、身份变化的迟到/选择应答、现有草稿/采样/波形/历史/CSV回归。合入已验收的探针反馈修复后才跑最终全UI、两个typecheck、lint/build/dist及受影响Python测试；不重复无关发布矩阵。主代理和独立审查者在精确CodeHead干净树审完整差异并做精选集成后更新8765。浏览器和新硬件仍DEFERRED，不升级版本、不进行远端动作。
