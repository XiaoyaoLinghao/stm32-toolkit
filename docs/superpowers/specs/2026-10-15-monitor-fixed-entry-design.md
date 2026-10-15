# Monitor 固定地址与会话恢复规范（已批准）

切片：MONITOR-ENTRY-01。规范 owner：主对话代理。用户于 2026-10-15 明确批准本规范和实施计划，授权开始本地实现。

Accepted base：`224d5ea416971b1ba401147a4a2b4bf99a3cb8de`（用户批准的 UI01 最终本地提交；产品 CodeHead 为 `67f0ec4fbc375ed60e1f857b4cae248bf73d1589`）。UI01 代码与可运行检查已验收，浏览器/视觉证据仍待主代理在获准环境补验；本入口规范与计划已批准。

## 用户行为

1. 用户运行 `stm32-monitor open --project <工程> --data-root <数据目录> --port 8765`。服务仅绑定 `127.0.0.1:8765`，启动器自动打开首次认证链接，终端显示可收藏的 `http://127.0.0.1:8765/`。认证完成后地址栏移除 token。
2. 服务仍在运行、同一浏览器会话有效时，关闭标签页后打开该书签，直接进入中文工作台，无需复制 token。
3. 停止服务后使用相同命令重启，启动器向默认/选定浏览器交付新的认证链接；该浏览器配置成功加载并完成 bootstrap 后恢复使用，书签地址不变。不同工程可选择不同端口同时运行。
4. 地址无效、会话丢失、端口占用时，提供明确的中文提示或既有 CLI 错误，不静默改端口或绕过会话校验。用户为每个工程配置独立端口；普通根地址标识该端口当前服务，不携带持久工程身份。

非目标：取消认证、后台常驻管理器、从 runtime 文件恢复原始 token、已有进程的 IPC/reopen 命令、浏览器关闭后的持久会话保证、自动抢占端口/探针、改变采样与历史导出语义。

## 冻结契约

### 监听与 CLI

- `MonitorConfig` 增加末尾字段 `port: int = 0`；0 表示既有 OS 动态分配，1..65535 表示指定端口。拒绝布尔值、非整数和越界值，按既有模型 `ValueError` 规则处理。
- `serve` 与 `open` 增加可选 `--port`，显式输入仅接受十进制整数 1..65535；省略则模型为 0。非法 CLI 参数由 argparse 拒绝，退出码 2。端口占用保留既有 `MONITOR_INPUT_INVALID`、退出码 1 与脱敏错误行为，不新增机器错误码。
- `MonitorService` 增加 keyword-only `port=0`。runtime 将唯一配置值传给 service factory，测试注入工厂适配该参数；不得引入另一份端口配置。
- 仅绑定 IPv4 `127.0.0.1`，继续验证实际监听地址；指定端口失败时清理已创建资源并返回失败，不回退随机端口。runtime 锁、记录和停止清理仍由原 owner 管理。
- `open` 成功后打印一行 token-free 的 `endpoint.url + '/'`；不新增带 token 的 stdout/stderr。`serve --json` 字段、Bearer 客户端与 endpoint 数据模型保持兼容。
- 第二个 `open` 仍由现有工作区锁拒绝，不宣称它可以重新打开已有服务。

### 会话 cookie

- HTTP bootstrap 仍是唯一创建浏览器认证会话的入口；随机 token 的生成、校验和失效语义不变，不持久化原始 token。
- 服务读写的 cookie 名统一为 `stm32_monitor_session_<实际监听端口>`，命名计算只有一个来源。只读取该名称，不接受旧固定名称作为回退。
- 保留 HttpOnly、SameSite=Strict、`Path=/api/v1`、浏览器会话 cookie 的现有属性，不新增 localStorage/sessionStorage 或 Max-Age/Expires。
- 端口后缀用于防止正常多服务相互覆盖 cookie，不宣称 cookie 按端口隔离。同一端口重启后旧 token 无效，自动 bootstrap 覆盖该 cookie。

### 前端入口

入口分类必须在任何 `history.replaceState` 之前保存浏览器序列化的 `location.href` 与 origin/pathname/search/hash；分类结果仅存在本次启动的局部变量。普通入口要求保存的 href 精确等于 `origin + '/'`；不得仅凭 search/hash 为空推断没有分隔符，因为 `/?`、`/#` 的这两个属性也可能为空。合法 fragment 分支要求 `#` 前的序列化部分精确等于 `origin + '/'`，再校验 fragment 内容。

| 输入 | 行为 |
|---|---|
| 精确的普通根地址，href 不含 query/fragment 分隔符 | 以 `credentials: same-origin` 请求一次 `GET /api/v1/status`；使用既有 operation `monitor.status` 与 `monitorStatusGuard` 验证成功后，返回 `{authenticated: true}` 成功结果并按原 main 路径挂载 App |
| 精确 `/`，无 query，合法且仅一个 token fragment | 立即清除地址敏感部分，执行既有 Bearer bootstrap；失败不得退回 cookie |
| 其他 path/query/fragment，包括 `/?`、`/#`、空 token、重复或未知字段 | 清除敏感部分后，显示既有无效链接错误；不请求 bootstrap/status，不降级接受 cookie |

- 普通入口的 HTTP 401/403 使用前端展示代码 `MONITOR_SESSION_EXPIRED`（不新增后端/API 错误码）；其他非 2xx 或有效失败 envelope 使用 `MONITOR_BOOTSTRAP_SERVICE_FAILED`；网络失败使用 `MONITOR_BOOTSTRAP_REQUEST_FAILED`；2xx 响应 envelope/schema 无效使用 `MONITOR_BOOTSTRAP_RESPONSE_INVALID`。仅 HTTP 成功且 typed status 合法才认证成功，不把失败当作认证成功。
- 会话失效的中文说明为：当前会话已失效；如果服务仍在运行，先在启动终端按 Ctrl+C 停止，再用相同 `open ... --port ...` 命令重新启动并自动认证。该提示不得声称当前启动器具备 reopen 能力。
- 复用成功后 App 自身的初始 status 请求继续由原 controller 发起；入口校验不另建 controller/WS，不缓存身份或向 App 注入第二份状态。
- Host、Origin、Fetch Metadata、loopback peer、HTTP/WS 认证校验均保持既有实现；本规范不以纯本机访问为由放宽它们。

## 状态与依赖方向

端口：CLI → MonitorConfig → runtime → MonitorService → 实际 endpoint。cookie 名由服务的实际 endpoint 推导；URL 展示也使用该 endpoint。认证状态只由服务校验；前端仅决定启动成功或中文启动错误。运行状态继续归原 controller/reducer 所有。

## 文件与责任

预计产品范围：Monitor `cli.py`、`models.py`、`runtime.py`、`service.py`；UI `bootstrap.ts`、必要的集中中文词条；对应已有测试、生成 ui_dist 与用户指南。auth.py、API schema、controller/reducer、协议版本、依赖/CI/发布脚本不在范围；若实现发现需要改变其中行为，退回主代理设计，不自行扩大。

批准后由一个 `gpt-6-sol/max` 实现 owner 在新隔离树实现；主对话代理独立审查 accepted-base 到 final-head 全部差异。无 push、PR mutation、merge、tag/release、close 或远端删除授权。

## 已知使用边界

书签恢复要求服务仍在运行且同一浏览器配置内的有效会话 cookie 尚在。启动器成功交付链接不代表页面已加载或认证成功；只有完成 bootstrap 的浏览器配置可以复用该会话，其他浏览器/配置不会同步。关闭整个浏览器是否保留会话取决于浏览器；清除 cookie 后需要按提示停止并重新 open。本切片不承诺无需启动服务就能访问网页。

若用户把原属于工程 A 的端口重新用于工程 B，并在同一浏览器主动认证 B，原普通书签将打开 B。这符合“端口当前服务”的定义，不能宣称裸根地址具有工程身份绑定。指南应要求固定端口按工程分配，并通过既有工作台顶栏确认当前工程；本切片不新增持久端口注册表或带工程身份的书签协议。

依据：已核对 v1.0.1 与 UI01 CodeHead 的 CLI/config/service/auth/bootstrap 源码。cookie 不按端口隔离，参见 [RFC 6265 §8.5](https://www.rfc-editor.org/rfc/rfc6265.html#section-8.5)。
