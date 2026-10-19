# Monitor 完整源文件目录树

## 身份、授权与边界

Accepted base：`3c4e2594bafc8d7ca2f1b00c1efe6683639cf05c`，其产品字节为上一轮已接受并部署的`423dc766e60233e4e79bd1ed5306e6631c1d3daa`。用户本次明确要求完整源文件树、不受变量分页影响，完成测试和独立审查后更新8765；此前已授权后续开发无需重新审批。本规格冻结该范围内的集成选择，不新增审批停点。主代理拥有设计、计划、完整差异审查、验收和部署；一个gpt-6-sol/max实现者独占产品与测试，另一同配置审查者独立审查。无所有权例外。

本地分支`codex/monitor-source-file-tree`，实施树`D:\codex-tmp\st1019\impl`。保留原用户工作树和现运行服务；无push、PR修改、远程merge、tag、release、安装、版本变化、用户固件构建/烧录或新硬件访问。浏览器、实际认证HTTP和新实机验证继续DEFERRED，未来由主代理在用户恢复相应验证后执行。

## 四个可运行场景

1. 默认源码页列出当前项目全部纳管源文件，如main.c、safe.c及没有变量的文件；文件列表不会因前100个变量均来自某文件而遗漏其他文件。按真实相对路径派生文件夹，保留扩展名；同名文件按路径区分。文件/文件夹可折叠，默认不展开叶子。
2. 展开文件显示文件级变量作用域及真实函数声明/定义作用域，包括没有局部变量的函数；展开作用域才读取变量。每个作用域独立分页，其他文件和作用域不因其分页被替换。原结构体/数组展开和经校验加入草稿继续可用。
3. 按文件、函数或变量名查询完整索引，显示匹配文件及作用域；展开后仅显示同一已提交query下的结果。文件名或函数名命中时可列对应作用域全部变量。根目录和各分支失败局部提示、对应重试，不阻断工作台，不影响另一个已展开分支。
4. 查询、源码/ELF/绑定上下文变化或关闭使旧树、分支、页、错误和选择请求退休；迟到页和选择ACK不能恢复旧目录/加入资格或重开已离开的抽屉。保留探针反馈、数值优先、采样、分组、历史、CSV及旧固件目录/寄存器。

非目标：任意磁盘文件浏览、解析未构建代码分支、完整C++、栈帧读取、编辑源码、另一套采样/认证/索引引擎、虚拟列表依赖、快照先发布再补AST的双阶段生命周期。本切片的“先列文件”是导航顺序；首次仍复用上一轮有界完整离线索引，不承诺解析完成前先发布文件。

## 文件、函数与唯一事实来源

只复用现有snapshot_project_inputs、SourcePlan/SourceIndex和SourceCatalogProvider。一次facts读取保留同一快照entries：纳入模型声明的源/汇编、纳管C源/项目头文件（.c/.h，大小写不敏感），以及AST中有声明/函数且确属同一snapshot的其他扩展文件；不另外递归扫描工作区。无变量文件由快照保留。未参与当前C编译的头文件/汇编可以列目录，但没有解析结果不能声称已解析其函数或不存在变量。

AST中项目内但不在权威snapshot的文件不能静默加入“已验证输入”；显式记录coverage issue，过滤该文件的声明/函数并使索引partial/canAdd=false。不扩大build.identity公共输入合同，不按basename猜来源。函数和文件元数据纳入目录结果摘要，目录/变量/选择共享同一catalogId与完整上下文。

适配器新增不可变SourceFunction元数据（稳定id、name、file、line/column、translationUnits）；SourceDeclaration追加兼容默认字段function_id。AST遍历FunctionDecl时以真实源位置、名称及声明身份构造稳定词法函数scope id，直接传给其ParmVarDecl/VarDecl，不能凭function字符串反向猜关联，也不能用Clang进程地址id。保留函数声明/定义的源码位置区别，跨TU同一源码作用域可合并并保留translationUnits；函数内部block path原样保留。文件级scope由文件身份独立构造，函数scope ID沿用该真实AST关联。空函数也有scope，空文件不伪造变量。

仍由一个provider拥有最多两个base/view缓存、同key合并、partial根重试、取消回收和原Windows Job生命周期；不修改通用process.py。昂贵元数据构建/查询离开事件循环，按file/scope键预索引，不新增全量平方匹配。保留原编译器预算和身份复核。

## 公共合同

新增`GET /api/v1/catalog/source-tree`，operation为`monitor.catalog.source.tree`，使用现有鉴权/封套。query白名单：query（沿用128字符）、cursor、limit（1..1000，默认1000）、parentId、catalogId。初页无parentId返回文件节点；parentId仅接受当前catalog的file节点并要求catalogId，返回其scope节点；scope不是本接口可展开的parent。后续元数据页必须携带catalogId。不能接受请求提供的文件系统路径。

响应延用schemaVersion=1、catalogId、identity、engine、coverage、total、items、nextCursor，身份、覆盖率和错误合同复用上一轮。items为严格可辨识联合：

- file：`{kind:"file",id,parentId:null,file,name,variableCount,scopeCount}`。file是已验证相对路径、name是含扩展名basename；计数为当前query匹配数量。
- scope：`{kind:"scope",id,parentId:fileId,file,name,function:string|null,line:number|null,variableCount}`。文件级scope的function=null，name使用稳定机器标签global，由UI显示“全局／文件作用域”；函数scope使用真实函数名和位置。

ID均为64位小写hex；line为正整数或null；路径<=512、名称<=256、计数为非负安全整数。文件节点上限10000；scope总量由有界函数元数据上限100000加每文件最多一个文件级scope约束（单文件最多100001）；不能通过静默截断冒充完整树。原AST声明与函数总量有界，各不超过100000，超过时coverage明确partial。单页最多1000 metadata项，并按900KiB data预算缩小，始终满足服务1MiB总上限。

原`GET /api/v1/catalog/source-variables`/`monitor.catalog.source.variables`新增可选scopeId，必须伴随catalogId且与aggregate parentId互斥。无scopeId保持旧公开行为；有scopeId只返回该scope的声明根，变量仍limit1..100，返回原SourceCatalogPage。成员继续使用旧parentId+catalogId展开。新scopeId与旧parentId、query、catalogId及tree/variables域标识一并进入HMAC cursor绑定，禁止跨scope、跨域及跨query复用游标。source-selection合同及旧Watch语法保持不变。

搜索语义统一NFC/casefold：变量匹配原name/file/function；函数节点也按真实file/function匹配，空函数可被搜到；文件名命中则保留文件所有scope，函数名命中则保留该scope全部变量，变量名命中则只保留匹配路径。query为空保留全部纳管文件和真实函数，文件级scope只在有对应变量时存在。部分解析的计数仅代表已解析声明，必须配coverage提示。

## 前端状态、请求和重试

reducer的catalog.source是唯一页面状态：query/initialized/generation/contextKey、完整根tree、按fileId的完整scope元数据branches、按scopeId的独立变量scopePages、原aggregate children和lastAddedId。不再从单一变量page反推文件目录，不另建Panel页面缓存；Panel只持有展开与输入草稿状态。选择查找覆盖scopePages及aggregate children，并保留原catalog/context/generation/groupGeneration/selector门禁。

目录generation改变时必须重置文件夹/文件/scope及成员的展开状态，或以受控状态确保新代次重新加载，不能遗留看似展开却没有当前页的节点。输入草稿不替代已提交query。覆盖问题使用有限issue摘要，不能把所有未纳管路径或主机绝对路径塞进响应。

controller沿用单调bigint sourceRequestEpoch签发代次、read/active/retries。root沿用catalog.source，selection沿用catalog.source-selection；每个文件/scope/aggregate节点使用独立`catalog.source-node.${nodeId}` RequestScope，共享既有pending/failure/retry机制。一个节点的请求不退休另一个节点。retireSource及关闭/查询/上下文变化必须覆盖整个动态命名空间，摘要/诊断按本节点准确展示；重试从操作入口重新获取当前代次与资格，不能借旧read闭包跳过admission。

每次根或file展开在一个read调用内部顺序自动读取全部metadata页，校验每页catalogId/identity/total一致、query/context/generation仍新鲜、父子类型关系、ID不重复、cursor不循环且有进展，并在有界总量内结束；完成后一次提交完整metadata。不能在dispatch后立刻读getState假设已采用再发下一页。若中途失败，不把已抓的前缀标为完整；局部失败支持重新读取，其他分支保持。变量只在各scope内人工加载更多，合并时复核cursor/父节点/目录。折叠的文件夹、文件和scope不创建其隐藏后代DOM；目录元数据可以完整保存，变量按需读取。

## 验收与部署

共享后端封套fixture贯穿provider/runtime/service→真实UI client→真实App。重点fixture覆盖：main超过100个变量且safe在旧第二页、第三个无变量文件、空函数、同名文件/函数、头文件、未纳管AST文件显式partial、metadata多页自动加载、scope独立变量分页、scope/域cursor错用、两个分支并发和各自失败重试、取消/查询/同epoch身份变化/旧ACK、已有工作台功能。使用真实离线C fixture验证AST函数关联，不能以仅mock函数名证明归属。

实现者跑受影响adapter/provider/runtime/service Python、全UI、两个typecheck、lint/build/verify:dist，并对当前21单元工程做一次只读tree+testtime路径核对；无用户工程写入或硬件。主代理在冻结CodeHead干净独立树审完整base→head差异、精选集成及资产一致性；独立审查者只读完整差异，作者不自审。报告准确区分执行者和离线/fixture证据。所有临时文件在D:\codex-tmp\st1019下独占根，TEMP/TMP/TMPDIR同绑，保留必要日志/最小失败证据后清理；任何拒绝目标不重试或绕过。

软件接受后主代理核对旧服务运维卡/进程/监听/源码，正常停止，再从最终产品干净树以同project/data/session公开open更新8765，记录源码、manifest、版本和OS监听。公开入口交接不作为真实浏览器PASS，不读取token/cookie或使用认证HTTP探测。
