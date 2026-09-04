# 当前实机验证原始代码位置

用户于 2026-09-04 指定的原始代码目录：

`D:\workspace\WDS\_CODE\branches\stable`

此路径是用户提供的来源定位，不是当前 Toolkit 实机命令的 project-root。
本机当次 `Test-Path -LiteralPath` 返回 `False`；原始目录内容、Git HEAD 和与验证副本的
逐文件对应关系尚未核实。保留用户原始拼写，不自行改写为其他历史路径。

当前已经执行 bind/register/sample 的验证副本为：

`C:\tmp\stm32tk-vs10a-legacy-campaign\project-standard-math`

- 验证副本 Git HEAD：`cf273a18b4c757b4866793c94b25d5ceaad39925`。
- ELF：`build/arm-debug/LWIP.elf`。
- ELF SHA256：`f59b84097e2f78a7e93f1c8a7d1041bd5818169bdf25d6598a8f749082475b6c`。
- Build ID：`a05dc376406721d497b0af451951420a583113eb298dd50d26eeb3ebdbfb8d44`。

后续不得把验证副本路径、历史 intake 路径与用户指定的原始代码位置混为一谈；也不得仅凭
这个来源定位声明原始目录与已烧录 ELF 字节一致。此记录不授权修改原始代码或切换实机固件。
