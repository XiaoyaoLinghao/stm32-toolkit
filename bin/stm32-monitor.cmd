@echo off
setlocal

if not defined STM32_TOOLKIT_DATA_ROOT (
  >&2 echo stm32-monitor: STM32_TOOLKIT_DATA_ROOT is required to locate the managed runtime before --data-root is parsed. Set it to the same data root passed to --data-root, then retry.
  exit /b 2
)

set "STM32_MONITOR_RUNTIME=%STM32_TOOLKIT_DATA_ROOT%\runtime\1.0.0\Scripts\python.exe"
if not exist "%STM32_MONITOR_RUNTIME%" (
  >&2 echo stm32-monitor: runtime/1.0.0/Scripts/python.exe is missing under STM32_TOOLKIT_DATA_ROOT. Run runtime Check or Repair for this data root, then retry.
  exit /b 2
)

"%STM32_MONITOR_RUNTIME%" -m stm32_monitor %*
set "STM32_MONITOR_EXIT_CODE=%ERRORLEVEL%"
exit /b %STM32_MONITOR_EXIT_CODE%
