# Monitor 源码变量目录：软件验收与本机部署

## 结论和身份

**ACCEPTED**，范围为本切片软件及本机服务更新。浏览器、实际认证 HTTP 和新版实机采样仍按用户要求 DEFERRED；本结论不构成物理 PASS 或新发布。

- Accepted base：`1c320d9dc102ca11a280b97e210517ac5a852b63`。
- 产品、测试与发布资产 CodeHead：`423dc766e60233e4e79bd1ed5306e6631c1d3daa`。
- 实现报告 head：`983540580f9e70f04e9e4770b9a16858fc4cd476`，相对产品 head 仅修改[实现报告](implementation-report.md)。
- 分支：`codex/monitor-source-catalog`；唯一实现者 `source_catalog_impl`（gpt-6-sol/max），独立只读审查者 `source_catalog_review`（同模型与努力），主代理负责规格、集成审查、验收和部署。实现者未接受自己的差异。
- 精确产品审查树：`D:\codex-tmp\sc1019\review`，detached CodeHead、tracked/untracked 状态为空，完整 accepted-base 到 CodeHead 的 `git diff --check` 通过。原用户工作树未用于实施或验证。

## 已完成的场景

| 场景 | 已连接的行为与证据边界 |
| --- | --- |
| 无探针查看源码变量 | 真实前端客户端与 App 自动加载共享后端封套；按文件、函数/作用域收纳，支持名称/文件/函数查询、分页、计数和明确覆盖率。旧固件变量和寄存器入口保留。 |
| 识别变量与采样资格 | 有效编译范围内的全局、文件静态、静态局部、自动局部和参数可见；GCC 预处理保留实际条件分支，Clang 解析声明，DWARF 与原 lookup/读范围共同核对加入资格。不能采样的项给出具体原因。 |
| 展开与加入 | 结构体/数组按需有界展开，深度和数量截断明确；选择经后端重新核对及前端当前上下文/草稿门禁后进入原草稿，不自动保存。旧请求不能重开已离开的操作面板。 |
| 探针反馈与工作台回归 | 已接受的探针反馈修复在本地合入；仅有效且经 reducer 采用的本次 ACK 显示成功并收起抽屉。未知/失败仍就地提示。数值在波形上方、按需显示波形、分组、历史和 CSV 路径保留并通过受影响回归。用户实际 HTTP ACK 尚未观察。 |

## 完整差异审查和修正

首次完整候选 `26e6b06ecafdc5dcff7488a04ab59df824ef40fb` 的判定为 REVISION_REQUIRED。部分结果导航丢失、深度限制原因、锁等待期限、重复成员错误提示、取消等待者留下 inflight、匿名/重名成员 ID 冲突，以及父进程已退出时的后代清理均在同一分支修正。新增真实 App 路径测试还复现并修正了同一渲染前连续搜索的代次竞态。

主代理复核完整范围，并在最终精确产品树重读 R1 后端/原生帮助文件/UI/测试及规格变化。独立审查者复用首次完整审查中未变的字节、复核所有 R1 差异与最终完整范围，结论 **NO BLOCKERS**；报告独立通过只读检查。原生 Windows Job 只归源码适配器所有，先挂接再恢复线程，退出/取消回收本次子树；关闭失败保留所有权并封闭适配器。未改变通用 process.py、旧 Watch 语法、认证、采样授权、依赖或版本。

## 验证归属

| 所有者 | 对最终相同产品字节实际执行的检查 | 结果与留证 |
| --- | --- | --- |
| 实现者 | 受影响 Python 六文件、全 UI、两个 typecheck、lint、build、verify:dist | 266 Python、57 文件/475 UI 通过；其余 exit 0，7 资产逐字节一致。日志 `D:\codex-tmp\sc1019\revision-check`；详见实现报告。 |
| 实现者 | 当前工程只读 provider 核对，无 binding | 21/21 C 单元完整、0 issue；testtime C/头文件可见且 probe_required，gpio 局部/参数 frame_required。这是离线证据，无用户固件构建/烧录或物理访问。 |
| 主代理 | 精确 CodeHead 的 11 个关键 UI 文件、静态资产测试、重新构建比较 | 72 UI、29 静态测试通过，7 资产逐字节一致；`D:\codex-tmp\sc1019\review-check-r2` 保存 code-head、argv、output 和 exit。 |
| 主代理 | source provider、service、adapter、DWARF declarations 与同 epoch 绑定变化的 runtime 集成 | 113 通过；`D:\codex-tmp\sc1019\review-source-check-r2` 保存相同四类记录。 |
| 独立审查者 | accepted base→最终 CodeHead 的完整差异、干净树、diff check、最终报告 | NO BLOCKERS；只读，没有将他人的测试归为自己执行。 |

Python 检查只有既有 cookie API deprecation warning。旧候选上的通过结果没有充作最终 CodeHead 的测试证据。真实浏览器、关闭重开和实际硬件/采样由主代理在用户恢复相应验证后另行执行，本轮没有把 fixture、AST、synthetic binding 或历史样本重命名为物理 PASS。

## 本机服务更新

软件接受后，主代理核对旧 PID17680 的监听、创建时间、命令、源码与 manifest，再通过原 exec87113 正常 Ctrl+C 停止；确认进程消失、8765 空闲。随后从精确干净产品树通过公开 `python -B -u -m stm32_monitor open` 更新，沿用 `D:\codex-tmp\md1016\p`、`D:\codex-tmp\md1016\data` 和 `monitor-demo-20261016`，端口8765。

公开 open 返回 `http://127.0.0.1:8765/`。OS 核对新监听为127.0.0.1:8765、PID10792/parent3528、创建时间2026-10-19T03:46:27.2430070Z；exec33017。源码为上述 CodeHead，manifest SHA256 为 `F1CD6A2E8D6783F788E5C96933F6E393524AEF4837622DC5A984C180CF663DBE`。运维卡为 `D:\codex-tmp\sc1019\service.json`。版本保持1.1.2；公开入口的浏览器交接不等于已观察认证成功或真实页面。

## 保留项与权限边界

实现者的 impl-check/revision-check、主代理初轮及最终轮 review 临时目录清理均被自动策略在执行前以 `blocked by policy` 拒绝，未删除、未重试或绕过。最终主审的7个精确绝对目标已核对包含关系及无 reparse，清单和拒绝记录分别为 `D:\codex-tmp\sc1019\review-cleanup-plan-r2.json`、`review-cleanup-denied-r2.json`；日志、测试源码、共享 fixture、用户数据均保留。清理受限不改变产品字节或测试结论。

所有提交和集成为本地操作，无 push、PR mutation、远程 merge、tag、release、安装、用户固件覆盖或新硬件操作。
