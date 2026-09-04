# 当前实机验证原始代码位置

用户于 2026-09-04 指定的原始代码目录：

`D:\workspace\MR_Code\branches\stable`

此路径是用户提供的来源定位，不是当前 Toolkit 实机命令的 project-root。
本机当次 `Test-Path -LiteralPath` 返回 `True`，确认目录存在。Git 检查返回“不是 Git
仓库”，因此不记录或推测原始目录 Git HEAD。与验证副本的逐文件对应关系尚未核实。
用户最初提供的 `D:\workspace\WDS\_CODE\branches\stable` 不存在，随后明确更正为上述
`MR_Code` 路径；以更正后的路径为准。

当前已经执行 bind/register/sample 的验证副本为：

`C:\tmp\stm32tk-vs10a-legacy-campaign\project-standard-math`

- 验证副本 Git HEAD：`cf273a18b4c757b4866793c94b25d5ceaad39925`。
- ELF：`build/arm-debug/LWIP.elf`。
- ELF SHA256：`f59b84097e2f78a7e93f1c8a7d1041bd5818169bdf25d6598a8f749082475b6c`。
- Build ID：`a05dc376406721d497b0af451951420a583113eb298dd50d26eeb3ebdbfb8d44`。

后续不得把验证副本路径、历史 intake 路径与用户指定的原始代码位置混为一谈；也不得仅凭
这个来源定位声明原始目录与已烧录 ELF 字节一致。此记录不授权修改原始代码或切换实机固件。
