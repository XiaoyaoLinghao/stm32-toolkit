import {existsSync} from "node:fs";
import {isAbsolute} from "node:path";
import {defineConfig,devices} from "@playwright/test";

// Controlled Chromium from the verified support root. The release helper binds
// STM32_MONITOR_CHROMIUM_EXECUTABLE to the exact verified browser executable;
// when it is set the config requires a rooted, existing path and fails closed
// otherwise (never silently falling back to an ambient browser).
const controlledChromium = process.env.STM32_MONITOR_CHROMIUM_EXECUTABLE;
let launchOptions: {executablePath?: string} = {};
if (controlledChromium !== undefined && controlledChromium.trim().length > 0) {
  if (!isAbsolute(controlledChromium)) {
    throw new Error("STM32_MONITOR_CHROMIUM_EXECUTABLE must be an absolute path");
  }
  if (!existsSync(controlledChromium)) {
    throw new Error(`STM32_MONITOR_CHROMIUM_EXECUTABLE does not exist: ${controlledChromium}`);
  }
  launchOptions = {executablePath: controlledChromium};
}

export default defineConfig({
  testDir: "./e2e",
  retries: 0,
  use: {browserName: "chromium", launchOptions},
  projects: [
    {name: "chromium-1280", use: {...devices["Desktop Chrome"], viewport: {width: 1280, height: 720}}},
    {name: "chromium-1024", use: {...devices["Desktop Chrome"], viewport: {width: 1024, height: 768}}},
  ],
});
