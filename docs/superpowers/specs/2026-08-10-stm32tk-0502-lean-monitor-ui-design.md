# STM32TK-0502 精简 Monitor UI 设计

**状态：** Reviewed；fix round 1 已关闭独立审阅 finding

**模块：** `STM32TK-0502-MONITOR-UI-RELEASE`

**Accepted base：** `bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa`

**版本目标：** 统一发布 `0.5.0`

**规格所有者 / 验收者：** Codex

**实现与实现测试所有者：** Codex 子代理（本目标不与 OpenClaw 协作）

## 1. 目的与发布顺序

0502 在已合并的 0501 Monitor service 之上增加可离线运行、随 Python wheel
分发的核心 Web UI，并完成 launcher、Plugin、Skill、README 和 `0.5.0`
发布对齐。0502 保持 `stm32-toolkit-monitor/1` 的 route、envelope、request/response、
WebSocket event、历史、采样、存储和导出契约；唯一获准的 0501 后端兼容修正是第 7.3
节限定的 cookie/browser request-auth policy，修改仅限 `auth.py`、`service.py` 及其测试。

发布顺序是硬门禁：0502 被 Codex 验收并形成完整 `0.5.0` 证据前，不得开始任何
`0.6.0` host/target test 或 AI diagnostics 实现。旧 0.5–0.6 计划中超出本设计核心
范围的 Monitor 功能按第 15 节延期，不得以“顺手实现”、隐藏入口或实验 flag 进入
0502。

## 2. 已批准的核心结果

用户能从 Toolkit Plugin 显式打开一个本地 Monitor 页面，并在一个工作区内完成：

1. 查看 project、probe 和 firmware identity；
2. 列出探针并显式 connect、reconnect、release；
3. 搜索变量和寄存器 catalog，选择标量或由 descriptor 浅层派生的成员/数组元素；
4. 创建、编辑、重命名、删除、导入、导出纯用户监控组；
5. 以 100 ms–5 s interval start、pause、resume、stop；
6. 在 typed table 中查看全部选中项，在基本多序列 chart 中查看选定数值序列；
7. 在紧凑状态条中查看 actual rate、latency 和 drop totals；
8. 分页查看当前 Monitor session 的基本历史；
9. 通过现有 verified export API 导出 CSV 或 JSONL；
10. 明确识别 error、stale、view reset、event gap 和 lease conflict。

页面不自动连接探针、不自动开始采样、不创建默认组，也不猜测 probe、ELF、SVD、
target、address、workspace 或 firmware identity。

## 3. 设计约束

- 前端使用 Preact、strict TypeScript、Vite、提交的 `package-lock.json` 和模块化
  ECharts；不得从 `echarts` 聚合入口导入完整包。
- 浏览器运行时完全离线，不含 CDN、remote font、analytics、telemetry、service
  worker 或任何非同源请求。
- UI 和 API 由同一个 aiohttp process、同一个 `127.0.0.1` 随机端口提供。
- 每个实例继续使用 0501 的随机 32-byte token；token 只经 URL fragment 交给页面，
  bootstrap 后只使用 HttpOnly cookie。
- 0502 必须修正当前 cookie auth 对 every request 强制 exact Origin、导致标准同源 GET
  无法工作的缺陷；修正不得放宽 loopback、Host、Bearer、mutation Origin 或 CSRF gate。
- UI 不打开 PyOCD、不导入 probe backend、不管理其他进程；硬件访问仍只经 0501
  runtime 和 Probe Service。
- 所有持久数据仍由 0501 按 `workspaceId`/`sessionId` 写入 plugin data；前端不得向
  项目仓库、`localStorage`、`sessionStorage`、IndexedDB 或浏览器 Cache 写状态。
- 不提供 presets、业务命名组、示例命名组或静默恢复后自动 start。fresh workspace
  必须显示零组的 empty state。
- 单个 sample value 失败不停止同一 batch 中其他值的显示。

## 4. 总体架构

```text
explicit human launcher (`stm32-monitor open`)
  → MonitorRuntime + MonitorService on 127.0.0.1:<random-port>
      ├── GET /, /assets/*: committed wheel assets
      ├── /api/v1/*: existing authenticated REST
      └── /api/v1/live: existing authenticated WebSocket
  → Preact app: fragment bootstrap → exact API/live adapters → reducer
      → typed table / bounded ECharts / paged history / verified download
  → existing 0501 GroupStore / Sampler / HistoryStore / HistoryExporter
  → Probe Service (sole hardware owner)
```

静态资源层与第 7.3 节 auth compatibility 是唯二后端变化；`/api/v1` envelope、route、
body/query grammar 和 WebSocket event union 不变。前端不得成为第二个 model authority。

## 5. 仓库与组件边界

### 5.1 前端源文件

```text
tools/stm32-monitor/ui/
├── package.json / package-lock.json / tsconfig.json
├── vite.config.ts / vitest.config.ts / playwright.config.ts
├── src/main.tsx / app.tsx / styles.css
├── src/api/{contract,client,live}.ts
├── src/state/{model,reducer,selectors}.ts
├── src/catalog/shallow-selectors.ts
├── src/chart/{echarts,series,zoom}.ts
├── src/components/{IdentityBar,ProbePanel,GroupPanel,CatalogPanel}.tsx
├── src/components/{LiveTable,LiveChart,ChartZoomControls,HistoryPanel,ExportPanel}.tsx
├── src/components/{StatusStrip,NoticeRegion}.tsx
├── tests/                       Vitest/Testing Library/axe
└── e2e/                         Playwright + real aiohttp fake-runtime fixture
```

配置要求 exact direct versions、committed lockfile、strict/noEmit/
noUncheckedIndexedAccess、deterministic Vite manifest/no sourcemap、jsdom + v8 branch
coverage 和 Chromium/Firefox/WebKit。`main.tsx` 在 Preact mount 前完成 token
take/scrub/bootstrap；`app.tsx` 不 fetch，components 不解析 envelope，chart 不持有身份
或组状态。API/live adapters 只发 typed action；纯 reducer 忽略旧 revision/epoch/run。

### 5.2 Python 静态资源与服务边界

```text
tools/stm32-monitor/src/stm32_monitor/
├── ui_assets.py     importlib.resources allowlist, MIME, ETag, headers
├── auth.py          bounded browser cookie evidence policy from §7.3
├── service.py       static routes + request method/fetch metadata into auth
└── ui_dist/{index.html,.vite/manifest.json,assets/<content-hashed files>}
```

`ui_dist` 是受版本控制的发布产物。`npm run build` 必须在临时目录重建并与提交的
`ui_dist` 逐 byte 比较；不允许开发机残留或 build time 写入 wheel。Python wheel
构建不需要 Node，wheel 通过 explicit package-data 收录上述文件。

`ui_assets.py` 在 service start 时读取 package resources 并建立精确 allowlist；不把
用户 path 拼到 filesystem path，不 directory-list，不对 `/api/*` 做 SPA fallback。
`index.html` 和 manifest 不超过 256 KiB，单 asset 不超过 4 MiB，全部 UI assets
合计不超过 8 MiB。未知或 traversal asset 返回固定 404，不回显输入。
`tests/test_auth.py` 与 `tests/test_service.py` 必须覆盖第 7.3 节的完整 allow/deny matrix；
除此之外不得更改 0501 auth/public operation semantics。

### 5.3 Launcher、Plugin 和文档边界

- `tools/stm32-monitor/src/stm32_monitor/cli.py`：保留 machine command
  `serve --project ... --data-root ... --session-id ... --json`；新增独立 human command
  `open --project ... --data-root ... [--session-id ...]`。
- `bin/stm32-monitor.cmd`：只选择
  `${CLAUDE_PLUGIN_DATA}/runtime/0.5.0/Scripts/python.exe` 并转发参数；不得 fallback 到
  `python`、`py` 或 `uv`。
- `skills/stm32-monitor/SKILL.md`：薄 Skill。先获取当前 project context，说明 UI
  只观察且不会自动连接/采样，得到用户明确打开请求后才调用 human launcher。
- `bin/setup-stm32-env.ps1` 与 `skills/setup-stm32-env/SKILL.md`：Bootstrap/Repair
  在同一个 `0.5.0` managed runtime 中安装并验证精确版本的
  `stm32-toolkit[probe]` 和 `stm32-monitor`，验证 UI manifest 和静态资源可读。
- `.claude-plugin/plugin.json`、`README.md`、`README_zh-CN.md`：统一说明 0.5.0、八个
  release Skills、显式启动、零 presets、项目隔离和 0.6 延期项。

`requirements/follow-on-skills/stm32-monitor/SKILL.md` 是历史 requirement source，
不是可执行 release Skill；不得复制其中旧的 `localhost:8888`、direct `pyocd`、
named preset、自动安装或 AI snapshot 行为。

## 6. CLI 和浏览器启动契约

### 6.1 Machine `serve --json`

0501 command 的参数和 stdout contract 保持不变。它只启动 listener、输出一行包含
`endpoint.url`、`endpoint.accessUrl`、`monitorVersion` 的 JSON，然后等待关闭：

- 不调用 browser API；
- 不新增或接受 `--open-browser`；
- 不写 token、access URL 或 raw endpoint 到 runtime record、日志、项目或临时文件；
- `accessUrl` 中 fragment token 是对授权 machine caller 的一次性 stdout handoff，
  Toolkit 自身不记录 stdout；
- failure 继续返回 bounded sanitized JSON，不输出 traceback 或内部 path。

### 6.2 Human `open`

`open` 是唯一会打开浏览器的 command。它先完成 runtime start，再使用 Python 标准
browser handoff 打开一次 `endpoint.access_url`；不在 terminal 打印带 fragment 的
URL。未提供 `--session-id` 时生成一个满足现有 safe-session grammar 的随机
`monitor-<hex>`，只用于本次 runtime。browser handoff 失败则停止 owned runtime 并
返回 sanitized failure；成功后 command 前台等待，Ctrl-C 返回 130 并完成 cleanup。

测试 seam 注入 browser opener；`serve --json` 的单元测试必须证明 opener 调用次数
为零，`open` 必须证明恰好一次且发生在 successful start 后。不得用隐藏 detached
process、shell history、临时 token file 或 URL clipboard 作为启动机制。

## 7. Fragment token bootstrap 和 HTTP 安全

### 7.1 Bootstrap 顺序

1. 浏览器请求 `http://127.0.0.1:<port>/#token=<64 lowercase hex>`；fragment 不进入
   HTTP request。
2. `main.tsx` 在加载 Preact、建立 state 或发出其他 request 前同步读取并验证 fragment。
3. 它立即调用 `history.replaceState(null, "", "/")` 清除地址栏和当前 history entry。
4. 它用局部变量向 `POST /api/v1/auth/bootstrap` 发送
   `Authorization: Bearer <token>` 和 exact same-origin `Origin`，body 为空。
5. server 设置现有 `HttpOnly; SameSite=Strict; Path=/api/v1` cookie；UI 在 `finally`
   中把局部 token 引用设为 `null`，之后才 mount application。
6. 后续 REST 和 WebSocket 只用 same-origin cookie；应用 state、props、DOM、URL、
   console、errors 和 persisted browser storage 中永远没有 token。

缺失、重复、非法 fragment 或 bootstrap failure 只渲染无 secret 的启动错误，且不
尝试猜 token、从 query 读取 token 或接受 localStorage token。

### 7.2 静态路由与 headers

静态 GET 在没有 token 时可读取，但必须先验证 IPv4 loopback peer、exact
`Host: 127.0.0.1:<bound-port>`、header budget 和可选 Origin；这阻止 DNS rebinding，
不放宽 `/api/v1` 的认证。每个 HTML/asset response 至少包含：

```text
Content-Security-Policy: default-src 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'none'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self' ws://127.0.0.1:<bound-port>; worker-src 'none'; child-src 'none'; media-src 'none'
Referrer-Policy: no-referrer
X-Content-Type-Options: nosniff
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Resource-Policy: same-origin
Permissions-Policy: camera=(), microphone=(), geolocation=(), usb=(), serial=(), payment=()
```

CSP 按实际随机端口生成，不允许 `*`、`unsafe-inline`、`unsafe-eval`、remote origin、
`data:` script 或 `blob:` worker。`index.html` 使用 `Cache-Control: no-store`；
content-hashed assets 使用 `public, max-age=31536000, immutable` 和 exact MIME/ETag。
生产 build 不含 source maps。

### 7.3 有界 browser cookie auth 兼容修正

当前 `auth.py` 的 `cookie_ok` 强制 `origin == self.origin`，但标准同源 `fetch()` GET
通常没有 Origin 且 JavaScript 不能设置该 forbidden header。0502 明确授权下列 transport
auth 修正；cookie 属性仍为 `HttpOnly; SameSite=Strict; Path=/api/v1`：

| Credential/request | 必须满足 | 必须拒绝 |
|---|---|---|
| 所有 API/WS | peer=`127.0.0.1`、Host=`127.0.0.1:<bound-port>`、header budget；有 Origin 时必须 exact origin；有 `Sec-Fetch-Site` 时必须 `same-origin` | wrong peer/Host/Origin；`cross-site`、`same-site`、`none` fetch site |
| Bearer（含 bootstrap） | exact bearer 且 Origin 必须 exact；bootstrap 不接受 cookie | missing/wrong Origin，即使 token 正确 |
| Cookie safe HTTP | method 仅 GET/HEAD；exact Origin，或 Origin 缺失且 `Sec-Fetch-Site: same-origin` | Origin 与 fetch metadata 都缺失；任何 non-same-origin metadata |
| Cookie WebSocket | GET upgrade；exact Origin，或 Origin 缺失且 `Sec-Fetch-Site: same-origin` | 同 safe HTTP；client message policy 不变 |
| Cookie mutation | POST/PATCH/PUT/DELETE 必须 exact Origin；如果 fetch metadata 存在也必须 `same-origin` | 无 Origin，即使 `Sec-Fetch-Site: same-origin`；其他 method |

`service.py` 只把 normalized method、`Sec-Fetch-Site` 和 WS context 交给 auth decision；不信任
caller-supplied “safe” flag。测试必须分别证明无-Origin同源 GET/HEAD/WS cookie 可用，
mutation 无 Origin、Bearer 无 exact Origin、missing metadata、`Origin:null`、cross/same-site、
`none`、wrong Host/peer 全部 fail closed。该修正不改变 operation schema，也不允许 DNS
rebinding、CSRF、cookie bootstrap、token query 或 non-loopback client。

## 8. 现有 API 的精确 UI 映射

所有 REST response 继续使用
`protocol/toolkitVersion/monitorVersion/ok/operation/code/message/data/details` envelope。
非 `ok` response 必须按 `code` 进入错误状态，不用 HTTP status 或 message 文本猜状态。

| UI 动作 | 0501 route 和精确输入 | UI 使用的输出 |
|---|---|---|
| 初始身份/刷新 | `GET /api/v1/status`，无 body/query | project、firmware、probe、sampling 完整状态 |
| 探针列表 | `GET /api/v1/probes`，无 body/query | `probes[]` 的 probeId/vendor/product/boardName |
| 变量搜索 | `GET /api/v1/catalog/variables?query=&cursor=&limit=` | descriptor `items`、`nextCursor` |
| 寄存器搜索 | `GET /api/v1/catalog/registers?query=&cursor=&limit=` | descriptor `items`、`nextCursor` |
| 组列表 | `GET /api/v1/groups?cursor=&limit=16` | group page、nextCursor、revision |
| 创建组 | `POST /api/v1/groups`，`{name,description,intervalMs,items,authorized:true}` | authoritative WatchGroup |
| 编辑/重命名 | `PATCH /api/v1/groups/{groupId}`，`expectedRevision`、changed fields、`authorized:true` | new authoritative revision |
| 删除组 | `DELETE /api/v1/groups/{groupId}`，`{expectedRevision,authorized:true}` | deleted confirmation |
| 导入组 | `POST /api/v1/groups/import`，`{document:{schemaVersion:1,groups:[...]},authorized:true}` | imported authoritative groups |
| 连接 | `POST /api/v1/probe/connect`，仅 `{probeId}` | ObservationBinding |
| 重连 | `POST /api/v1/probe/reconnect`，严格无 body | new binding/epoch；仅 prior successful connect 后启用 |
| 释放 | `POST /api/v1/probe/release`，严格无 body | released confirmation |
| 开始 | `POST /api/v1/sampling/start`，`{groupId,expectedRevision}` | sampler result；随后以 state event 为准 |
| 暂停/恢复/停止 | 对应 `/api/v1/sampling/{pause,resume,stop}`，严格无 body | result；随后以 state event 为准 |
| 基本历史 | `GET /api/v1/history`，必需 `startNs/endNs`，可选 `limit/cursor/runId/groupId/selectorKind/selector` | HistoryPage batch slices |
| 创建证据导出 | `POST /api/v1/exports`，`{startNs,endNs,format:"csv"|"jsonl",authorized:true}` | verified ExportArtifact |
| 导出状态 | `GET /api/v1/exports/{exportId}` | verified metadata |
| 下载 | `GET /api/v1/exports/{exportId}/download`，无 query/Range | server-controlled filename/content |
| 实时流 | `GET /api/v1/live[?afterEventId=N]` WebSocket，client 不发消息 | hello/state/sample/heartbeat union |

Bodyless POST 不能发送 `{}`、`Content-Type` 或 caller identity。UI 从不发送
`workspaceId`、`sessionId`、project/data root、target、ELF、SVD、address、backend、
operation level、build pin 或 download path/filename。

### 8.1 组导出不新增后端 route

“用户 group export”由浏览器把已分页取得的 authoritative groups 转换为现有 import
schema：

```json
{"schemaVersion":1,"groups":[{"name":"...","description":"...","intervalMs":250,"items":[]}]}
```

它必须去掉 groupId、revision 和 timestamps，使用用户点击产生的 Blob download；导入
前展示 group 数、item 数和冲突说明，用户再次确认后才发送 `authorized:true`。这不是
sample/history JSON snapshot，也不得命名为 AI export。

## 9. Catalog 与复杂类型的精简规则

变量和寄存器只有在 probe connected 后可查询。搜索输入 NFC normalize、最多 128
字符、300 ms debounce；翻页使用 opaque cursor，query 或 binding identity 改变时丢弃
旧 cursor 和旧结果。default limit 100，UI 不请求超过 server maximum 256。

UI 只接受 0501 descriptor 的 public fields：

- variable：selector、typeName、kind、byteSize、signed、encoding、qualifiers、aliases、
  enumValues、elementCount、elementKind、memberNames；
- register：selector、sizeBits、access、readAction、reset metadata、fields、sampleable、
  requiresAccessAcknowledgement。

复杂变量只允许一跳派生：

- `memberNames` 中的 `m` 生成 `${selector}.${m}`；
- `elementCount=N` 中用户选择的 `i` 生成 `${selector}[${i}]`，要求 `0 <= i < N`；
- `N <= 256` 可列出全部 index；`N > 256` 使用 bounded index 输入，不 materialize
  全数组；
- 不递归猜 member type/offset，不从 byteSize 推断类型，不解析 pointer，不发 raw
  address，不修改 0501 catalog 或 sampling protocol；
- derived selector 最终仍作为普通 `WatchItem` 由现有 backend 验证。

不可 sample 的 register 禁用添加并解释 `readAction/access` 风险；需要 access
acknowledgement 的 register 在用户本次 add 操作中显示确认，不持久化全局豁免。

## 10. UI 状态、数据流与有界内存

### 10.1 Authoritative state

启动成功后先并行读取 status、probes 和全部 group pages；catalog 仅在连接后按需读取。
WebSocket 首个 hello/state 建立 `stateRevision`，之后：

- 小于当前 `stateRevision` 的 state 被忽略；
- sample 的 workspace/session/binding 与当前 status 不一致时拒绝显示并进入 stale；
- `bindingEpoch` 或 `runId` 改变时清空 live ring、插入 “view reset” notice，并开始新
  chart segment；不得把它表述成已证明的 MCU physical reset；
- `eventId` 连续记录；断线重连用最后 eventId 作为 `afterEventId`；
- state event 的 `gap:true` 插入显式 gap，清空不可证明连续的 chart segment并重新
  GET status；不插值、不补造 sample；
- heartbeat 35 秒未到达即显示 stale connection。WebSocket transport 按
  0.5/1/2/4/8 秒 capped backoff 自动重连，但绝不自动 reconnect/reacquire probe 或
  restart sampling。

### 10.2 Typed table

表格按 group item order 保留最多 256 行。每行显示 selector、kind、typeName、typed
value、rawHex、last captured time、trend 和 exact error code。`typedValue.value` 只有
finite number 才进入 chart；enum/string/object/array 仍在 table 以 bounded、escaped、
可展开一层的文本显示。未知 JSON shape 安全 stringify，不使用 `innerHTML`。

trend 只比较同一 binding/run 下相邻 numeric value；gap、error、reset 或 identity
change 后 trend 归零。单项 `ERROR` 只标记该行，其余行继续更新。

### 10.3 基本多序列 chart

用户可从 table 选择最多 8 个 numeric series。每 series 保留最近 600 个点；ECharts
仅注册 `LineChart`、`GridComponent`、`TooltipComponent`、`LegendComponent`、
`DatasetComponent`、`DataZoomComponent` 和 `CanvasRenderer`，不从聚合入口导入。sample ingress
由 animation frame 合并，最多每 100 ms 调用一次 `setOption`；gap 使用 null point
且 `connectNulls:false`。

0.5 保留当前 segment 的单范围 basic data zoom：鼠标滚轮/拖拽和触摸手势使用
ECharts inside/slider dataZoom；`ChartZoomControls` 提供可聚焦的放大、缩小、恢复全部按钮，
键盘 `+`、`-`、`0` 与按钮等价。缩放后更新可见范围文本，恢复操作始终可达并回到
0–100%；reducer 在 gap/reset/new run 时同步恢复。Vitest/Testing Library 验证
pointer/touch option、键盘和 reset state，axe 验证控件名称/聚焦，Playwright 验证实际缩放及
可恢复性。typed table 仍是无 canvas 依赖的等价可访问数据源。多范围、多 run overlay、
brush comparison、annotation/诊断 marker 和完整质量面板属于 0.6。

### 10.4 紧凑质量状态

StatusStrip 只显示最新 `actualRateHz`、`latencyNs` 和四类累计 drops：subscriber、
history、deadline、service。drop 增长时给一次非阻塞 notice。它不绘制质量趋势、
分布、per-stage dashboard 或 diagnostic timeline。

### 10.5 基本历史

用户提供 start/end 时间，选择可选 current group/run/selector filter，点击 Load 请求一
个 page。UI flatten `HistoryBatchSlice` 时保留 batch binding、startOrdinal 和 value
ordinal；Next 使用 server `nextCursor`，Previous 只使用内存中的已访问 cursor stack，
页面刷新不持久化。每次最多 10,000 values，不自动抓取全部历史，不跨 session，不做
两段历史比较。历史 chart 同样受 8×600 展示上限，原始 page 仍可在表格分页查看。

## 11. UX 和无障碍

- IdentityBar 始终显示 project name、target device、Git HEAD/dirty、buildId/ELF digest
  的短显示与完整可复制值；firmware 缺失时明确 stale/不可连接。
- ProbePanel 对 list/connect/reconnect/release 使用真实 button state；lease conflict
  不显示 steal/force 按钮。
- GroupPanel fresh state 文案明确“没有用户监控组”，不建议或预填业务组名。create、
  import、delete 和 access-risk register add 需要用户当次确认；普通字段编辑保存不做
  重复确认，但始终发送 `authorized:true` 作为本次点击的证明。
- Start 只有 connected、group revision 当前且 group 至少一个 item 时启用；interval
  输入的 `min=100`、`max=5000` 与服务端校验一致。
- 所有 controls 有 programmatic label；错误与状态不只靠颜色；notice 使用
  `aria-live=polite`，阻塞错误用 `role=alert`；dialog 打开后 focus 进入，关闭后返回
  trigger，Escape 可取消非提交状态。
- 完整键盘流程覆盖 probe、catalog、group editor、sampling、history 和 export。
  chart 缩放控件和恢复全部也必须可键盘操作；visible focus contrast >= 3:1，
  文本 contrast >= 4.5:1，页面 200% zoom 不丢操作；
  `prefers-reduced-motion` 时禁用非必要动画。
- 目标 viewport 为 1280×720 及以上桌面；1024×768 允许 panels 纵向堆叠。移动端
  专用布局、主题编辑和国际化不属于 0502。

## 12. 错误和不连续状态

| 状态 | 权威信号 | UI 行为 |
|---|---|---|
| item error | SampleValue `status:"ERROR"` + exact `code` | 行级 error；其他值继续 |
| request error | non-ok protocol envelope | 对应 panel 保留输入，显示 code/message，不展示内部 details 为事实 |
| stale firmware/provenance | `MONITOR_FIRMWARE_CHANGED`、`MONITOR_PROVENANCE_CHANGED`、firmware null 或 sample binding mismatch | 阻塞 start，清 catalog/live buffer，要求用户刷新身份后显式 reconnect |
| view reset | bindingEpoch/runId/authoritative binding 改变 | 清 live continuity，显示新 segment；不声称 MCU reset |
| event gap | state event `gap:true` 或 server-reported subscriber drops | chart 插 gap、刷新 status、显示丢失事实，不回填 |
| lease conflict | `MONITOR_PROBE_BUSY`、`PROBE_LEASE_LOST` 或 `PAUSED_BLOCKED` + blockedCode | 显示 exact reason，禁止 auto-resume/steal；只提供显式 release/reconnect |
| transport stale | heartbeat 超过 35 秒或 socket closed | 保留 last value 并标 stale；仅重连 WebSocket，不触碰 probe |

删除 group 若命中 revision conflict，重新抓取 groups 并要求用户重做决定；不得以 last
write wins 覆盖。下载失败不回退到 filesystem path。所有 unexpected exception 在
Python 和 browser 侧均映射为固定 public message；console 不打印 response body、
token、project absolute path 或 sample values。

## 13. 打包与 0.5.0 promotion

### 13.1 Dependency contract

Python runtime dependencies 仍仅为 `stm32-toolkit==0.5.0` 和 `aiohttp>=3.9,<4`；Preact、
ECharts 和测试工具是 `tools/stm32-monitor/ui` 的 npm dependencies/devDependencies，
不得进入 Python import graph。`npm ci` 是唯一安装方式；direct versions 精确固定，
lockfileVersion 由指定 Node/npm 生成且提交。

生产 build 必须通过静态检查证明没有 `eval/new Function`、remote URL、full ECharts
bundle、source map、service worker 或 inline script/style。gzip 后 initial JS <=
450 KiB、CSS <= 50 KiB；所有未压缩 wheel UI assets 合计 <= 8 MiB。

### 13.2 Unified version surfaces

0502 在同一个 implementation delivery 中把 active product surfaces 从 0.4.0 提升到
0.5.0：两个 `pyproject.toml`、两个 package `__version__`、Toolkit CLI version、Monitor
protocol envelope 的 toolkit/monitor version、plugin manifest、managed-runtime
launcher/setup、release Skills、README 和相应 active tests。

不得改写历史 specs、已验收 implementation reports 或专门测试 previous-version
compatibility 的 fixture。Setup Repair 必须识别并隔离已有 healthy/broken 0.4.0
runtime，再原子提升 0.5.0；promotion 后验证两个 distributions、probe extra、doctor、
Monitor CLI 和 UI asset manifest。

### 13.3 Wheel evidence

使用一次 clean source tree 构建：

- `stm32_toolkit-0.5.0-py3-none-any.whl`；
- `stm32_monitor-0.5.0-py3-none-any.whl`。

在 repository-external fresh venv 安装两 wheel 后，必须在删去 repo `PYTHONPATH` 的
环境中证明 exact versions、ordinary imports lazy/no project writes、`stm32-monitor
serve --json` 无 browser side effect、static index/assets 可读、CSP 正确、API auth
仍关闭失败。report 记录 wheel filename、byte size 和 SHA-256；不把 token 或 access
URL 写入 report。

### 13.4 Tracked implementation report

实现报告的唯一路径是
`docs/codex/returns/STM32TK-0502-MONITOR-UI-RELEASE/implementation-report.md`。Codex 子代理
先产生一个 code head，再提交 report；report 必须记录 module ID、实现状态、完整
accepted-base SHA、branch、完整 **code head before report commit** SHA、scope/path summary
与版本/lockfile 事实。每个 gate 一行记录 evidence owner、`PASS/FAIL/BLOCKED`；只有具名的
`Linux release owner` 和 `user/hardware owner` 两类平台 gate 可记录 `DEFERRED`。每行还要记录 OS/arch、工具绝对路径与版本、working directory、完整命令、UTC 时间、
exit code、bounded stdout/stderr summary 和关键测量。artifact inventory 对 wheel、`ui_dist`
tree/manifest 及保留的 E2E/performance evidence 记录相对路径、byte size 和 SHA-256。
报告不得包含其自身/final commit SHA、moving commit totals、token/access URL 或伪造的硬件 PASS；
report commit 之后的 final head 只在 return/PR metadata 中出现。

## 14. 测试、性能和 evidence matrix

实现与实现测试 owner 是 Codex 子代理。Windows 强制 gate 只有 `PASS/FAIL/BLOCKED`；`PASS`
仅表示指定 owner 在 report 的 code head 上实际运行，纯代码失败不得 `DEFERRED`。仓库规则未授权
新增 CI workflow，且本会话没有受控 Linux runner，因此 Linux 只能作为明确的平台证据延期，不能
借此延期任何已可在 Windows、浏览器或安装 wheel 上验证的产品行为。

### 14.1 强制平台与工具解析

| Owner / status | 强制环境 | 规则 |
|---|---|---|
| Codex Windows 验收子代理 / mandatory | Windows 11 x64，CPython 3.10/3.12，Codex bundled Node/npm，Playwright Chromium | 从 Codex bundled runtime 定位每个工具并以绝对路径调用；不依赖 `PATH`。任一必需 runtime 无法定位则模块 `BLOCKED`。 |
| 后续 Linux release owner / platform-deferred | Linux x86_64、CPython 3.10/3.12、Node/npm、Playwright | 本模块不新增 CI workflow。只有取得受控 runner 后才可把该行从 `DEFERRED — Linux release owner` 提升为 PASS；不得复用 Windows 结果。 |

Windows 首次 lockfile 构建时把 bundled Node 的完整已解析版本作为
`package.json#engines.node` 具体下限，上限为下一 major；`packageManager` 固定已解析的完整
npm 版本。report 记录实际值，不以“Node 22/npm 10”或当前 `PATH` 作假设。

### 14.2 精确 gate matrix

| Gate / owner | 命令契约 | PASS 条件 |
|---|---|---|
| Git scope / Windows | clean review worktree；`git diff --name-status bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa..CODE_HEAD` | 全 diff 属于 0502，report code head 对齐 |
| Node / Windows mandatory；Linux deferred | 以已记录的绝对工具路径运行 `npm ci`、typecheck、lint、`test:coverage`、`test:a11y`、build/dist verify、production audit | Windows：lockfile 不变；strict TS/axe 全过；新/修 product module branch >=90%；dist byte-identical/满足 size；无 high/critical。Linux 独立记录。 |
| Python / Windows mandatory；Linux deferred | CPython 3.10/3.12 fresh venv 运行完整 Monitor suite；3.12 跑 branch coverage、既有非重叠 Toolkit shards | Windows：所有 nodeid 恰好一次且 pass；总体和每个新/修 product module branch >=90%。Linux 独立记录。 |
| Auth/package/performance / Windows mandatory；Linux deferred | 运行 `test_auth.py`、`test_service.py`、`test_package_boundary.py`、`test_performance.py -q -s`；构建/外部 venv 安装两 wheel | Windows：第 7.3 节矩阵、0501 性能门禁、package isolation、exact 0.5.0/assets/hash 全过。Linux 独立记录。 |
| E2E / Windows mandatory；Linux deferred | Windows 跑 Playwright Chromium 1280×720/1024×768；Linux runner 可用时再跑 Chromium/Firefox/WebKit | Windows：第 14.3 节、基本 chart zoom/恢复、CSP/token/keyboard/200% page zoom/no-remote 全过；不强制专用 Edge。Linux 独立记录。 |
| Launcher/package / Windows | `cmd.exe /d /c bin\stm32-monitor.cmd ...`；两 Python 外部 venv 验证 wheel | 无 ambient Python fallback；`serve` 不开 browser；`open` 恰好一次；Ctrl-C cleanup；import/assets 隔离 |
| Plugin / Windows mandatory；Linux deferred | mandatory fallback：扩展并运行 `tools/stm32-toolkit/tests/test_plugin_layout.py`，验证 manifest schema、8 Skills、launcher/setup 与版本；官方 CLI 可用时另跑 `claude plugin validate .` | fallback validator 必须 pass；CLI 不可用只记录环境事实，不取代 fallback；Linux 独立记录 |
| Security / Windows mandatory；Linux deferred | 检查 built JS/HTML、wheel RECORD、headers、storage/request log | Windows 必须证明 token 不在 DOM/log/storage/files；strict CSP/same-origin；no CDN/source maps；Linux 独立记录 |
| Physical board / user/hardware owner | 一块已支持板的观察 smoke | 平台专属，可记 `DEFERRED — user/hardware owner`；另一类可延期项仅为具名 Linux release owner。无真实命令/输出不得声称硬件 PASS |

### 14.3 必须覆盖的 E2E 场景

Playwright 使用 real `MonitorService` + test-only fake runtime，不能绕过 HTTP/WS：

1. fragment 清除、HttpOnly bootstrap、cookie refresh、bad token fail closed；fresh workspace 零组及 group CRUD/export/import conflict；
2. probe list/connect/reconnect/release、busy/lease-lost 不抢占；catalog pagination 与 scalar/float/enum/array/member/register/unavailable；
3. 100/250/5000 ms start/pause/resume/stop；256-row table、8×600 chart、鼠标/触摸/键盘 zoom 及 reset、item error isolation；
4. replay success、expired `gap:true`、heartbeat stale、binding/run reset；compact quality；basic paged history 与 verified CSV/JSONL；
5. 两 workspace 的 port/token/groups/history/live/storage 隔离；三浏览器中任何非当前 loopback origin request 都失败且计数为零；
6. bootstrap 后 DOM/URL/console/localStorage/sessionStorage/IndexedDB names/readable cookie 中无 token。

### 14.4 UI 性能 fixture

Chromium 1280×720 production build 以 10 Hz、256 rows、8×600 points 运行 5 分钟；第 2–5 分钟要求 update p95 <=150 ms、无 >=200 ms Long Task、points <=4,800、queue 无增长、heap slope <=2 MiB/min，且 client coalescing 不改变 server drop totals。report 记录 CPU/Node/Chromium、viewport、sample count、p50/p95/max、Long Tasks、heap slope 和 asset sizes。

## 15. 明确延期到 0.6，0502 禁止实现

旧联合计划中的以下内容移到 `0.6.0`，0502 code/assets/hidden route/flag/tests/README 均不得包含：AI-readable snapshot 或 diagnostic session export、“AI Analyze”；多 run/group/firmware overlay、diff/brush/cross-session 等 advanced history comparison；rate/latency/drop timeline、distribution、per-stage/halt-impact 等 full quality dashboard；annotations/bookmarks/diagnostic markers；diagnostic timeline 与 hypothesis/evidence/action/fix-verification UI。

0.5 的 verified CSV/JSONL history export 与仅用于用户组迁移的 group schema JSON 都不是 AI snapshot/session export。

## 16. 其他非目标

- 除第 7.3 节受控 auth transport 修正外，不改 0501 REST/WS schema/operation、history v2、retention、sampler/exporter；不加 raw/register write、halt/step/reset/flash/debug control。
- 不加 probe steal、auto probe reconnect/start、named-group restore、递归 complex tree、pointer/address/type guessing。
- 不加 cloud/remote auth/TLS/fixed port/external DB/collaboration/CI/dispatch automation；Node/node_modules 不进 Plugin/runtime/wheel，UI 不是独立服务器或 desktop app。

## 17. 验收标准

0502 仅在以下全部成立时可判定 `ACCEPTED`：

1. accepted-base→head 只含核心 UI/static/auth compatibility/launcher/Plugin/Skill/README/version/evidence；除第 7.3 节外 0501 protocol schema/operation diff 为零；fresh workspace 正确 identity、零组、无 preset/name seed。
2. probe lifecycle、catalog/shallow selection、group CRUD/import/export、100 ms–5 s lifecycle、typed table、8-series chart 及可恢复 basic zoom、paged history、verified CSV/JSONL 全部可用。
3. compact quality 与 error/stale/reset/gap/lease-conflict 行为准确；不自动抢占、不伪造连续性。
4. human `open` 只开一次 browser；machine `serve --json` 不开 browser；两者 cancellation-safe、无 ambient interpreter。
5. 0.5.0 wheel 含可复现 committed dist，Python build 不需 Node，offline/no-CDN；token 仅局部 fragment bootstrap/HttpOnly cookie，runtime record 仅 token SHA-256，DOM/URL/console/storage/wheel/report/logs 无 token。
6. loopback/random port/Host/Origin/CSP/same-origin/no-remote/workspace isolation 与第 14 节双 Python、Node、coverage、performance、wheel、E2E、Windows/plugin 强制 gates 全 PASS；第 13.4 节 report 对应 returned code head。Linux 与硬件未跑时只能按各自指定平台 owner 明确 DEFERRED，且不得掩盖任何 Windows 可复现的产品失败。
7. active Toolkit/Monitor/Plugin/runtime/Skills/README 全为 0.5.0，0.4.0 可受控 Repair，两 wheel hashes 已记录；第 15 节功能不存在，0.5 验收前没有 0.6 实现。

超出第 7.3 节的 protocol 改动、token 泄露、remote request、preset、workspace crossing、隐式 probe/start、不可复现 dist、缺失强制 evidence 或任何 deferred product feature 都是拒绝条件。
