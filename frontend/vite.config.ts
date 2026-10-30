import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// VibeTrade v1.1 - 100% Static GitHub Pages Configuration
export default defineConfig({
  base: "./",
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "./src") },
  },
  server: {
    port: 5899,
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: (id: string) => {
          if (/node_modules\/(react|react-dom|react-router)\//.test(id)) return "vendor-react";
          if (/node_modules\/echarts\//.test(id)) return "vendor-charts";
          return undefined;
        },
      },
    },
  },
});
