import {fileURLToPath} from "node:url";
import {defineConfig} from "vitest/config";
import preact from "@preact/preset-vite";
export default defineConfig({plugins:[preact()],test:{environment:"jsdom",setupFiles:["./tests/setup.ts"],
  exclude:["**/e2e/**","**/node_modules/**","**/dist/**"],
  env:{STM32_MONITOR_WIRE_FIXTURE:fileURLToPath(new URL("./tests/wire-fixture.json",import.meta.url))},
  coverage:{provider:"v8",reportsDirectory:"coverage",reporter:["text","json"],all:true,perFile:true,
    include:["src/**/*.{ts,tsx}"],exclude:["src/env.d.ts"]}}});
