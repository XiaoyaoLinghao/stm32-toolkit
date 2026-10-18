# Monitor 工作台重构验收与部署

2026-10-18，结论：**ACCEPTED**。当前用户已批准设计、实施、测试、独立审查和更新8765；真实浏览器验证继续暂缓。没有远端写入、安装、固件或新增板卡操作。

## 身份与所有权

- 模块/阶段：MONITOR-WORKBENCH-REFACTOR，软件切片接受及本机部署完成。
- Accepted base：`ab274cf8ecde1bfd352419eb49140961818a43ac`。
- 接受的产品 CodeHead：`8649c494721e8cb631c84855a204dc271e09df00`。
- 实现和报告最终头：`74fccde23fdfb9376e335f42879102792557b808`；该头相对CodeHead只修改实现报告。
- 分支：`codex/monitor-workbench-refactor`；无PR，无本轮远端授权，无所有权例外。
- 主代理拥有规范、计划、整合、完整差异审查、验收和部署；workbench_impl（gpt-6-sol/max）独占产品与实现测试；workbench_review（gpt-6-sol/max）独立只读审查，未修改文件或运行测试。
- 运行/主代理复测树：`D:\codex-tmp\mw1018\review`，精确CodeHead、tracked/untracked状态干净。原始`D:\workspace\stm32-toolkit`的无关改动未被整合或删除。

规范、计划及批准参考图位于`docs/superpowers/`；[实现报告](implementation-report.md)记录命令、完整失败分类和CodeHead之前的实现证据。本记录不包含自己的最终提交SHA。

## 接受的用户场景

1. 中文浅色工作台采用52px顶栏、28px底栏、默认约290px分组目录和弹性波形主区。采样/缩放集中，数值区按条目数分配空间并可收起；设备、组编辑和诊断使用覆盖抽屉。窄屏目录有内部关闭入口。
2. 目录添加对象仍走原reducer，并打开组编辑；普通关闭、收起及切页保留组草稿、导入预览、查询和导出未提交范围。导航、写入重试和导出确认保持焦点、最上层Escape/Tab及原操作身份；失败通过常驻入口恢复。
3. 原采样开始/暂停/继续/停止、真实来源分组目录、最多8曲线、缩放、组JSON导入导出、历史查询分页和服务端CSV/JSONL制品核验下载保留。未连接的主动作打开设备选择，合法Stop不被隐藏。运行来源与新鲜度仍按exact run/group/revision，不能用新草稿重标旧样本。

controller/state/API/chart数学、Python后端、schemas、依赖/锁文件和版本号未改变。原型的模拟状态和CSV实现没有进入生产路径。

## 完整差异审查与R1

主代理和独立审查者均核对了完整accepted-base到候选的差异：第一轮覆盖全部33个变化路径；R1再核对所有新增/变化路径及完整最终路径清单，包含StatusStrip、报告和重建dist。生成物通过字节一致性与静态资源测试核对，不把摘要或局部补丁代替完整差异。

第一轮两个PRODUCT展示问题返回同一实现者并在一轮R1内解决：

- `ui/src/styles.css`的固定数值区在390px外壳高度下让图表host归零，向上弹出的曲线管理还会被主区裁切。现用84–208px的有界数值高度，390px时主区扣边框后图表host约88px；弹层向下展开并在剩余数值区内滚动。普通桌面108/180/208px预算保留。这是静态CSS几何核对，不是浏览器排版PASS。
- `ui/src/app.tsx`与`components/StatusStrip.tsx`原底栏缺少来源且窄屏会隐藏部分指标。现底栏显示exact runtime来源、新鲜度和简短指标，可聚焦并横向滚动；诊断抽屉提供完整采样率、延迟、原始纳秒、采集时间和四类丢弃计数。

报告范围句另分类为REPORT并已修正；不据此撤销正确的产品证据。独立复审确认无剩余非deferred产品或报告问题。主代理据最终代码、证据和复审作出ACCEPTED，没有主代理代写产品代码。

## 软件验证

实现者在`D:\codex-tmp\mw1018\impl-check`保存每次argv、stdout/stderr和exit；详见实现报告。

| 层级/责任人 | 结果与适用范围 |
| --- | --- |
| 实现者全量UI unit/a11y | 51文件、438测试通过；默认高并发时出现5秒超时，限制为4 workers/15秒runner时限后通过，业务断言未放宽。原失败日志保留。 |
| 最终受影响检查/实现者 | 完整套件后的小范围焦点/标签变化、R1由相应聚焦回归覆盖；R1为9文件47项通过，另有App回归和最终歧义查询修正后App通过。未把旧438结果重标为最终所有字节的重跑。 |
| 最终构建门禁/实现者 | 两个typecheck、lint、build、verify:dist通过；dist七文件与重建逐字节一致。 |
| 精确最终CodeHead/主代理 | 7文件34项UI精选测试通过，覆盖workbench App、live来源/新鲜度、history、export、chart交互、sampling、a11y。 |
| 精确最终CodeHead/主代理 | `test_ui_dist.py`和`test_ui_assets.py`共29项通过，显式双源码PYTHONPATH、禁字节码、禁pytest缓存及独占basetemp。 |
| 差异/主代理 | `git diff --check`通过；运行树干净；最终报告delta仅文档。 |

主代理准确argv/完整日志/exit位于`D:\codex-tmp\mw1018\review-check\{ui,python}`；执行入口`D:\codex-tmp\mw1018\run-review.ps1`绑定完整CodeHead。UI使用2 workers/15秒、无cache，TEMP/TMP/TMPDIR和Python basetemp均在独占本轮根。没有重复发布矩阵或无关后端全量测试。

## 8765部署证据

部署前重新核对端口空闲、CodeHead和运行树干净；通过既有公开入口`python -B -u -m stm32_monitor open ... --port 8765`启动。包装`D:\codex-tmp\mw1018\start-monitor.ps1`只输出固定短地址，不读/回显token或认证接口。

- 入口：`http://127.0.0.1:8765/`；OS确认唯一监听`127.0.0.1:8765`。
- 实际运行版本：`1.1.2`；源码为上述接受的CodeHead。
- Python PID：`14464`；父进程：`9692`；创建UTC：`2026-10-18T14:02:06.0032410Z`；工具会话`26559`保持运行。
- project：`D:\codex-tmp\md1016\p`；data：`D:\codex-tmp\md1016\data`；session：`monitor-demo-20261016`。复用既有工程、组和历史，不覆盖旧F429证据或CSV。
- 打包静态资源七文件已记录路径、大小和SHA256；manifest SHA256为`4C2BCA26C9C7ED663622FC8CE7416E9627BFE61A2E55C31C7FE7556F09DCADEE`。
- 完整部署卡：`D:\codex-tmp\mw1018\service.json`；公开CLI成功输出与OS进程/监听已核对。

**DEFERRED**：真实浏览器渲染、关闭后重开/交互、浏览器e2e、新版UI硬件采样。启动可能进行正常系统浏览器交接，但本轮未读取或操作浏览器，未据此声称页面验证通过；旧F429物理证据不重标为新UI PASS。

## 产物与收尾

保留源码工作树、可复用node_modules、批准参考图、完整命令/测试日志、最小失败证据及部署卡。服务仍运行，其临时目录不清理。

实现者对`impl-check/focused1/{tmp,cache}`的清理被自动执行策略拒绝，未重试或绕过；其余run临时文件按同一拒绝边界保留。主代理分别核实`review-check/ui/{tmp,cache}`与`review-check/python/{tmp,pytest}`均在本轮根、无reparse祖先，随后一次原生PowerShell删除也被工具以`blocked by policy`拒绝；未重试或换工具。清理预检记录在`D:\codex-tmp\mw1018\cleanup-preflight.json`，主代理pytest临时目录108个后代条目保留。此辅助清理限制不影响已验证的产品与运行服务。
