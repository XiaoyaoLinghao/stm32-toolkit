# Monitor 固定入口实施计划（已批准）

对应规范：[2026-10-15-monitor-fixed-entry-design.md](../specs/2026-10-15-monitor-fixed-entry-design.md)。切片：MONITOR-ENTRY-01。

Accepted base：`224d5ea416971b1ba401147a4a2b4bf99a3cb8de`。用户于 2026-10-15 明确批准规范和计划并授权实施。该基线的 UI01 本地代码已验收；浏览器/视觉证据保留待验，不因开始 ENTRY01 自动转为 PASS。

## 所有权和隔离

- 主对话代理：基线重建、规范、计划、集成、完整差异审查和验收。
- 单一 `gpt-6-sol/max` 子代理：有界实现与实现测试，不递归委派，不自我验收。
- 计划本地分支：`codex/monitor-entry-01-fixed-url`；无 PR/远端动作授权。
- 全新隔离 Git/worktree 从 accepted base 开始；临时目录、缓存与证据仅位于 `D:\codex-tmp`。原始脏工作区保持不动。主对话代理负责精确路径清理。
- 本切片不与其他写代理并行修改共享文件；依赖/lockfile/版本/CI 均不改。

## 实施顺序

1. 确认 clean/full SHA，记录 config/service factory 调用者、CLI 兼容断言和认证安全检查的既有测试。
2. 贯通可选端口：CLI 校验、模型默认值、runtime 转发、service 指定绑定和失败清理。`open` 输出无 token 短地址；不改变 serve JSON。
3. 在 auth 适配边界集中定义 HTTP 默认端口 authority/origin 表示与精确匹配，供 endpoint/静态服务/认证共同使用；在 service 统一按实际端口计算 cookie 名并用于 bootstrap/授权。验证实际端口 80 的 canonical/显式等价写法与其他主机/来源拒绝，并验证不同服务 cookie 互不覆盖，Bearer 与其他请求边界不变。
4. 前端先分类 URL 再清除敏感信息，增加严格的普通根地址 cookie/status 恢复；沿用原挂载/controller 生命周期和集中中文错误词条。
5. 更新指南，完成下列检查、重建 ui_dist，提交产品 CodeHead 后返回；主代理在干净树独立审查，修订留在同一分支。通过后写实现报告，区分 CodeHead 与报告提交。

## 有界验证

| 层次 | Owner / 环境 | 证据 |
|---|---|---|
| CLI/模型/传参 | 实现代理 / Windows pinned Python | 默认动态端口、显式端口、非法值退出码、service factory 传参；stdout 无新增 token，serve JSON 兼容 |
| 绑定/清理 | 实现代理 / 可用 loopback 的 Python 环境 | 指定端口成功、冲突明确失败、只绑定127.0.0.1、失败/正常停止清理；运行根自包含 |
| 认证回归 | 实现代理 / Python aiohttp fixture | cookie 名写读一致、双服务 cookie 并存、同端口重启旧 cookie 拒绝、旧固定名拒绝；既有 Bearer、HTTP/WS、Host/Origin/Fetch Metadata 检查 |
| 默认端口边界 | 实现代理与主代理分别 / 纯 Python auth+endpoint、Node URL parser | 实际端口 80 的 endpoint canonical URL、浏览器解析与精确 Host/Origin 等价形式；非 80、localhost、错误端口/协议/畸形来源均不放宽。纯解析/函数结果不能代表真实监听或浏览器 PASS |
| 启动分支 | 实现代理 / pinned Node+Vitest | 使用会真实更新 location 的 Window fixture，验证 href/query 在 scrub 前判定，包括 `/?`、`/#`；普通根路径有效/失效 cookie、无效响应/网络失败；非法 token/query 不发 status 请求；失败不挂载 App |
| 前端静态/资产 | 实现代理 / pinned Node | typecheck、typecheck:e2e、lint、受影响 Vitest；build、verify:dist；不得手改 bundle |
| 用户路径 | 主对话代理 / 获准访问本机端口的 Windows 浏览器 | 在同一浏览器配置中首次 bootstrap→token移除→关标签页→短书签恢复；同端口重启后重新加载授权链接并完成 bootstrap；不同配置不宣称同步会话；双工程并开；会话丢失和占用端口提示 |
| 独立审查 | 主对话代理 / 同一 CodeHead clean review tree | accepted-base 全差异、核心 auth/URL 分支检查、复跑受影响静态/测试与生成资产一致性 |
| 发布/硬件 | 后续发布/集成 owner | 最终包嵌入、全量发布矩阵、目标硬件；本切片不声称发布或物理 PASS |

UI01 期间本机 Python socketpair/loopback 连接及独立 Chromium 启动已受环境限制；现有浏览器访问本机端口也未获授权。ENTRY01 不以更换浏览器、代理或降低安全校验绕过限制。可运行的检查照常完成；不可运行项分类 ENVIRONMENT，保留最小证据并交给主对话代理在获准的环境补验。纯代码失败必须修复，不能 deferred。

## 接受与退出

规范四个场景闭合、无未解决代码/认证缺陷、所有可运行必需检查通过、生成资产一致。浏览器和真实 loopback 证据若仍缺失，明确列为待验，不能宣称完整用户路径验收。发布行为仍需单独授权。

本切片已获得独立批准，按上述冻结契约扩展入口；UI01 的旧验证证据不代表新入口已通过。
