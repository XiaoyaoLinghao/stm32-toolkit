import {defineConfig} from "vite";
import preact from "@preact/preset-vite";
export default defineConfig({plugins:[preact()],build:{manifest:true,sourcemap:false,rollupOptions:{output:{entryFileNames:"assets/[name]-[hash].js",chunkFileNames:"assets/[name]-[hash].js",assetFileNames:"assets/[name]-[hash][extname]"}}}});
