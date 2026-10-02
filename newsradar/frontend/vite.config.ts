import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发期:Vite dev server 把 /api 与 /health 代理到本地 FastAPI(8000)
// 生产期:构建产物由 FastAPI 直接托管(见 app/main.py)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})