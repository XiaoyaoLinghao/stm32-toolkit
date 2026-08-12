---
name: stm32-monitor
description: Use when a user explicitly asks to open the project-isolated STM32 Monitor UI.
---

# Open STM32 Monitor

1. Call `stm32_project_context`; stop on non-ok and never guess project, target, ELF, SVD, address, or probe.
2. Explain that the UI is observation-only, starts with zero presets, and never connects a probe or starts sampling automatically.
3. Continue only after the user's explicit request to open this project's UI.
4. Run in the foreground:

   ```powershell
   & '${CLAUDE_PLUGIN_ROOT}/bin/stm32-monitor.cmd' open --project '${CLAUDE_PROJECT_DIR}' --data-root '${CLAUDE_PLUGIN_DATA}'
   ```

Never print, persist, copy, or log the fragment URL. Connect, group creation, and sampling remain explicit page actions.
