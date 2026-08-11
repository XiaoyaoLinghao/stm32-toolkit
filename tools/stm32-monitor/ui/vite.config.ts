import {fileURLToPath} from "node:url";
import {defineConfig} from "vite";
import preact from "@preact/preset-vite";
const uiDist=fileURLToPath(new URL("../src/stm32_monitor/ui_dist",import.meta.url));
export default defineConfig({plugins:[preact()],build:{outDir:uiDist,emptyOutDir:true,manifest:true,sourcemap:false,rollupOptions:{output:{entryFileNames:"assets/[name]-[hash].js",chunkFileNames:"assets/[name]-[hash].js",assetFileNames:"assets/[name]-[hash][extname]"}}}});
