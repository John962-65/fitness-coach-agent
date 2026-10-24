/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发时 /api 代理到本地后端（python3 -m backend，默认 8000；FC_API_TARGET 可覆盖）
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.FC_API_TARGET || 'http://127.0.0.1:8000', changeOrigin: true } },
  },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
})
