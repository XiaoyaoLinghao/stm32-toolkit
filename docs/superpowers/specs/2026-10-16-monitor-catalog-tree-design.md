# Monitor 按来源收纳变量与寄存器

2026-10-16；Full accepted base：`c836df30de046e2d630157caeaa5a006eb870ce2`（先行连接修复的最终本地接受提交，产品 `8bfba36d365df07acd6854ca2dfd1c9974393bef`）。实现分支 `codex/monitor-catalog-tree`，实现树 `D:\codex-tmp\mufin1015\impl` 从此干净base分出；原始工作区、交付分支、运行中的连接修复审查树均保留。用户请求左侧目录按程序块收纳，已授权连续本地实施。主代理拥有本规范、集成、完整差异审查和接受；单一 gpt-6-sol/max 实现者拥有产品/测试；独立 gpt-6-sol/max 审查者复核。无 ownership override；无新增 push、PR、merge、tag、release 权限，版本仍1.1.2。

## 三条可运行场景

1. 连接后加载变量目录，按真实 DWARF 编译单元（源文件）显示折叠组。展开所需文件、查看变量类型、将叶项按原 selector 加入观测组草稿；未知来源有明确单独分组，重名文件不错误合并。
2. 切换寄存器目录，按真实 SVD 外设分组。带点号的外设名仍为一个正确组，展开可查看寄存器及原访问风险提示；禁止采样的寄存器仍不能加入。
3. 名称搜索、加载下一页、重试、身份变化和切换目录保持正确性；同组跨页合并展示已加载项，不宣称目录已全部加载，不允许将旧绑定/旧搜索条目加入草稿。

## 冻结数据与依赖

沿用现有 DWARF/SVD 引擎、CatalogPage、MonitorObservation 的重验证与分页，不新增引擎或查询服务。现有 Toolkit VariableDescriptor、RegisterDescriptor 和 CatalogPage 的 `to_dict()` JSON 合同保持不变。可在 descriptor 上增加只用于内存传递的不可变可选 `catalog_group` 元数据，默认 None；新值含经过校验的 id/label，`to_dict()` 排除该字段。生产解析器填入真实元数据，Monitor runtime 为 UI 输出每页 item 时显式附加 `group:{id,label}`，nextCursor 不变。

新增 group 为 Monitor 变量/寄存器列表 item 的必需字段，id 为1至128字符的 ASCII opaque identity（字母、数字、冒号、下划线、横线），label 为1至512字符的可打印纯文本。无元数据的兼容 descriptor 由 Monitor 适配器映射为按类别区分的固定 unknown id 和中文“未标注来源”/“未标注外设”；不能猜测归属。前端分别定义带 group 的 catalog item 类型和严格 guard，复用原 descriptor guard；原描述符契约与其他协议测试不需要接受额外字段。缺失/无效 group、未知字段必须产生原 MONITOR_RESPONSE_INVALID，不静默丢条目。

DWARF 在解析 CU 时取得 CU offset 和 DW_AT_name、DW_AT_comp_dir；在内部 _CatalogSymbol 保留 group 并传至每个可返回根 descriptor，后续分页只透出同一对象。id 固定为 `cu:<CU offset十六进制>`，限定在现有 bindingKey/ELF 身份作用域内；不能只用文件名作为id。若名称缺失，同一 CU 仍有独立id和“未标注编译单元”标签；原歧义 selector 排除规则不变。目录只分组已有根变量，不扩张可采样类型，不枚举不存在的成员。

来源路径仅作显示元数据，不打开源文件或绕开 ELF/绑定验证。只有 DW_AT_name 自身为绝对路径或与绝对 comp_dir 组合成绝对路径，且词法规范化后可证明位于已绑定 project root 内，才显示项目相对路径。相对 comp_dir、跨盘、外部、异常编码或过长路径降级为安全 basename，仍无法安全提取则显示未知标签。元数据异常不得使目录失败。禁止传出原始绝对路径、控制字符或遍历串；不同 CU 同标签仍为独立组。

SVD 解析展开后的 peripheral identity 时在内部 SvdRegister 记录组信息并传至 descriptor；id 固定为 `svd:<exact expanded peripheral name 的 UTF-8 SHA256>`，label 为该外设名。不能通过 selector 的第一个点切分：合法 SVD 名称可含点。register selector、cluster、readAction/access、sampleable 与 requiresAccessAcknowledgement 保持。

## 展示与生命周期

CatalogPanel 用原生 details/summary 展示可键盘操作的两层目录。普通空查询加载后默认折叠；非空名称搜索得到的新结果默认展开命中的已加载组。相同绑定+目录类别+已提交 query 内，用户的展开/收起选择跨追加分页保留；绑定或已提交 query 变化后重置该选择。变量/寄存器状态分别管理，不由输入框尚未提交的文本提前替换结果。

每组显示已加载项数量，目录注明“已加载 N 项”；nextCursor存在时显示还有更多结果和既有加载下一页入口，不将分组数或已加载数当总数。跨页按group.id归组，页面中每个selector只显示一次；相同descriptor重复可保留首次项，但同id不同label或同selector不同group视为契约矛盾。页内在严格响应校验处拒绝；追加页与同绑定/类别/已提交query已接受结果冲突时，由controller以当前请求作用域返回原 `MONITOR_RESPONSE_INVALID`，整页不追加、保留旧结果并允许原就地重试，不静默改变归属。不同id同label保留独立组，可附显示序号帮助区分。

保留旧搜索结果提示、bindingKey保护、pending/editBusy、寄存器访问限制、失败就地重试、原样selector加草稿及手动编辑组的能力。此次搜索继续匹配变量/寄存器名称，不宣称支持按源文件内容搜索。不自动预取全部目录、不自动硬件连接或采样。

## 非目标与证据

不增加函数/词法块层、结构体或数组递归浏览、完整组索引、服务器分组筛选、虚拟列表、固件变更、安装新依赖、权限排查或浏览器自动化。只添加真实来源一级分组，后续深层类型浏览须另定契约。

离线验证覆盖：DWARF 两CU/同名文件/未知来源/项目内相对路径/外部绝对路径不泄露/歧义符号仍排除；SVD 外设名含点和簇、跨页；Toolkit 原JSON不变；Monitor runtime逐item分组wire和严格UI解析；折叠与键盘、搜索默认展开、跨页状态保持、旧绑定/旧query禁止加入、原寄存器风险规则。UI共享catalog fixture发生变化，允许一次完整UI回归及typecheck/lint/build/dist；Python仅相关目录与Monitor runtime回归。主代理和独立审查者审查完整base→CodeHead，浏览器和新实机证据继续暂缓。
