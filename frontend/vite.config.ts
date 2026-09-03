import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 前后端分离：开发态由 Vite 代理转发，生产构建产物独立部署（可置于任意静态服务器/Nginx）
export default defineConfig({
  plugins: [react()],
  server: {
    port: 18016,
    proxy: {
      // 主后端 API (:18000)
      "/api": { target: "http://localhost:18000", changeOrigin: true },
      // RAG 制度问答服务 (:18003)，以 /rag-api 前缀区分
      "/rag-api": {
        target: "http://localhost:18003",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/rag-api/, ""),
      },
    },
  },
});
