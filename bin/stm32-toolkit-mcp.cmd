@echo off
setlocal

if not defined CLAUDE_PLUGIN_DATA (
  >&2 echo stm32-toolkit-mcp: CLAUDE_PLUGIN_DATA is not set. Run /stm32-toolkit:setup-stm32-env, then retry.
  exit /b 2
)

set "STM32_TOOLKIT_RUNTIME=%CLAUDE_PLUGIN_DATA%\runtime\0.2.0\Scripts\python.exe"
if not exist "%STM32_TOOLKIT_RUNTIME%" (
  >&2 echo stm32-toolkit-mcp: runtime/0.2.0/Scripts/python.exe is missing under CLAUDE_PLUGIN_DATA. Run /stm32-toolkit:setup-stm32-env, then retry.
  exit /b 2
)

"%STM32_TOOLKIT_RUNTIME%" -m stm32_toolkit.mcp_server %*
set "STM32_TOOLKIT_EXIT_CODE=%ERRORLEVEL%"
exit /b %STM32_TOOLKIT_EXIT_CODE%
