import { defineConfig } from "vite";
export default defineConfig({
  build: {
    lib: { entry: "entry.js", name: "VivlioCore", formats: ["iife"],
           fileName: () => "vivlio-core.js" },
    outDir: "dist", emptyOutDir: true, minify: true, target: "es2020",
  },
});
