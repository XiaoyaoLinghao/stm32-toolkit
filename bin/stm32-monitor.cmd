@echo off
setlocal

if not defined CLAUDE_PLUGIN_DATA (
  >&2 echo stm32-monitor: CLAUDE_PLUGIN_DATA is not set. Run /stm32-toolkit:setup-stm32-env, then retry.
  exit /b 2
)

set "STM32_MONITOR_RUNTIME=%CLAUDE_PLUGIN_DATA%\runtime\0.5.0\Scripts\python.exe"
if not exist "%STM32_MONITOR_RUNTIME%" (
  >&2 echo stm32-monitor: runtime/0.5.0/Scripts/python.exe is missing under CLAUDE_PLUGIN_DATA. Run /stm32-toolkit:setup-stm32-env, then retry.
  exit /b 2
)

"%STM32_MONITOR_RUNTIME%" -m stm32_monitor %*
set "STM32_MONITOR_EXIT_CODE=%ERRORLEVEL%"
exit /b %STM32_MONITOR_EXIT_CODE%
