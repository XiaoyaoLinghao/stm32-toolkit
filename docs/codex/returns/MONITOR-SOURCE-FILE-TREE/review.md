# Monitor 完整源文件目录树：软件验收与本机部署

## 结论与身份

**ACCEPTED**，范围为本切片软件和本机8765服务更新。真实浏览器、实际认证HTTP和新版实机验证依用户要求继续DEFERRED，不构成物理PASS或新发布。

- Accepted base：`3c4e2594bafc8d7ca2f1b00c1efe6683639cf05c`。
- 产品、测试与生成资产CodeHead：`41b5cc37f60d26da2ed323dd7b934fc980b3df61`。
- 实施报告head：`f6ba4cbb21e2b8ceb3577a95a46bbdccaaaaec87`，其父提交为CodeHead，后续只增加[实施报告](implementation-report.md)。
- 分支`codex/monitor-source-file-tree`；file_tree_impl（gpt-6-sol/max）唯一实现，file_tree_review_sol（显式gpt-6-sol/max通用只读角色）独立审查，主代理拥有设计、完整差异复核、验收与部署。合同预检者file_tree_review不计作最终产品审查。
- 精确审查及部署树`D:\codex-tmp\st1019\review`，detached CodeHead，tracked/untracked状态为空，完整base到CodeHead的diff check通过。原用户工作树未用于实施或验证。

## 场景与完整差异审查

根metadata从权威项目输入快照列出完整纳管源文件，按相对路径派生可折叠文件夹；包括无变量文件，不再由首个100变量反推文件列表。文件展开显示真实AST函数及文件级作用域，包括空函数；作用域展开再读取自己的变量页，原聚合成员展开和选择后加入草稿继续沿原链路工作。

新增source-tree公开路由与原source-variables的scopeId参数共享同一provider、目录身份和授权。文件/函数metadata自动取全后原子采用，变量每scope独立分页；查询覆盖文件、函数和变量。节点独立请求、错误和重试，旧上下文、查询、代次和迟到选择ACK均退休。保留数值优先、探针成功反馈、采样、分组、历史、CSV和固件变量/寄存器入口。

主代理复核完整43文件base→CodeHead差异，包括产品、测试、规格计划、SOP及生成资产；独立审查者只读同一完整范围并核对报告，结论**NO BLOCKERS**。独立审查未发现AST函数归属、跨文件词法scope投影、snapshot覆盖、metadata/变量分页、cursor绑定、请求退休、重试或选择ACK门禁的阻断问题。审查者没有运行测试，不冒领执行证据。

冻结前的集成核对已落实跨文件body-include真实函数身份、未纳管/孤儿声明显式partial、Unicode函数保留词法上下文、2048字符游标及中文长查询预算、昂贵查询离开事件循环。对应真实离线C fixture与公开分页回归包含在最终产品测试中。没有改变build.identity、通用process引擎、DWARF读取资格、认证/采样授权、依赖或版本。

## 验证归属与留证

| 执行者 | 最终相同产品字节上的检查 | 结果与证据根 |
| --- | --- | --- |
| 实现者 | 受影响adapter/provider/runtime/service Python、完整UI、两个typecheck、lint、build、verify:dist | 143 Python、57文件/474 UI通过；其余exit 0，7资产逐字节一致。完整命令和日志见实施报告及`D:\codex-tmp\st1019\impl-check`。 |
| 实现者 | 当前项目只读SourceCatalogProvider.tree，无binding | 21/21 C单元、184文件、0 issue；testtime命中`App/vs10_app.c`、`App/vs10_app.h`、`Tests/vs10_target.c`。本次首次索引实测36.544秒；无用户工程构建/写入或硬件调用。 |
| 主代理 | 精确CodeHead的12个源码/探针/数值/分组/live/history/错误/工作台UI文件 | 72通过，18.59秒；`D:\codex-tmp\st1019\review-check\ui`保存argv、output、exit及根code-head。 |
| 主代理 | provider、service、adapter、DWARF declarations及同epoch身份变化runtime节点（含新tree） | 119通过，40.29秒；`D:\codex-tmp\st1019\review-source-check`保存argv、output、exit、code-head。 |
| 主代理 | 静态资产测试、独立重建比较 | 29测试通过、7资产逐字节一致；`review-check\python`、`review-check\dist`保留命令和输出。 |
| 独立审查者 | 完整base→CodeHead差异、干净树、diff check及报告 | NO BLOCKERS；只读审查，无测试执行主张。 |

Python只有既有aiohttp cookie API deprecation warning。实现者初次全UI中的旧fixture适配失败已分类、修正并在最终474项全量通过，旧失败日志保留；旧候选不充作最终PASS。离线解析、service fixture、jsdom和无binding目录均不是浏览器认证或物理采样证明。首次导航仍等待有界完整源码索引，不采用快照先发、AST后补的双阶段生命周期。

## 8765更新

软件接受后，主代理核对旧服务卡、PID10792、创建时间、命令、loopback监听、源码及manifest均一致；通过原exec33017发送Ctrl+C正常停止，确认进程消失、端口空闲。随后由公开`python -B -u -m stm32_monitor open`在精确干净CodeHead树启动，沿用项目`D:\codex-tmp\md1016\p`、数据`D:\codex-tmp\md1016\data`、session `monitor-demo-20261016`和端口8765。

公开open返回`http://127.0.0.1:8765/`。OS复核新服务PID22740、parent18592、创建时间2026-10-19T06:04:18.5764500Z、exec27630，仅监听127.0.0.1:8765。manifest SHA256为`085AAC538E31239CD045D944A7D21C64F43978285E9098E6F12DBA14B705DF11`，版本保持1.1.2。运维卡`D:\codex-tmp\st1019\service.json`记录上述身份，旧服务核对/停止证据也保存在该任务根。

本次只核对OS与源码/资产，公开open的浏览器交接不构成浏览器PASS。没有读取认证token/cookie或调用实际服务认证HTTP；关闭重开和新版硬件采样由主代理在用户恢复相应验证后执行。

## 清理与权限边界

主代理7个新建测试临时目录已逐项核对绝对路径包含关系及无reparse，单次清理成功；清单/结果为`D:\codex-tmp\st1019\cleanup-review-plan.json`、`cleanup-review-result.json`，argv、日志、exit、code-head继续保留。服务树、运行中service-temp及私有依赖保留供当前运行使用。

实现者此前清理9个已盘点pytest临时目录的命令被自动策略在执行前以`blocked by policy`拒绝；未重试、未绕过、未删除，目录及必要失败证据保留。此前其他任务的拒绝目标也未触碰。清理受限不改变产品字节或通过结果。

本次所有提交和集成仅在本地，无push、PR mutation、远程merge、tag、release、安装、版本提升、用户固件覆盖或新硬件操作。
