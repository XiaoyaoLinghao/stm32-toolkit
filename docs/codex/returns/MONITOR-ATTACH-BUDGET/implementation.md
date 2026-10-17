# MONITOR-ATTACH-BUDGET 实现报告

- Accepted base：`0b9f3a75c6490f1f7c2706b1eef907f0fa252de6`。
- 报告前产品 CodeHead：`93fa4bf7a7af78eae6c30ba827b47c8beba14fa4`。
- 实现者：ui03_impl（gpt-6-sol/max）。本报告不作自我接受；主代理和独立审查者负责完整差异审查。无远端、浏览器、真实服务或硬件操作。

## 交付行为

`ProbeClient` 的 `attach_timeout_ms` 是严格整数 1..300000，默认仍为 5000 ms，只改变 `probe.attach` 请求。Monitor 默认单参数客户端工厂设为 35000 ms，初次绑定和同一客户端的重验证各自使用该有界预算；读请求和其他通用请求仍保持原期限。Probe Service/worker 的锁、截止时间、生命周期与清理均未更改。

`PROBE_TIMEOUT` 经 Monitor observation open、revalidate、read、ProbeSession 阻断/目录和 runtime 目录路径保留为 `MONITOR_PROBE_TIMEOUT`。失败不发布部分绑定或样本，连接失败原有白名单 `attachDiagnostic` 与清理优先级保留。工作台失败卡新增“探针请求超时”中文标题，现有详情与人工恢复流程不变。UI 构建产物已重新生成。

## 离线证据

所有命令的实际 argv、完整 stdout/stderr 与退出码分别保存在 `D:\codex-tmp\mf1017\test-impl\*-command.txt`、同名前缀 `.log`、`*-exit.txt`；Python `PYTHONPATH` 指向本实现树的 Toolkit/Monitor `src`，`TEMP/TMP/TMPDIR` 指向本轮 `test-impl\t`，pytest 使用独立 `--basetemp` 且禁用默认缓存。

| 运行 | 结果 | 证据前缀 |
| --- | --- | --- |
| 产品修复前聚焦红回归 | 13 failed，exit 1；构造参数、请求预算、超时归类、阻断均暴露旧行为 | `red-*` |
| 补充目录红回归 | 2 failed，exit 1；ProbeSession 与 runtime 的目录超时被错归 provenance | `red2-*` |
| ProbeClient 与跨层聚焦绿回归 | 82 passed，exit 0 | `green-focused-*` |
| 真实 Probe Service + fake backend 延迟 5.25 秒 | 1 passed，exit 0；旧 5 秒界限之后，Monitor 客户端仍正常 OBSERVE attach、读取，backend 未停核 | `slow-attach-*` |
| Toolkit/Monitor 相关套件和生命周期精选节点 | 252 passed、1 skipped，exit 0；含队列到期、迟到候选、取消、清理及诊断 | `python-matrix-*` |
| 目录代码守卫修订后 Monitor 三套件 | 91 passed，exit 0 | `monitor-final-*` |
| 最终 runtime 格式修订后完整 runtime 套件 | 61 passed，exit 0 | `runtime-code-final-*` |
| UI 失败卡/中文测试 | 2 files、9 tests passed，exit 0 | `ui-focused-*` |
| UI typecheck、e2e typecheck、lint、build、verify:dist | 各 exit 0；dist 7 文件逐字节一致 | `ui-typecheck-*`、`ui-typecheck-e2e-*`、`ui-lint-*`、`ui-build-*`、`ui-verify-dist-*` |

唯一跳过项是 `test_monitor_observation.py:948` 的 Windows 平台条件：目录句柄阻止 rename；属 PLATFORM，未作为物理或该场景 PASS。Vite 构建仍提示既有大 chunk，构建与 dist 比对成功。未运行发布矩阵或真实浏览器。

真实 F429 一次续验、历史/CSV/波形及 8765 服务恢复由主代理在独立精确 CodeHead 审查和执行卡核对后负责；本实现报告只记录离线软件证据。

## 临时目录与清理

本轮专属 `D:\codex-tmp\mf1017\test-impl` 下保留命令、日志、退出码及失败证据。拟清理的可丢弃 pytest basetemp/cache 目录为 `red`、`red2`、`green-focused`、`slow-attach`、`python-matrix`、`monitor-final`、`runtime-final`、`runtime-code-final` 和 `t`。单次 PowerShell 路径核对及删除命令在执行前被策略拒绝（`blocked by policy`）；因此未删除，也未重试或改用其他工具绕过。复制的 UI `node_modules` 保留供独立审查，未安装依赖。主代理负责后续可归因清理。
