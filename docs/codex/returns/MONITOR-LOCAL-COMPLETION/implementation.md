# Monitor 最终本地集成实现回报

## 身份与边界

- Full accepted base：`a2ccdd2f3bfbecfd2fa1fc52f0313d7016c287c7`；固定产品 CodeHead：`de6f3434865f3c85119e566c314ded0c6ea3e232`；分支 `codex/monitor-workbench-local-complete`；实现树 `D:\codex-tmp\mufin1015\impl`。本报告在产品提交后单独提交，不记录报告自身 SHA。
- 按主代理冻结的 `docs/superpowers/plans/2026-10-16-monitor-local-integration-plan.md`，本地 merge 精确远端 `3edd82e6b8f2ebd5df88dcafde1e75f722357c3e`；merge 提交 `09f5706b9f4e5853f1df83c9902d790963fff84d` 的第二父提交正是该 SHA。远端相对发布 `0f06c659f5e04aa1f8e53022eae9b5e964da2b4b` 的 9 个文件全部保留，7 份文档与远端字节一致；两个测试文件只做已接受中文及生命周期合同适配。
- 没有安装依赖、修改 Python/API/wire/codec、导出转换与行为、版本、锁文件或构建配置；没有浏览器、硬件、服务切换和远端写操作。主代理和独立审查者负责完整差异审查与接受。

## 集成行为

1. `bootstrap.test.ts` 保留远端新增的纯根入口、拒绝和异常响应测试；将固定恢复断言改为产品中文。测试仍核对 fragment hash 清除、一次同源请求，以及 token、服务端 message/details 和原始响应不进入返回值或页面。
2. `groups-panel.test.tsx` 保留导入预览确认及远端新增的读取中卸载测试。输入文件在读取开始即清空，以允许重新选同一文件；卸载前捕获输入状态，卸载后等 FileReader 完成，断言无 detached input 的 value setter 调用、状态无变化、无导入回调和无预览。原 `groups-import-lifecycle.test.tsx` 回归一并通过。
3. `zh.ts` 的通用 `invalidRange` 只说明 UTC 解析与先后顺序；新增 `historyInvalidRange` 专属历史记录的 1970/int64 提示，`HistoryPanel` 使用后者。`ExportPanel` 继续使用通用文案，`historyInput/inputNs` 与导出操作未变。重新构建并跟踪 7 个 UI dist 文件。

## 实现者证据

命令均在 `D:\codex-tmp\mufin1015\impl\tools\stm32-monitor\ui` 运行。每次设置 `TEMP/TMP/TMPDIR`、npm 缓存和适用的 Vitest 缓存到对应 `D:\codex-tmp\mufin1015\run` 子目录，关闭 npm 更新通知；每处有 `command.txt` 与完整 `output.log`。最终检查针对上述固定 CodeHead；产品提交后重建并确认工作树干净。

| 命令 | 结果 | 日志子目录 |
| --- | --- | --- |
| `npm.cmd run test` | exit 0；49 文件、417 测试通过 | `full-ui-final` |
| `npm.cmd run typecheck` | exit 0 | `typecheck-final` |
| `npm.cmd run typecheck:e2e` | exit 0 | `typecheck-e2e-final` |
| `npm.cmd run lint` | exit 0 | `lint-final` |
| `npm.cmd run build` | exit 0 | `build-final` |
| `npm.cmd run verify:dist` | exit 0；7 文件逐字节一致 | `verify-dist-final` |

红证据：`red-copy/output.log` 中新增导出倒置范围断言在旧共享 1970 文案下按预期失败，2 文件共 1 失败、15 通过，exit 1。修改文案后 `focused1/output.log` 覆盖 bootstrap、groups-panel、groups-import-lifecycle、export-panel、UI06 HistoryPanel：5 文件、76 测试通过。增强卸载后的 setter 断言后 `focused2/output.log` 的组测试 2 文件、29 测试通过；随后重新执行最终全套 UI、两项 TS 和 lint。合并时的英文固定断言与旧文件保留断言属于 **PRODUCT（测试契约适配）**：适配已接受的中文 UI 和读取开始清空 input 行为，没有放宽 token 非泄露或卸载后副作用保护。全套 UI 的 jsdom navigation 提示及构建的大 chunk 建议均非失败。

本次运行子目录为 `red-copy`、`focused1`、`focused2`、`full-ui`、`full-ui-final`、`typecheck`、`typecheck-final`、`typecheck-e2e`、`typecheck-e2e-final`、`lint`、`lint-final`、`build`、`build-final`、`verify-dist`、`verify-dist-final`。主代理是运行根清理 owner；独立验收后按归属清理无用缓存及中间输出，保留最终与最小红证据。

实现者不自行接受产品差异。真实浏览器/视口/手势/axe、HTTP/WS 服务、关闭后重新打开、物理采样和发布层证据仍归主代理或后续 owner；此处 jsdom 与离线构建不冒充外部 PASS。
