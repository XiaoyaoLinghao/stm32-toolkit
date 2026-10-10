---
name: stm32-monitor
description: Use when a user explicitly asks to open the project-isolated STM32 Monitor UI.
---

# Open STM32 Monitor

1. Call `stm32_project_context`; stop on non-ok and never guess project, target, ELF, SVD, address, or probe.
2. Explain that the UI is observation-only, starts with zero presets, and never connects a probe or starts sampling automatically.
3. Continue only after the user's explicit request to open this project's UI.
4. Run in a terminal that can remain open. The launcher needs `STM32_TOOLKIT_DATA_ROOT` before it can find managed Python; `--data-root` is still passed to the Python CLI. Run in the foreground:

   ```powershell
   $previousStm32ToolkitDataRoot = [Environment]::GetEnvironmentVariable('STM32_TOOLKIT_DATA_ROOT', 'Process')
   try {
     [Environment]::SetEnvironmentVariable('STM32_TOOLKIT_DATA_ROOT', '${CLAUDE_PLUGIN_DATA}', 'Process')
     & '${CLAUDE_PLUGIN_ROOT}/bin/stm32-monitor.cmd' open --project '${CLAUDE_PROJECT_DIR}' --data-root '${CLAUDE_PLUGIN_DATA}'
   } finally {
     [Environment]::SetEnvironmentVariable('STM32_TOOLKIT_DATA_ROOT', $previousStm32ToolkitDataRoot, 'Process')
   }
   ```

5. Keep that terminal open while using the UI. Press Ctrl-C there to invoke the existing service shutdown and cleanup. Closing the browser tab or stopping sampling does not stop the Monitor service. Use `open` again for a fresh authenticated tab when the current link is missing, invalid, or rejected.

Never print, persist, copy, or log the fragment URL. Connect, group creation, and sampling remain explicit page actions. Use the `127.0.0.1` tab created by `open`; `localhost` is not an accepted Host alias. Do not delete a lock file or stop an unrelated process as a recovery step.
