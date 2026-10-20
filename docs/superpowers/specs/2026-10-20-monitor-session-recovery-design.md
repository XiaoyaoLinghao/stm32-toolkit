# Monitor 会话恢复与访问错误分类

切片 ENTRY02，accepted full base `095a81e48e5e0cf698b23da12cd02dbe71a3f9a1`。用户报告固定8765入口反复提示失效；既有连续修复授权覆盖本地实现、测试、独立审查与服务更新，不再次索取审批。主代理负责规范、集成和验收，单一gpt-6-sol/max实现者负责产品与测试，独立gpt-6-sol/max审查者不得实现或自批。无远端、安装、硬件或固件动作；浏览器与live authenticated HTTP验证继续暂缓。

## 问题与场景

ENTRY01只固定端口并复用有效cookie：每次服务重启生成新bearer，旧cookie失效；认证链接交付系统默认浏览器，其他配置不共享cookie。原规范明确排除已有服务reopen，旧提示要求Ctrl+C再open。另一个已证实产品缺陷是plain-root启动把401与403都映射为会话失效；403也可能是Host/Origin/peer/Fetch Metadata拒绝，不能归因为过期。端口监听不能证明浏览器已认证。

1. 同一浏览器已有有效会话时，固定短地址直接进入工作台，保留ENTRY01严格入口语法。
2. 原`open`仍运行且处于交互终端时，用户按Enter再次把认证页面交付系统默认浏览器，无需停止服务、复制token、重新绑定探针或重放写操作。仅调用浏览器启动函数成功不表示页面已完成认证。
3. 原始plain-root的401显示会话不可用说明与“重新检查会话”。同一浏览器完成认证后重查typed status，成功才挂载App且最多一次；多次点击和迟到结果不能重复挂载。403显示独立的访问拒绝文案，不指示token过期或自动放宽策略。
4. 非法入口或被拒绝的fragment，即使地址已清除，也不能通过重试降级为cookie登录。非TTY、标准输入不可用、服务结束和Ctrl+C不挂起新的输入线程或阻碍原关闭清理。

## 冻结边界

本切片选择原owner进程中的终端操作，**不增加独立CLI reopen/IPC、持久grant、公开token mint或新的信任根**。Enter由持有endpoint凭据的原`open`进程处理，复用既有webbrowser交付；不修改bearer生命周期、cookie、bootstrap API、Host/Origin/Fetch Metadata/loopback保护或root授权语义。失去cookie的无凭据页面仍不能自行登录。不新增第二份认证/运行状态或持久保存真实凭据。

终端监听只在真实可读TTY启用；采用有界、可取消的非阻塞读取，不用无法取消的readline线程。监听任务归`open`生命周期管理，runtime关闭/异常/取消必须结束任务并释放reader，不影响现有资源清理。回车只触发浏览器交付，不停止runtime，不修改采样/分组，不生成新服务或替换endpoint。不处理标准输入中其他命令为授权。重复回车不产生并发启动；失败可再次按Enter，不把浏览器拒绝交付当认证成功。

stdout保持初始一行无token短URL；交互说明与交付结果仅在stderr使用固定安全文本，绝不输出真实token、access URL、cookie、异常原文或endpoint repr。非TTY保留原脚本行为，不增加读stdin或额外stdout。不宣称第二个`open`能唤醒已有服务。

前端只有服务typed status验证或原bootstrap成功能启动App。401展示代码保持`MONITOR_SESSION_EXPIRED`；403使用新的前端展示代码`MONITOR_ACCESS_REJECTED`，后端wire错误不变。固定说明解释默认浏览器/配置边界、原终端Enter、安全重查以及非交互启动需由启动方重新交付。不得继续推荐停止服务作为常规恢复操作。只有原始精确plain-root的会话失败允许cookie重查；资格由清除URL前保存的入口分类决定，不能在重试时重新分类已清除的fragment。重查一次在途，成功挂载一次，失败仍可重查；不会启动App/controller/WebSocket或自动重放mutation直至认证通过。

暂按系统默认浏览器场景实施；用户的浏览器目标问题已异步提出。Codex内置浏览器若未获得该profile凭据，本切片不能授权它，不使用宿主私有接口或旁路网络访问；这一边界必须写入交付。不承诺跨浏览器共享、关闭整个浏览器后保留会话、服务重启后旧cookie继续有效。

## 范围与验收

实现范围为Monitor cli.py及至多一个小终端适配helper，UI bootstrap/main/集中中文词条与必要启动提示样式、相应CLI/bootstrap/main测试、现有Playwright cookie名称断言及文档、确定性ui_dist。一个实现owner，不改runtime/service/auth、controller、采样、CSV、源码目录、依赖/lockfiles或发布版本；发现需改这些边界先返回主代理。当前源码53/53与唯一已知快照头文件warning保持不变。

必须RED→GREEN证明401/403分类、plain-root多次401→有效status恢复/单次挂载、并发点击、invalid/rejected fragment无fallback；CLI证明TTY Enter交付、同endpoint/runtime不重启、无额外stdout或凭据输出、交付失败可重试、非TTY不读stdin、关闭/取消不挂起。运行受影响Python CLI/auth/service与UI bootstrap/main回归、typecheck、lint、build、dist校验；独立冻结head复跑适用检查并完整base→FinalHead审查。Playwright真实关闭重开/重启/跨profile验证仍DEFERRED，不能借其他工具访问同一受阻页面补证。

验收后才正常Ctrl+C停当前owned exec18912，核实PID27460及workers/lease/8765释放，用相同工程/data/session和新clean source publicopen重启，记录创建时间、PID、代码/报告head与固定入口。源码工程、ELF与脏主目录不变。临时文件均在ma1020；主负责清理，保留最小失败证据，不重试已有策略拒绝的mp/mr清理目标。
