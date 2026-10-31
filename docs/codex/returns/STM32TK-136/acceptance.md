# v1.3.6 工具侧修复：定向验收记录

验证源码：`9a8b83bb6ee02cea0ab0240b7f3cbd86fbf97a9b`。
Primary 独立复核；实现与实现测试由本地 Claude Code CLI 完成。
本页记录已完成的定向检查；完整回归、最终覆盖率及发布状态另行汇总。
原 Keil/迁移工程、现有安装与硬件未操作。所有工程均为测试创建的临时夹具。

## 构建与 context

在已有真实 ARM GNU 夹具上依次执行公共 CLI（实际入口为隔离解释器的
`-m stm32_toolkit.cli`，下列 `<fixture>` 为
`D:/codex-tmp/v136-evidence/p01/t/test_real_gcc_debug_release_de0/out/gcc-project`）：

```text
stm32-toolkit build --project <fixture> --preset arm-release --json
stm32-toolkit build --project <fixture> --preset arm-debug --json
stm32-toolkit project context --project-root <fixture> --data-root <temporary-data> --session-id v136-offline --json
```

两次构建和最终 context 均实际退出 0、`ok=true`，均未传 `--clean`。

| 字段 | arm-debug | arm-release |
| --- | --- | --- |
| receipt | `artifacts/migration/build-result.json` | `artifacts/migration/arm-release/build-result.json` |
| toolkitVersion | `1.3.6` | `1.3.6` |
| buildId | `769bdb58aabb4644c79b8c0214657f03129d36b8d682b23a2fc48c7f32125c90` | `9d5e1ac932808eeb519b250ceff0a7a47900fce208d2f764fbd579e3c70a8d80` |
| elfSha256（identity） | `c36fd5db5bc8e0c7b25c4b5fe183e9b598785c1fcc51e2630097fc9c2d2678ef` | `e736a6802c609598ed04bba1b08b3e1f9f8044ede2ec2231a515b370add59813` |

context 返回 `elfFresh=true`、`preset=arm-debug`，其 `buildId`/`elfSha256`
与上表 debug identity 完全一致；`sourceBaseline=input-snapshot-v1`，无 Git
内容身份路径正常。首次 context 验收脚本误用仅适用于 workflow 的 `--project`
别名，保留其参数错误和脚本 JSON 解码失败；只补做一次 `--project-root`
只读检查，没有重跑两次已成功构建。原 CLI 数值退出未被该脚本保存，保持 unknown。

## ABI 来源与烧录证据

迁移 PLAN/APPLY 与 conversion report 的定向测试已通过。新增构建测试同时
验证 schema-1/schema-2，identity、typed identity、receipt 的证据相等：

```json
{"rawFloatAbi":null,"selectedAbi":"hard","origin":"inferred","ruleId":"MIGRATION_FLOAT_ABI_DEFAULT_HARD_INFERRED","baselineVerified":false}
{"rawFloatAbi":"softfp","selectedAbi":"softfp","origin":"declared","ruleId":"MIGRATION_FLOAT_ABI_DECLARED","baselineVerified":false}
```

两类均包含原始决策字段、`warning`、固定 `reportPath` 与实际报告 SHA-256；
推断未升级为原二进制 ABI 已验证。显式 softfp 不被覆盖。缺可选字段的旧记录、
增量构建保留旧捕获证据、无效/变化报告和伪造 receipt 的处理均有覆盖。

受管烧录使用离线后端夹具测试公共 JSON 与持久化 receipt：

| backendBytesProgrammed | backendSectorsProgrammed | verifiedBytes |
| --- | --- | --- |
| null | null | 320 |
| 1234 | 2 | 320 |
| 0 | 0 | 320 |

每个用例只编程调用一次。`null` 表示后端未报告；0 与真实整数原样保存，
`verifiedBytes` 是独立回读范围。这是软件协议测试，不是新实机烧录记录。

## 独立测试与构建

Primary 对 `test_build_abi_evidence.py`、`test_build_runner.py`、
`test_build_preset_evidence.py`、`test_build_snapshot.py`、`test_firmware_identity.py`
运行既有 pytest/原生分支覆盖入口：321 passed，0 failed/error/skip，实际退出 0，
源码未变。其中真实 GCC debug → release → debug 流程及正常固件准入通过。
先前失败与修正均保留，不将重叠检查累加为额外独立用例。

[两次发布包构建和官方校验](candidate-build.md)已通过。
原始命令、JSON、JUnit 和源绑定记录位于 `D:/codex-tmp/v136-evidence`：
`p01/execution.json`、`cli-acceptance/execution-complete.json`、
`acceptance-checkpoint.json`、`complete-package-verification.json`。
完整矩阵完成前，不把本页解释为全部发行资格或已发布。
