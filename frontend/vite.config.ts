/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// Адрес FastAPI в режиме разработки; другой порт можно задать в frontend/.env.local: API_TARGET=http://127.0.0.1:8010
export default defineConfig(({ mode }) => {
  const target = loadEnv(mode, process.cwd(), '').API_TARGET || 'http://127.0.0.1:8000'
  return {
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target, changeOrigin: false },
      '/media': { target, changeOrigin: false },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
  }
})
