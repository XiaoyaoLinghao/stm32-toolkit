@echo off
setlocal

if not defined STM32_TOOLKIT_DATA_ROOT (
  >&2 echo stm32-toolkit-mcp: STM32_TOOLKIT_DATA_ROOT is not set. Run the generic runtime Check, then retry.
  exit /b 2
)

set "STM32_TOOLKIT_RUNTIME=%STM32_TOOLKIT_DATA_ROOT%\runtime\0.9.0\Scripts\python.exe"
if not exist "%STM32_TOOLKIT_RUNTIME%" (
  >&2 echo stm32-toolkit-mcp: runtime/0.9.0/Scripts/python.exe is missing under STM32_TOOLKIT_DATA_ROOT.
  exit /b 2
)

"%STM32_TOOLKIT_RUNTIME%" -m stm32_toolkit.mcp_server %*
set "STM32_TOOLKIT_EXIT_CODE=%ERRORLEVEL%"
exit /b %STM32_TOOLKIT_EXIT_CODE%
