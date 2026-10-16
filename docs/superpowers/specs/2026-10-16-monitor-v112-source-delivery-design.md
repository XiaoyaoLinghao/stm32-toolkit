# Monitor 已验收更新的 v1.1.2 源码交付规范

2026-10-16；用户明确批准将已验收 Monitor 更新推送 GitHub，并要求版本 v1.1.2；此前已授权本地后续工作无需再审批。Full accepted base：`b257c7e2ebb757c5228d5176d813e14573c4403e`，Monitor 产品 `de6f3434865f3c85119e566c314ded0c6ea3e232`。主代理审定本规范和计划，负责集成、独立完整差异审查与接受；单一 gpt-6-sol/max 实现者负责版本及相应测试，独立 gpt-6-sol/max 只读审查者复核。无 ownership override。

当前分支 `codex/monitor-workbench-local-complete`，隔离实现树 `D:\codex-tmp\mufin1015\impl` clean；远端 master `3edd82e6b8f2ebd5df88dcafde1e75f722357c3e` 已包含在本地候选祖先中，交付分支与 v1.1.2 标签在本次只读核对时不存在。原始工作区保持不动。唯一授权远端动作是把已验收的版本更新推送到该交付分支；没有 PR、master 合并、tag/Release、删除或强推授权。最后以远端精确 SHA 核对交付。

## 三条用户场景

1. 源码、CLI/协议、Toolkit/Monitor/Python依赖、UI、插件、启动器及发行元数据一致识别为 1.1.2；Monitor 的全部已接受行为保持，协议/数据 schema 版本不随产品版本更改。
2. 已发布 1.0.1 的运行时经既有 Check 可识别为旧版本，只有显式 Repair 才进入原升级事务；旧 1.0.1 生成工程可读取并按原 configure 合同更新，用户改动仍受保护。旧版本身份与现存用户数据不被重写。
3. 定向版本/兼容回归、生成资产核对和独立完整差异通过后，版本提交与 Monitor 既有提交一起推送交付分支；分支远端 HEAD 等于被接受的最终本地 HEAD。

## 单一版本合同与边界

运行版本的源头仍为 Toolkit `__version__`，Monitor import/协议沿用它；现有静态 manifest、pyproject、启动器、setup 与 release builder/policy/schema 按既有机制同步为1.1.2，不新增版本框架。Monitor 的 Toolkit 精确依赖同步为 `stm32-toolkit==1.1.2`。UI lockfile 只改顶层与根 package 元数据，不改第三方包版本、resolved、integrity 或依赖图。

setup 对 release builder 与 policy 的两个 SHA256 trust anchor 必须随对应文件最终字节重新计算并同步。锚点以 Git 提交/归档内的精确文件字节为准，不以 Windows checkout 的自动换行副本代替；由既有归档锚点回归证明。除这两个必要派生常量外，不改变 trust 校验规则或失败语义。

setup 的 LegacyRuntimeVersions 纳入1.0.1，保留已有旧版本及未知/未来/同版本异源/降级拒绝；generation 的 legacy producer 纳入1.0.1，仍保留1.0.0/0.9.0支持。不变更 schema/协议名称或授权、身份、哈希、事务、锁、恢复规则，不实际升级用户安装环境。

持久导出清单继续按现有精确 Toolkit/Monitor 版本校验；不放宽 `exports.py`，不自动迁移或重签旧清单。旧1.0.1导出在1.1.2下不能视为新版本合法产物；使用原版本读取原导出或在新版本重新创建导出。历史采样/组数据及旧固件/证据保留原身份，相关文档说明此边界。

当前候选文字改为1.1.2，明确最新已发布仍为1.0.1、本轮是源码分支推送。CHANGELOG 添加 Monitor 汇总，保留历史条目；release-status 可追加未发布候选状态，不改旧发布日期、SHA、coverage或物理结果。README双语、当前安装路径示例、user-guide 与 Windows preflight 的“当前版本”同步。过去规格、计划、接受报告、旧工程/固件/evidence fixture 和第三方依赖中的1.0.1不能整体替换。

## 非目标与证据

不新增 UI 功能，不安装新工具/依赖，不构建发布包或改写旧发布资产，不实际运行 Repair，不执行硬件、浏览器或权限排查，不创建标签/Release/PR。浏览器、硬件与发布矩阵继续 DEFERRED；旧1.0.1 coverage例外不授予1.1.2发布资格。只有与版本身份及兼容相关的软件检查重跑；已接受 Monitor 行为证据保留其原范围。8765 原服务保持至本次源码接受；主代理可沿已授权运行流程更新本机来源，仅验证进程/监听，不冒充浏览器通过。
